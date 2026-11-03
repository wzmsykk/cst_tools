"""Exercise the probe's scanner/checkpoint wiring with a fake native peer."""
from pathlib import Path
from uuid import uuid4
import shutil
from csttool.configuration import read_json,write_json_atomic
from test.support import validate_hom_recovery_native as module


def test_native_mesh_instrumentation_has_its_own_declared_file_handle(tmp_path):
    from test.managed_cstworker_test import build_worker_shell
    shell=build_worker_shell(tmp_path)
    worker=module.MeshWorker.__new__(module.MeshWorker);worker.__dict__.update(shell.__dict__)
    worker.batch_script_path=worker.project_path.with_suffix('')/'Model/3D/Model.run'
    worker.reject=False;worker._build_macro()
    text=worker.macro_path.read_text(encoding='ascii')
    assert text.count('Dim CSTToolsMeshFile As Integer')==1
    assert text.index('Dim CSTToolsMeshFile As Integer') < text.index('Open outFullDir & "mesh-cells.txt"')
    assert 'Print #CSTToolsMeshFile, RestoreParameterExpression("cell")' in text


def test_probe_checks_mesh_roundtrip_and_resumes_confirmation_from_disk(tmp_path,monkeypatch):
    source=tmp_path/'source.cst';source.write_bytes(b'fixture')
    class Preprocessor:
        def __init__(self,*a,**k):pass
        def preprocess(self,source,output,*a,**k):shutil.copyfile(source,output)
    class Service:
        def __init__(self,*a,**k):pass
        def stage_definition(self,*a):return {'definition_revision':'fake'}
        def verify_definition(self,*a):return {'ready':True}
    class Worker:
        reject=False
        def __init__(self,identity,config):self.directory=Path(config['taskFileDir'])
        def run_task(self,name,*,params):
            task=uuid4().hex;directory=self.directory/task;directory.mkdir(parents=True)
            if self.reject:return dict(TaskStatus='Failure',FailureReport='SOLVER_FAILED: injected')
            (directory/'mesh-cells.txt').write_text(('20' if params['cell']==6 else '10')+'\n'+str(params['cell']))
            write_json_atomic(directory/'received.json',dict(task_id=task,status='Success',phase='acknowledged'))
            freq=1147.4269 if params['fmin']<=1147.4269 else 1753.
            return dict(TaskStatus='Success',TaskID=task,ResultDirectory=str(directory),
                ReceiptPath=str(directory/'received.json'),
                PostProcessResult=[dict(resultName='frequency',value=freq),dict(resultName='rq',value=223.)])
        def stop(self):return True
    monkeypatch.setattr(module,'FixturePreprocessor',Preprocessor)
    monkeypatch.setattr(module,'ApplicationService',Service)
    monkeypatch.setattr(module,'MeshWorker',Worker)
    monkeypatch.setattr(module,'cst_processes',lambda:[])
    monkeypatch.setattr(module,'cleanup_case',lambda *a:0)
    root=tmp_path/'case';root.mkdir()
    result=module.run(source,source,root)
    assert result['passed'] and result['resume_first_phase']=='confirm'
    assert [x['cell'] for x in result['mesh_roundtrip']]==[4,6,4]
    assert [x['phase'] for x in result['attempts']].count('confirm')==1
    assert read_json(root/'scan.json')['report']['modes']
