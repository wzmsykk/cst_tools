"""Owned COM new-MWS construction using the shared definition macro.

Empty saved MWS files cannot currently enter Model.run batch in CST2022. This
uses a newly created 3D object's RunScript, with no OpenFile/global Active3D.
The parent binds its modeler/DE process identity before allowing any modelling.
"""
from pathlib import Path
import os
import subprocess
from uuid import uuid4
import psutil
from .acceptance_session import cst_processes,wait_probe
from .configuration import read_json,write_json_atomic
from .cst_process_env import cst_process_environment
from .vb_codec import quote_vb_string
from .cst_background import BackgroundWindowObserver, PrivateDesktop, WindowsWindowBackend
from .windows_desktop_process import DesktopProcess


WRAPPER = r'''
param([string]$MacroPath,[string]$ModelPath,[string]$Directory,[string]$Nonce,[string]$ServerPath)
$ErrorActionPreference = 'Stop'
$studio = $null
$project = $null
$bound = $false
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Threading;
public sealed class CstToolsMacroCall {
 [DllImport("ole32.dll")] static extern int CoMarshalInterThreadInterfaceInStream(ref Guid iid, IntPtr obj, out IntPtr stream);
 [DllImport("ole32.dll")] static extern int CoGetInterfaceAndReleaseStream(IntPtr stream, ref Guid iid, out IntPtr obj);
 [DllImport("ole32.dll")] static extern int CoInitializeEx(IntPtr reserved, uint flags);
 [DllImport("ole32.dll")] static extern void CoUninitialize();
 IntPtr stream; string path;
 public volatile bool Completed;
 public string Error;
 public CstToolsMacroCall(object project, string macro) {
  path=macro;
  Guid iid=new Guid("00020400-0000-0000-C000-000000000046");
  IntPtr ptr=Marshal.GetIUnknownForObject(project);
  try { Marshal.ThrowExceptionForHR(CoMarshalInterThreadInterfaceInStream(ref iid,ptr,out stream)); }
  finally { Marshal.Release(ptr); }
 }
 public void Start() {
  Thread thread=new Thread(Run); thread.SetApartmentState(ApartmentState.STA); thread.Start();
 }
 void Run() {
  object proxy=null; bool initialized=false;
  try {
   Marshal.ThrowExceptionForHR(CoInitializeEx(IntPtr.Zero,2)); initialized=true;
   Guid iid=new Guid("00020400-0000-0000-C000-000000000046"); IntPtr ptr;
   Marshal.ThrowExceptionForHR(CoGetInterfaceAndReleaseStream(stream,ref iid,out ptr));
   try { proxy=Marshal.GetObjectForIUnknown(ptr); } finally { Marshal.Release(ptr); }
   ((dynamic)proxy).RunScript(path);
  } catch(Exception e) { Error=e.ToString(); }
  finally {
   try { if(proxy!=null) Marshal.ReleaseComObject(proxy); }
   catch(Exception e) { Error=(Error??"")+"; release: "+e.ToString(); }
   finally { if(initialized) CoUninitialize(); Completed=true; }
  }
 }
}
'@ -ReferencedAssemblies Microsoft.CSharp,System.Core
try {
 # Use the selected installation's registered COM-server command, explicitly
 # launched on this helper's non-input desktop. No global registration changes.
 $serverInfo = New-Object System.Diagnostics.ProcessStartInfo
 $serverInfo.FileName = $ServerPath
 $serverInfo.Arguments = '-activex -i'
 $serverInfo.UseShellExecute = $false
 $serverInfo.CreateNoWindow = $true
 $serverInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Minimized
 $server = [System.Diagnostics.Process]::Start($serverInfo)
 [IO.File]::WriteAllText((Join-Path $Directory 'server-process.json'), (@{pid=$server.Id} | ConvertTo-Json))
 if (!$server.WaitForInputIdle(30000)) { throw 'owned COM server did not become input-idle' }
 $studio = New-Object -ComObject CSTStudio.Application.2022
 $project = $studio.NewMWS()
 Write-Output 'stage=single-runscript; begin'
 $call = [CstToolsMacroCall]::new($project,$MacroPath)
 $call.Start()
 while (!$call.Completed) {
  $binding = Join-Path $Directory 'identity-bound.json'
  if (!$bound -and (Test-Path -LiteralPath $binding)) {
   $value = Get-Content -Raw -LiteralPath $binding | ConvertFrom-Json
   if ($value.nonce -eq $Nonce) {
    $bound = $true
    # Only the original application reference, after parent identity proof.
    $studio.SetQuietMode($true)
    Write-Output 'stage=quiet; setter-returned; requested=True; readback=not-exposed-by-COM'
    $ready = Join-Path $Directory 'quiet-ready.json'
    $temporary = Join-Path $Directory 'quiet-ready.tmp'
    [IO.File]::WriteAllText($temporary, (@{nonce=$Nonce;requested=$true;setter_returned=$true;readback='not-exposed-by-COM'} | ConvertTo-Json))
    Move-Item -LiteralPath $temporary -Destination $ready
   }
  }
  Start-Sleep -Milliseconds 20
 }
 if ($call.Error) { throw $call.Error }
 Write-Output 'stage=single-runscript; returned'
} finally {
 $binding = Join-Path $Directory 'identity-bound.json'
 if (Test-Path -LiteralPath $binding) {
  $value = Get-Content -Raw -LiteralPath $binding | ConvertFrom-Json
  if ($value.nonce -eq $Nonce) { $bound = $true }
 }
 try {
  if ($null -ne $project) {
   if ($bound -and !(Test-Path -LiteralPath (Join-Path $Directory 'completed.txt'))) {
    # Preserve only our failed new candidate, avoiding an unsaved-sheet prompt.
    Write-Output 'stage=failed-candidate-save; begin'
    $project.SaveAs($ModelPath, $false)
    Write-Output 'stage=failed-candidate-save; returned'
   }
   Write-Output 'stage=project-close; begin'
   $project.Quit()
   Write-Output 'stage=project-close; returned'
   [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($project)
  }
 } finally {
  if ($null -ne $studio) {
   # Never close an application whose new process identity was not proven.
   if ($bound) {
    Write-Output 'stage=application-close; begin'
    $studio.Quit()
    Write-Output 'stage=application-close; returned'
   }
   [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($studio)
  }
 }
}
'''


