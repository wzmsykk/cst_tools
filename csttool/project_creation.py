"""New MWS bootstrap via the selected installation's own Python ABI.

The bridge creates a new DE, obtains its documented pid(), and waits for owner
identity binding before new_mws/save/close. No Active3D or arbitrary user VBA.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
from uuid import uuid4
import psutil
from .acceptance_session import cst_processes,wait_probe
from .configuration import read_json,write_json_atomic
from .cst_process_env import cst_process_environment
from .cst_background import PrivateDesktop, BackgroundWindowObserver, WindowsWindowBackend
from .windows_desktop_process import DesktopProcess

BRIDGE = r'''
import json,os,sys,time
from pathlib import Path
root=Path(sys.argv[1]); libraries=sys.argv[2]; nonce=sys.argv[3]
sys.path.insert(0,libraries)
from cst.interface import DesignEnvironment

def record(name,value):
    path=root/name
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value),encoding='utf-8')
    os.replace(str(temp),str(path))

def stage(value):
    (root/'stage.txt').write_text(value,encoding='ascii')

de=None; project=None; failed=False
try:
    stage('create-environment')
    de=DesignEnvironment.new(options=['-i'])
    record('de-pid.json',{'pid':de.pid(),'nonce':nonce})
    deadline=time.monotonic()+30
    while not (root/'identity-bound.json').exists():
        if time.monotonic()>deadline:raise RuntimeError('owner did not bind DE identity')
        time.sleep(.05)
    if json.loads((root/'identity-bound.json').read_text(encoding='utf-8'))['nonce']!=nonce:
        raise RuntimeError('binding nonce mismatch')
    stage('quiet')
    de.set_quiet_mode(True)
    quiet=bool(de.in_quiet_mode())
    record('quiet-ready.json',{'nonce':nonce,'requested':True,'readback':quiet})
    if not quiet:raise RuntimeError('owned DE quiet readback is false')
    stage('new-mws')
    project=de.new_mws()
    stage('units-history')
    project.modeler.add_to_history('CST Tools project units','With Units\n .Geometry "mm"\n .Frequency "MHz"\nEnd With')
    stage('save')
    project.save(str(root/'definition.cst'),include_results=False)
except Exception as error:
    failed=True
    record('failure.json',{'type':type(error).__name__,'message':str(error)})
    raise
finally:
    try:
        if project is not None:
            stage('project-close')
            project.close()
    finally:
        if de is not None:
            stage('de-close')
            de.close()
    if not failed:(root/'completed.txt').write_text(nonce,encoding='ascii')
'''


class NativeProjectCreator:
    def __init__(self,on_progress=None):
        self.on_progress=on_progress

    def __call__(self,directory,executable):
        directory=Path(directory).resolve()
        executable=Path(executable).resolve(strict=True)
        from .cst_installations import infer_cst_version
        if os.name!='nt' or infer_cst_version(executable)!=2022:
            raise ValueError('UNSUPPORTED_CAPABILITY: bootstrap calibrated for CST 2022')
        runtime=executable.parent/'AMD64/python/python.exe'
        libraries=executable.parent/'AMD64/python_cst_libraries'
        if not runtime.is_file() or not libraries.is_dir():
            raise ValueError('UNSUPPORTED_CAPABILITY: installation Python runtime missing')
        nonce=uuid4().hex
        directory.mkdir(parents=True,exist_ok=False)
        script=directory/'create_project.py';script.write_text(BRIDGE,encoding='utf-8')
        env=cst_process_environment()
        for key in ('PYTHONPATH','PYTHONHOME'):env.pop(key,None)
        env['PATH']=str(executable.parent/'AMD64')+os.pathsep+env.get('PATH','')
        write_json_atomic(directory/'bootstrap-context.json',dict(runtime=str(runtime),
            runtime_sha256=hashlib.sha256(runtime.read_bytes()).hexdigest(),libraries=str(libraries),
            wmic_path=shutil.which('wmic',path=env.get('PATH','')),platform=os.name))
        baseline=cst_processes();bound=[];last_stage=[None]
        baseline_ids={(p['pid'],p['create_time']) for p in baseline}
        from contextlib import ExitStack
        with ExitStack() as stack:
            desktop=stack.enter_context(PrivateDesktop())
            windows=stack.enter_context(BackgroundWindowObserver(executable.parent,minimize=False,backend=WindowsWindowBackend(desktop.handle)))
            log=stack.enter_context((directory/'cst.log').open('wb'))
            process=DesktopProcess([str(runtime),str(script),str(directory),str(libraries),nonce],
                desktop='WinSta0\\'+desktop.name,cwd=directory,env=env,log=log)
            launcher=psutil.Process(process.pid)
            expected=(process.pid,launcher.create_time())
            write_json_atomic(directory/'session-status.json',dict(exit_confirmed=False,kind='project-bootstrap',
                owned=[dict(pid=expected[0],create_time=expected[1])]))
            def observe(report):
                if bound:windows.bind(report['owned'])
                if self.on_progress and report['stage']!=last_stage[0]:
                    self.on_progress(dict(stage=report['stage'],reason='等待原生工程创建/保存/正常退出',workspace=str(directory)))
                    last_stage[0]=report['stage']
                pidfile=directory/'de-pid.json'
                if not bound and pidfile.exists():
                    identity=read_json(pidfile)
                    if identity.get('nonce')!=nonce or type(identity.get('pid')) is not int:
                        raise ValueError('bootstrap DE identity malformed')
                    peer=psutil.Process(identity['pid'])
                    if ((peer.pid,peer.create_time()) in baseline_ids or peer.create_time()<expected[1]-2
                            or not Path(peer.exe()).resolve().is_relative_to(executable.parent)):
                        raise ValueError('bootstrap DE executable outside selected installation')
                    bound.append((peer.pid,peer.create_time()))
                    report['owned'].append(dict(pid=bound[0][0],create_time=bound[0][1]))
                    report['kind']='project-bootstrap'
                    write_json_atomic(directory/'session-status.json',report)
                    windows.bind(report['owned'])
                    write_json_atomic(directory/'identity-bound.json',dict(nonce=nonce))
            try:
                report=wait_probe(process,directory,stage_timeout=180,exit_timeout=60,
                    completion_names=('completed.txt','failure.json'),
                    expected_launcher_identity=expected,bound_roots=bound,on_observation=observe,
                    preexisting_processes=baseline,task_project=directory/'definition.cst')
            except Exception as error:
                native=read_json(directory/'failure.json') if (directory/'failure.json').exists() else None
                if native is not None:
                    raise RuntimeError('PROJECT_CREATION_FAILED: '+native.get('type','unknown')+': '+native.get('message','')+
                        '; owned exit unconfirmed; inspect '+str(directory)) from error
                raise
            finally:
                observed=windows.report()
                observed['private_desktop']=desktop.name
                write_json_atomic(directory/'window-observation.json',observed)
        observation=windows.report()
        observation.update(private_desktop=desktop.name,desktop_handle_closed=desktop.handle is None)
        write_json_atomic(directory/'window-observation.json',observation)
        report.update(exit_code=process.returncode,kind='project-bootstrap',quiet=read_json(directory/'quiet-ready.json') if (directory/'quiet-ready.json').exists() else None,
                      window_observation={k:v for k,v in observation.items() if k not in ('owned_events','actions')})
        write_json_atomic(directory/'session-status.json',report)
        if (not bound or process.returncode!=0 or not report['exit_confirmed']
                or not (directory/'completed.txt').exists()
                or (directory/'completed.txt').read_text(encoding='ascii')!=nonce):
            raise RuntimeError('PROJECT_CREATION_FAILED: inspect '+str(directory))
        return dict(status='created',model_path=str(directory/'definition.cst'),
                    closure=report,runtime_sha256=hashlib.sha256(runtime.read_bytes()).hexdigest())
