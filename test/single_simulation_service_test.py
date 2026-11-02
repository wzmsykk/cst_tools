"""Shared-service fake-peer acceptance; no CST, native verifier or G03 acceptance."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from csttool.application_service import ApplicationService,ServiceError
from csttool.configuration import read_json,write_json_atomic
from csttool.execution_contract import StopIntent
from csttool.native_execution_capture import KEYS,NATIVE_VERSION
from csttool.run_store import RunStore
from csttool.worker_models import SimulationResult,WorkerConfig
from test.a1_history_profile_test import HISTORY,PARAMETERS
from test.saved_project_source_test import container


def fake_verifier(path,projection,installation):
    return dict(status='verified',source_sha256=projection.source_hash,scope='root',
                gates=['saved-reopened','identity','settings','standard-close'],fake_only=True)


class FakeWorker:
    calls=0
    stop_error=False
    metrics=(500.,1.2)
    capture_bad=False
    def __init__(self,identity,config,logger=None):
        self.config=config
        self.root=config.task_directory/uuid4().hex;self.root.mkdir(parents=True)
        self.model=self.root/'worker-input.cst';shutil.copyfile(config.project_path,self.model)
        self.store=RunStore(config.project_directory,config.run_directory)
        self.task_id=uuid4().hex
        self.intent=self.store.prepare_execution_attempt(self.task_id,definition_path=config.project_path,
            model_path=self.model,config=config.execution_config,project_id=config.execution_project_id,executable=config.executable,
            definition_revision=config.execution_definition_revision)
        self.observations=self.root/'native';self.observations.mkdir()

    @property
    def execution_identity(self):
        return dict({key:self.intent[key] for key in ('task_id','project_id','definition_revision','definition_sha256')},
                    session_id=self.root.name)

    def run_task(self,name,*,params):
        assert params=={}
        type(self).calls+=1
        result=self.config.result_directory/'project.cst';result.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(self.model,result)
        post=[dict(resultName='frequency',value=self.metrics[0]),dict(resultName='rq',value=self.metrics[1])]
        self.store.event(self.task_id,'received');self.store.event(self.task_id,'acknowledged')
        metadata=dict(format='CSTEXEC1',nonce=self.intent['nonce'],project=str(self.model.with_suffix('')),
                      build=NATIVE_VERSION,solver='HF Eigenmode',length='mm',frequency='MHz')
        values=dict(SolverTypeTet='OK:1',FrequencyTargetActive='OK:True',FrequencyTargetValue='OK:500',
                    AdaptionActiveTet='OK:False',Modes='OK:1',MeshType='OK:1')
        for phase in ('pre','started','post'):
            frame=dict(metadata,phase=phase)
            if phase=='pre':frame.update({key:'MISSING' for key in KEYS})
            if phase=='post':frame.update(values,solver_return='1',calculated_modes='1')
            frame['end']='CSTEXEC1'
            (self.observations/('native-'+phase+'.tsv')).write_text(''.join(k+'\t'+v+'\n' for k,v in frame.items()))
        db=self.model.with_suffix('')/'Result/Model.db';db.parent.mkdir(parents=True);db.write_bytes(b'fake DB')
        receipt=self.root/'received.json'
        write_json_atomic(receipt,dict(task_id=self.task_id,session_id=self.root.name,phase='acknowledged',status='Success',
            postprocess=post,snapshot_sha256=hashlib.sha256(result.read_bytes()).hexdigest()))
        self.store.artifacts(self.task_id,received=receipt)
        return SimulationResult('single','Success',name,{},post,snapshot=result,task_id=self.task_id,receipt_path=receipt)

    def stop(self):
        if self.stop_error:raise RuntimeError('injected unconfirmed stop')
        return True
    def request_stop(self):pass
    def finalize_execution_capture(self):
        closure=dict(exit_confirmed=True,active_pids=[],task_project=str(self.model),
                     owned=[dict(pid=123,create_time=1)],exit_code=0)
        receipt=self.store.finalize_execution_attempt(self.task_id,observations=self.observations,closure=closure)
        return {**receipt,'status':'execution-snapshot-mismatch'} if self.capture_bad else receipt


@pytest.fixture(autouse=True)
def reset_fake():
    FakeWorker.calls=0;FakeWorker.stop_error=False;FakeWorker.metrics=(500.,1.2);FakeWorker.capture_bad=False


def make_service(tmp_path,*,verified=True,project_id='project-test'):
    exe=tmp_path/'install/CST.exe';exe.parent.mkdir(exist_ok=True);exe.write_bytes(b'fake launcher')
    modeler=exe.parent/'AMD64/modeler_AMD64.exe';modeler.parent.mkdir(exist_ok=True);modeler.write_bytes(b'fake modeler')
    source=tmp_path/'owner-source.cst'
    source.write_bytes(container([('Model/3D/Model.mod',HISTORY.encode()),
                                  ('Model/Parameters.json',json.dumps({'parameters':PARAMETERS}).encode())]))
    service=ApplicationService(tmp_path,project_id,installations={'local':exe},
                               definition_verifier=fake_verifier if verified else None,worker_factory=FakeWorker)
    definition=service.stage_definition('document-a',source,'local')
    payload=dict(kind='simulation',document_id='document-a',definition_revision=definition['definition_revision'])
    return service,payload,definition


def test_pending_definition_cannot_launch_and_caller_cannot_assert_ready(tmp_path):
    service,payload,definition=make_service(tmp_path,verified=False)
    assert definition['ready'] is False
    with pytest.raises(ServiceError,match='DEFINITION_NOT_READY'):service.preflight(payload)
    with pytest.raises(ServiceError,match='INVALID_ARGUMENT'):service.preflight({**payload,'ready':True})
    assert FakeWorker.calls==0
    service.definition_verifier=fake_verifier
    assert service.verify_definition(payload['document_id'],payload['definition_revision'])['ready']


def test_fake_single_run_uses_native_runstore_ack_and_adoption_then_query(tmp_path):
    service,payload,_=make_service(tmp_path)
    status=[]
    execution=service.execute_simulation(payload,run_id='run-a',stop=StopIntent(),update=lambda **kw:status.append(kw))
    execution.run(payload)
    assert FakeWorker.calls==1 and execution.session_safety()=='confirmed-closed'
    result=service.get_simulation_results('run-a')
    assert result['frequency_mhz']==500 and result['rq_ohm']==1.2
    assert result['capture']['database_verified'] and not result['capture']['publish_ready']
    assert result['capture']['binding']['definition_revision']==result['definition_revision']
    assert execution._log.path.exists() and execution._log.jsonl_path.exists()
    assert all(getattr(handler,'stream',None) is None for handler in execution._log._handlers)
    assert '连续确认计算边界' not in (execution.overview.directory/'summary.md').read_text(encoding='utf-8')
    task=read_json(tmp_path/'control/runs/run-a/tasks'/result['task_id']/'attempt.json')
    assert task['event']=='algorithm_adopted'
    artifacts=read_json(tmp_path/'control/runs/run-a/tasks'/result['task_id']/'artifacts.json')
    assert read_json(tmp_path/artifacts['received']['path'])['phase']=='algorithm_adopted'
    with pytest.raises(ServiceError,match='RUN_RECONCILIATION_REQUIRED'):
        service.execute_simulation(payload,run_id='run-a',stop=StopIntent(),update=lambda **kw:None).run(payload)
    assert FakeWorker.calls==1
    with pytest.raises(ServiceError,match='RESULT_CHANGED'):service.get_simulation_results('run-a','old')


@pytest.mark.parametrize('field,value',[('resume',True),('worker_count',2),('source_project','evil.cst'),
                                     ('installation',{'executable':'evil.exe'}),('parameters',{}),('algorithm',{})])
def test_single_submission_rejects_legacy_overrides(tmp_path,field,value):
    service,payload,_=make_service(tmp_path)
    with pytest.raises(ServiceError,match='INVALID_ARGUMENT'):service.preflight({**payload,field:value})
    assert FakeWorker.calls==0


def test_changed_frozen_metadata_or_project_is_not_adopted(tmp_path):
    service,payload,definition=make_service(tmp_path)
    path=service._directory(payload['document_id'],payload['definition_revision'])/'definition.json'
    definition['config']['target_value']='600';write_json_atomic(path,definition)
    with pytest.raises(ServiceError,match='STALE_DOCUMENT'):service.preflight(payload)


@pytest.mark.parametrize('fault',['stop','capture','metrics'])
def test_bad_close_capture_or_metrics_never_publish_result(tmp_path,fault):
    service,payload,_=make_service(tmp_path)
    if fault=='stop':FakeWorker.stop_error=True
    if fault=='capture':FakeWorker.capture_bad=True
    if fault=='metrics':FakeWorker.metrics=(float('nan'),1.)
    execution=service.execute_simulation(payload,run_id='run-a',stop=StopIntent(),update=lambda **kw:None)
    with pytest.raises((RuntimeError,ValueError)):execution.run(payload)
    assert not (tmp_path/'control/runs/run-a/simulation-result.json').exists()
    assert execution.recovery_required()


def test_stop_before_worker_dispatch_does_not_create_cst_or_retry(tmp_path):
    service,payload,_=make_service(tmp_path);stop=StopIntent();stop.request()
    execution=service.execute_simulation(payload,run_id='run-a',stop=stop,update=lambda **kw:None)
    from csttool.hom_scan import ScanInterrupted
    with pytest.raises(ScanInterrupted):execution.run(payload)
    assert FakeWorker.calls==0 and not execution.recovery_required()


def test_runner_simulation_receipt_replay_and_kind_state(tmp_path):
    from csttool.runner import Runner
    from test.runner_test import command,wait_until
    runner=Runner(tmp_path)
    try:
        service,payload,_=make_service(tmp_path,project_id=runner.project_id)
        runner.application_service=service
        runner.command(command('claim'))
        start=command('start',payload)
        receipt=runner.command(start)
        wait_until(lambda:runner.snapshot()['state']=='COMPLETED')
        assert runner.command(start)==receipt
        assert FakeWorker.calls==1
        result=runner.simulation_results(receipt['run_id'])
        assert result['frequency_mhz']==500
        assert runner.snapshot()['run_kind']=='simulation' and runner.snapshot()['total_tasks']==1
        assert runner.snapshot()['coverage'] is None
        runner.worker.join()
    finally:runner.close()


def test_managed_single_macro_hooks_reuse_existing_protocol(tmp_path,monkeypatch):
    from csttool.managed_cstworker import ManagedCSTWorker
    service,payload,definition=make_service(tmp_path)
    monkeypatch.setattr(ManagedCSTWorker,'_start',lambda worker:None)
    config=WorkerConfig(tmp_path/'temp/worker',tmp_path/'result/worker',service.installations['local'],
        service._directory('document-a',definition['definition_revision'])/'definition.cst',(),
        run_directory=tmp_path/'logs/run',project_directory=tmp_path,
        execution_config=__import__('csttool.execution_snapshot',fromlist=['ExecutionConfig']).ExecutionConfig(**definition['config']),
        execution_project_id=service.project_id,execution_definition_sha256=definition['source_sha256'])
    worker=ManagedCSTWorker('single',config)
    text=worker.macro_path.read_text()
    assert text.count('solverReturn = EigenmodeSolver.Start')==1
    assert text.index('            CaptureBeforeSolver')<text.index('solverReturn = EigenmodeSolver.Start')
    assert text.index('            CaptureAfterSolver solverReturn')>text.index('solverReturn = EigenmodeSolver.Start')
    assert 'modelNeedsRecovery = False\n            CaptureBeforeSolver' in text
    assert 'CSTP_WriteCompletion' in text and 'CSTC2_WriteCloseReceipt' in text
    with pytest.raises(ValueError,match='forbids overrides'):
        worker.run_task('bad',params={'fmin':900})


def test_result_publication_gap_reconciles_without_compute_or_duplicate_adoption(tmp_path,monkeypatch):
    import csttool.application_service as module
    service,payload,_=make_service(tmp_path)
    original=module.write_json_atomic
    def fail_result(path,value):
        if Path(path).name=='simulation-result.json':raise OSError('injected final publication failure')
        return original(path,value)
    monkeypatch.setattr(module,'write_json_atomic',fail_result)
    with pytest.raises(OSError,match='publication failure'):
        service.execute_simulation(payload,run_id='run-a',stop=StopIntent(),update=lambda **kw:None).run(payload)
    journal=tmp_path/'control/runs/run-a/events.jsonl';before=journal.read_bytes()
    monkeypatch.setattr(module,'write_json_atomic',original)
    service.reconcile_simulation('run-a')
    assert service.get_simulation_results('run-a')['frequency_mhz']==500
    assert journal.read_bytes()==before and FakeWorker.calls==1
    service.reconcile_simulation('run-a')
    assert FakeWorker.calls==1


def test_initial_intent_write_failure_releases_project_lock(tmp_path,monkeypatch):
    import csttool.application_service as module
    from csttool.project_run_lock import ProjectRunLock
    service,payload,_=make_service(tmp_path)
    def failed(*args,**kwargs):raise OSError('disk fault')
    monkeypatch.setattr(module,'write_json_atomic',failed)
    with pytest.raises(OSError):
        service.execute_simulation(payload,run_id='run-a',stop=StopIntent(),update=lambda **kw:None).run(payload)
    lock=ProjectRunLock(tmp_path);lock.acquire();lock.release()


def test_native_capture_after_last_stop_check_and_separate_failure_stage(tmp_path,monkeypatch):
    from csttool.managed_cstworker import ManagedCSTWorker
    from csttool.execution_snapshot import ExecutionConfig
    service,payload,definition=make_service(tmp_path)
    monkeypatch.setattr(ManagedCSTWorker,'_start',lambda worker:None)
    config=WorkerConfig(tmp_path/'temp/worker',tmp_path/'result/worker',service.installations['local'],
        service._directory('document-a',definition['definition_revision'])/'definition.cst',(),
        run_directory=tmp_path/'logs/run',project_directory=tmp_path,
        execution_config=ExecutionConfig(**definition['config']),execution_project_id=service.project_id,
        execution_definition_sha256=definition['source_sha256'])
    text=ManagedCSTWorker('single',config).macro_path.read_text()
    assert text.index('CSTPMW_CheckStop "before-solver"')<text.index('            CaptureBeforeSolver')
    assert text.index('            CaptureBeforeSolver')<text.index('"calling EigenmodeSolver.Start"')
    assert 'stage = "native-capture-post"\n            CaptureAfterSolver' in text


def test_runner_stop_thread_publication_cannot_join_before_start(tmp_path,monkeypatch):
    import threading,time
    from csttool.runner import Runner
    from test.runner_test import WaitingExecution,command,wait_until
    WaitingExecution.gate.clear()
    original=threading.Thread.start
    def delayed_start(thread):
        if thread.name=='RUNNER/STOP':
            WaitingExecution.gate.set();time.sleep(.1)
        return original(thread)
    monkeypatch.setattr(threading.Thread,'start',delayed_start)
    runner=Runner(tmp_path,WaitingExecution)
    try:
        runner.command(command('claim'));result=runner.command(command('start'))
        wait_until(lambda:runner.executor is not None)
        runner.command(command('stop',run_id=result['run_id']))
        runner.worker.join(3)
        assert runner.snapshot()['state']=='INTERRUPTED'
    finally:WaitingExecution.gate.set();runner.close()


def test_runner_recover_repairs_simulation_publication_gap_without_legacy_backend(tmp_path,monkeypatch):
    import csttool.application_service as module
    from csttool.runner import Runner
    from test.runner_test import command,wait_until
    runner=Runner(tmp_path)
    original=module.write_json_atomic
    def fail_final(path,value):
        if Path(path).name=='simulation-result.json':raise OSError('publication gap')
        return original(path,value)
    try:
        service,payload,_=make_service(tmp_path,project_id=runner.project_id);runner.application_service=service
        monkeypatch.setattr(module,'write_json_atomic',fail_final)
        runner.command(command('claim'));started=runner.command(command('start',payload))
        wait_until(lambda:runner.snapshot()['state']=='RECOVERY_REQUIRED');runner.worker.join()
        assert FakeWorker.calls==1
        monkeypatch.setattr(module,'write_json_atomic',original)
        runner.command(command('recover'))
        wait_until(lambda:runner.snapshot()['state']=='IDLE');runner.worker.join()
        assert runner.simulation_results(started['run_id'])['frequency_mhz']==500
        assert FakeWorker.calls==1
    finally:runner.close()


def test_authenticated_http_shared_result_query_and_lost_response_replay(tmp_path,monkeypatch):
    import threading
    import csttool.runner as module
    from csttool.runner_client import RunnerClient
    from test.runner_test import wait_until
    base=module.Runner;instances=[]
    class ConfiguredRunner(base):
        def __init__(self,project,executor_factory=None):
            super().__init__(project,executor_factory)
            service,payload,_=make_service(Path(project),project_id=self.project_id)
            self.application_service=service;self.test_payload=payload;instances.append(self)
    monkeypatch.setattr(module,'Runner',ConfiguredRunner)
    thread=threading.Thread(target=module.serve,args=(tmp_path,),daemon=True);thread.start()
    wait_until(lambda:(tmp_path/'control/runner.json').exists())
    client=RunnerClient(tmp_path,'http-client');client.connect(launch=False)
    try:
        client.command('claim');request=uuid4().hex
        receipt=client.command('start',instances[0].test_payload,request_id=request)
        # A lost application response is recovered by repeating the same command.
        assert client.command('start',instances[0].test_payload,request_id=request)==receipt
        wait_until(lambda:client.status()['state']=='COMPLETED')
        instances[0].worker.join()
        result=client.simulation_results(receipt['run_id'])
        assert result['rq_ohm']==1.2 and FakeWorker.calls==1
        exported=client.command('export_simulation_results',dict(run_id=result['run_id'],
            result_revision=result['result_revision'],formats=['json','csv']),request_id='export-http')
        assert exported['accepted'] and len(exported['artifacts'])==2
        assert client.command('export_simulation_results',dict(run_id=result['run_id'],
            result_revision=result['result_revision'],formats=['json','csv']),request_id='export-http')==exported
        assert FakeWorker.calls==1
        from csttool.runner_client import RunnerRejected
        with pytest.raises(RunnerRejected) as rejected:client.simulation_results(receipt['run_id'],'stale')
        assert rejected.value.code=='RESULT_CHANGED'
    finally:
        instances[0].shutdown_requested.set();thread.join(5)
        assert not thread.is_alive()


def test_corrupt_definition_is_explicit_rejection_and_cannot_launch(tmp_path):
    service,payload,_=make_service(tmp_path)
    path=service._directory(payload['document_id'],payload['definition_revision'])/'definition.json'
    path.write_text('{"ready":true,"ready":true}')
    with pytest.raises(ServiceError,match='DEFINITION_INVALID'):service.preflight(payload)
    assert FakeWorker.calls==0


def test_definition_target_min_comparison_keeps_decimal_precision(tmp_path):
    service,payload,_=make_service(tmp_path)
    source=tmp_path/'owner-source.cst'
    history=HISTORY.replace('.SetFrequencyTarget True, "fmin"','.SetFrequencyTarget True, "500.000000000000001"')
    source.write_bytes(container([('Model/3D/Model.mod',history.encode()),
                                 ('Model/Parameters.json',json.dumps({'parameters':PARAMETERS}).encode())]))
    with pytest.raises(ServiceError,match='UNSUPPORTED_CAPABILITY'):
        service.stage_definition('document-b',source,'local')


def test_unsupported_capture_encoding_is_rejected_before_worker_creation(tmp_path):
    project=tmp_path/'中文项目';project.mkdir()
    service,payload,_=make_service(project)
    with pytest.raises(ServiceError,match='ASCII project paths'):service.preflight(payload)
    assert FakeWorker.calls==0


def test_preflight_hash_does_not_hold_control_lock_and_rechecks_ownership(tmp_path,monkeypatch):
    import threading
    from csttool.runner import Runner
    from test.runner_test import command
    runner=Runner(tmp_path);service,payload,_=make_service(tmp_path,project_id=runner.project_id)
    runner.application_service=service
    entered,release=threading.Event(),threading.Event();errors=[]
    original=service.preflight
    def blocked(value):entered.set();release.wait(4);return original(value)
    monkeypatch.setattr(service,'preflight',blocked)
    def submit():
        try:runner.command(command('start',payload))
        except Exception as exc:errors.append(exc)
    runner.command(command('claim'));thread=threading.Thread(target=submit);thread.start()
    probe=None
    try:
        assert entered.wait(2)
        probe=threading.Thread(target=runner.snapshot);probe.start();probe.join(.5)
        assert not probe.is_alive()
        runner.command(command('release'))
        release.set();thread.join(3)
        assert errors and 'ownership or run changed' in str(errors[0])
        assert FakeWorker.calls==0
    finally:
        release.set();thread.join(4)
        if probe:probe.join(4)
        runner.close()


def test_definition_changed_after_preflight_is_rejected_before_cst_launch(tmp_path,monkeypatch):
    from csttool.managed_cstworker import ManagedCSTWorker
    from csttool.execution_snapshot import ExecutionConfig
    service,payload,definition=make_service(tmp_path)
    source=service._directory('document-a',definition['definition_revision'])/'definition.cst'
    config=WorkerConfig(tmp_path/'temp/worker',tmp_path/'result/worker',service.installations['local'],source,(),
        run_directory=tmp_path/'logs/run',project_directory=tmp_path,
        execution_config=ExecutionConfig(**definition['config']),execution_project_id=service.project_id,
        execution_definition_sha256=definition['source_sha256'])
    source.write_bytes(b'changed after preflight')
    def forbidden(worker):raise AssertionError('CST must not launch')
    monkeypatch.setattr(ManagedCSTWorker,'_start',forbidden)
    with pytest.raises(ValueError,match='refuse CST launch'):ManagedCSTWorker('single',config)


def test_export_adopted_result_is_stable_and_never_recomputes(tmp_path):
    import csv
    service,payload,_=make_service(tmp_path)
    service.execute_simulation(payload,run_id='export-one',stop=StopIntent(),update=lambda **kw:None).run(payload)
    result=service.get_simulation_results('export-one')
    exported=service.export_simulation_results('export-one',result['result_revision'],['json','csv'])
    assert exported==service.export_simulation_results('export-one',result['result_revision'],['csv','json'])
    assert FakeWorker.calls==1
    csvpath=next(tmp_path/a['path'] for a in exported['artifacts'] if a['format']=='csv')
    rows=list(csv.DictReader(csvpath.open(encoding='utf-8',newline='')))
    assert [r['unit'] for r in rows]==['MHz','ohm']
    with pytest.raises(ServiceError,match='RESULT_CHANGED'):
        service.export_simulation_results('export-one','wrong',['json'])
    with pytest.raises(ServiceError,match='INVALID_ARGUMENT'):
        service.export_simulation_results('export-one',result['result_revision'],['csv','csv'])
    csvpath.write_text('corrupted')
    with pytest.raises(ServiceError,match='RESULT_CHANGED'):
        service.export_simulation_results('export-one',result['result_revision'],['csv'])