def render_identity_probe(directory,nonce):
    path=quote_vb_string(directory/'modeler-identity.tsv')
    temporary=quote_vb_string(directory/'modeler-identity.tmp')
    binding=quote_vb_string(directory/'quiet-ready.json')
    return f'''Private Declare Function CSTToolsProcessId Lib "kernel32" Alias "GetCurrentProcessId" () As Long
Private Declare Sub CSTToolsBindingSleep Lib "kernel32" Alias "Sleep" (ByVal ms As Long)
Private Sub CSTToolsBindNewProject
 Dim f As Integer, tick As Integer
 f = FreeFile
 Open "{temporary}" For Output As #f
 Print #f, "{nonce}"
 Print #f, CStr(CSTToolsProcessId())
 Close #f
 Name "{temporary}" As "{path}"
 For tick = 1 To 600
  If Dir("{binding}") <> "" Then Exit Sub
  DoEvents
  CSTToolsBindingSleep 50
 Next tick
 Err.Raise vbObjectError + 2994, "A1", "owner identity/quiet handshake did not complete"
End Sub
'''


def verify_new_com_identity(pid,executable,started,baseline_ids):
    modeler=psutil.Process(pid)
    roots=[p for p in [modeler,*modeler.parents()] if p.name().lower().startswith('cst design environment')]
    if not roots:raise ValueError('new COM DE ancestry not proven')
    de=roots[0]
    for peer in (modeler,de):
        if ((peer.pid,peer.create_time()) in baseline_ids or peer.create_time()<started-2
                or not Path(peer.exe()).resolve().is_relative_to(Path(executable).parent)):
            raise ValueError('COM instance is preexisting or outside selected installation')
    return modeler,de


