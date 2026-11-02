"""Explicit G04 serial real-CST acceptance of shared single-simulation service."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.acceptance_session import exclusive_probe,wait_probe,cst_processes
from csttool.application_service import ApplicationService
from csttool.configuration import write_json_atomic
from csttool.cst_process_env import cst_process_environment
from csttool.execution_contract import StopIntent
from csttool.vb_codec import quote_vb_string


def render_model(root):
    history=(ROOT/'test/fixtures/a1-pillbox-history.vb').read_text(encoding='utf-8')
    lines=[line for line in history.splitlines() if line.strip() and not line.lstrip().startswith("'")]
    # Bounded chunks avoid WinWrap physical continuation limit.
    history_code='\n'.join('    history = history & "'+quote_vb_string(line)+'" & vbCrLf' for line in lines)
    params='\n'.join(f'    StoreParameter "{key}", "{value}"' for key,value in
                     [('R','100'),('L','100'),('fmin','500'),('fmax','2000'),('nmodes','1'),('cell','4')])
    return f''''#Language "WWB-COM"
Option Explicit
Sub Main
    Dim history As String, f As Integer, message As String
    On Error GoTo Failed
{params}
    history = ""
{history_code}
    If Not AddToHistory("G04 Pillbox definition", history) Then Err.Raise vbObjectError + 2991, "G04", "history rejected"
    SaveAs "{quote_vb_string(root/'source.cst')}", False
    f = FreeFile
    Open "{quote_vb_string(root/'completed.txt')}" For Output As #f
    Print #f, "saved"
    Close #f
    Exit Sub
Failed:
    message = CStr(Err.Number) & " " & Err.Description
    On Error Resume Next
    Close
    f = FreeFile
    Open "{quote_vb_string(root/'failed.txt')}" For Output As #f
    Print #f, message
    Close #f
End Sub
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cst-exe',required=True,type=Path)
    parser.add_argument('--run-cst',action='store_true')
    args=parser.parse_args()
    if not args.run_cst:parser.error('requires explicit --run-cst')
    with exclusive_probe(ROOT):
        root=ROOT/'artifacts'/('single-g04-'+uuid4().hex[:8]);root.mkdir()
        print('G04_ROOT='+str(root),flush=True)
        macro=root/'create.bas';macro.write_text(render_model(root),encoding='ascii')
        # Own COM references are closed in finally, including RunScript exceptions.
        wrapper=root/'create.ps1'
        wrapper.write_text("""param([string]$MacroPath)
$ErrorActionPreference = 'Stop'
$studio = $null
$project = $null
try {
 $studio = New-Object -ComObject CSTStudio.Application.2022
 $project = $studio.NewMWS()
 $project.RunScript($MacroPath)
} finally {
 if ($null -ne $project) {
  $project.SaveAs((Join-Path (Split-Path $MacroPath) 'source.cst'), $false)
  $project.Quit()
  [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($project)
 }
 if ($null -ne $studio) {
  $studio.Quit()
  [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($studio)
 }
}
""",encoding='utf-8')
        baseline=cst_processes()
        with (root/'creation.log').open('wb') as stream:
            proc=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
                str(wrapper),
                '-MacroPath',str(macro)],cwd=root,env=cst_process_environment(),stdout=stream,stderr=subprocess.STDOUT)
            status=wait_probe(proc,root,preexisting_processes=baseline,task_project=root/'source.cst')
        if not status['exit_confirmed'] or status['foreign_processes'] or proc.returncode!=0 or (root/'failed.txt').exists():
            raise RuntimeError('creation failed; inspect '+str(root))
        service=ApplicationService(root,'g04-pillbox',installations={'local':args.cst_exe})
        definition=service.stage_definition('pillbox',root/'source.cst','local')
        definition=service.verify_definition('pillbox',definition['definition_revision'])
        write_json_atomic(root/'g03.json',definition)
        payload=dict(kind='simulation',document_id='pillbox',definition_revision=definition['definition_revision'])
        execution=service.execute_simulation(payload,run_id='g04-single',stop=StopIntent(),
            update=lambda **values:print(json.dumps(values,ensure_ascii=False),flush=True))
        execution.run(payload)
        result=service.get_simulation_results('g04-single')
        write_json_atomic(root/'acceptance.json',dict(gate='G04',result=result,real_cst=True))
        print('G04_ACCEPTED',flush=True)

if __name__=='__main__':main()