def inject_definition_ownership(macro,directory,nonce,*,profile=None,mapping=None):
    """Pure ownership-code/source-map preparation, with no COM or process calls."""
    from copy import deepcopy
    import hashlib
    from .settings_projection import PROFILE,GEOMETRY_PROFILE
    if profile not in (None,PROFILE,GEOMETRY_PROFILE):raise ValueError('unknown generated definition profile')
    if profile is not None:
        from .winwrap_checks import check_module
        check_module(macro,profile=profile)
        if mapping is None or mapping.get('hashes',{}).get('outer')!=hashlib.sha256(macro.encode('ascii')).hexdigest():
            raise ValueError('source map does not bind the generated module')
        if (mapping.get('schema_version')==2 and mapping.get('profile')!=profile) or mapping.get('schema_version') not in (1,2):
            raise ValueError('source map profile differs from the generated module')
    if (macro.count('Option Explicit\n')!=1 or macro.count('Sub Main\n')!=1
            or macro.count('    On Error GoTo Failed\n')!=1 or 'Private Sub CSTToolsBindNewProject' in macro):
        raise ValueError('generated macro entry point is not unique or already bound')
    anchor='    CSTToolsStage = "parameters"\n' if profile else '    On Error GoTo Failed\n'
    if macro.count(anchor)!=1:raise ValueError('owned macro binding anchor is not unique')
    binding_line=macro[:macro.index(anchor)].count('\n')+1+(0 if profile else 1)
    declarations,body=render_identity_probe(directory,nonce).split('Private Sub',1)
    macro=macro.replace('Option Explicit\n','Option Explicit\n'+declarations,1)
    macro=macro.replace(anchor,('    CSTToolsBindNewProject\n'+anchor) if profile else (anchor+'    CSTToolsBindNewProject\n'),1)
    macro+='\nPrivate Sub'+body
    from .winwrap_emitter import check_lines
    if profile is not None:check_lines(macro.splitlines())
    if mapping is not None:
        mapping=deepcopy(mapping)
        def shift(line):return line+2+(1 if line>=binding_line else 0)
        mapping['final_outer']=[{**row,'line_start':shift(row['line_start']),'line_end':shift(row['line_end'])} for row in mapping['outer']]
        mapping['hashes']['final_outer']=hashlib.sha256(macro.encode('ascii')).hexdigest()
        mapping['ownership_injection']=dict(declaration_lines=2,binding_lines=1,binding_before_line=binding_line)
    return macro,mapping


def run_new_definition(executable,model,directory,macro,*,isolate_desktop=True,generated_profile=None,cancel_check=None):
    from .cst_installations import infer_cst_version
    executable=Path(executable).resolve(strict=True)
    if os.name!='nt' or infer_cst_version(executable)!=2022:
        raise ValueError('UNSUPPORTED_CAPABILITY: owned definition construction requires CST2022/Windows')
    directory=Path(directory).resolve();model=Path(model).resolve()
    mapping_path=directory/'source-map.json'
    mapping=read_json(mapping_path) if generated_profile and mapping_path.exists() else None
    nonce=uuid4().hex
    macro,mapping=inject_definition_ownership(macro,directory,nonce,profile=generated_profile,mapping=mapping)
    wrapper=directory/'build.ps1';wrapper.write_text(WRAPPER,encoding='utf-8')
    if mapping is not None:write_json_atomic(mapping_path,mapping)
    macro_path=directory/'probe.bas';macro_path.write_text(macro,encoding='ascii')
    baseline=cst_processes();baseline_ids={(p['pid'],p['create_time']) for p in baseline}
    bound=[]
    announced_server=[]
    options={'creationflags':subprocess.CREATE_NO_WINDOW}
    startup=subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow=7
    options['startupinfo']=startup
    from contextlib import ExitStack
    with ExitStack() as stack:
        desktop=stack.enter_context(PrivateDesktop()) if isolate_desktop else None
        windows=stack.enter_context(BackgroundWindowObserver(executable.parent,
            minimize=desktop is None,backend=WindowsWindowBackend(desktop.handle if desktop else None)))
        log=stack.enter_context((directory/'cst.log').open('wb'))
        command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
            str(wrapper),'-MacroPath',str(macro_path),'-ModelPath',str(model),
            '-Directory',str(directory),'-Nonce',nonce,
            '-ServerPath',str(executable.parent/'AMD64/CST DESIGN ENVIRONMENT_AMD64.exe')]
        if desktop is not None:
            process=DesktopProcess(command,desktop='WinSta0\\'+desktop.name,cwd=directory,
                                   env=cst_process_environment(),log=log)
        else:
            process=subprocess.Popen(command,cwd=directory,env=cst_process_environment(),
                                     stdout=log,stderr=subprocess.STDOUT,**options)
        launcher=psutil.Process(process.pid);expected=(process.pid,launcher.create_time())
        write_json_atomic(directory/'session-status.json',dict(exit_confirmed=False,owned=[dict(pid=expected[0],create_time=expected[1])]))
        def observe(report):
            if cancel_check is not None:
                from .hom_scan import ScanInterrupted
                try:cancel_check()
                except ScanInterrupted:
                    # Signal the owned macro and keep observing standard exit;
                    # abandoning wait_probe here would leave a live COM instance.
                    (directory/'cancel.request').touch(exist_ok=True)
            server_file=directory/'server-process.json'
            if not announced_server and server_file.exists():
                server=psutil.Process(read_json(server_file)['pid'])
                if (server.ppid()!=process.pid or server.create_time()<expected[1]-2
                        or (server.pid,server.create_time()) in baseline_ids
                        or Path(server.exe()).resolve()!= (executable.parent/'AMD64/CST DESIGN ENVIRONMENT_AMD64.exe').resolve()):
                    raise ValueError('explicit COM server identity not proven')
                announced_server.append((server.pid,server.create_time()))
            if announced_server:
                windows.bind(report['owned'])
            identity=directory/'modeler-identity.tsv'
            if bound or not identity.exists():return
            lines=identity.read_text(encoding='ascii').splitlines()
            if len(lines)!=2 or lines[0]!=nonce or not lines[1].isdigit():
                raise ValueError('invalid COM modeler identity frame')
            modeler,de=verify_new_com_identity(int(lines[1]),executable,expected[1],baseline_ids)
            if not announced_server or (de.pid,de.create_time())!=announced_server[0]:
                raise ValueError('COM object did not bind the explicitly launched server')
            bound.append((de.pid,de.create_time()))
            report['owned'].extend(dict(pid=p.pid,create_time=p.create_time()) for p in (modeler,de))
            write_json_atomic(directory/'session-status.json',report)
            windows.bind(report['owned'])
            write_json_atomic(directory/'identity-bound.json',dict(nonce=nonce))
        try:
            report=wait_probe(process,directory,expected_launcher_identity=expected,bound_roots=bound,
                preexisting_processes=baseline,task_project=model,on_observation=observe,stage_timeout=180,exit_timeout=60)
        finally:
            observed=windows.report()
            observed['private_desktop']=desktop.name if desktop else None
            write_json_atomic(directory/'window-observation.json',observed)
    window_report=windows.report()
    window_report['private_desktop']=desktop.name if desktop else None
    window_report['desktop_handle_closed']=desktop.handle is None if desktop else None
    write_json_atomic(directory/'window-observation.json',window_report)
    report.update(exit_code=process.returncode)
    write_json_atomic(directory/'session-status.json',report)
    if not bound:raise RuntimeError('new COM instance was not identity-bound; inspect '+str(directory))
    quiet=read_json(directory/'quiet-ready.json') if (directory/'quiet-ready.json').exists() else None
    summary={k:v for k,v in window_report.items() if k not in ('owned_events','actions')}
    summary.update(owned_window_events=len(window_report['owned_events']),minimize_actions=len(window_report['actions']))
    return dict(exit_code=process.returncode,exit_confirmed=report['exit_confirmed'],
                quiet=quiet,window_observation=summary,
                window_observation_path=str(directory/'window-observation.json'))
