"""Owner-side G02 empty project transaction; fake native peer, no CST."""
import ast
import json
import pytest
from csttool.application_service import ApplicationService,ServiceError
from csttool.configuration import write_json_atomic
from csttool.project_creation import BRIDGE
from test.saved_project_source_test import container


def payload(**overrides):
    return dict(kind='definition',operation='create_project',name='new-mws',installation_ref='local',module='mws',
                units={'length':'mm','frequency':'MHz'},**overrides)


def service(tmp_path,fail=False):
    calls=[]
    def create(directory,executable):
        calls.append(1)
        directory.mkdir(parents=True)
        if fail:raise OSError('injected bootstrap failure')
        model=directory/'definition.cst'
        model.write_bytes(container([('Model/3D/Model.mod',b'With Units\n .Geometry "mm"\n .Frequency "MHz"\nEnd With'),
            ('Model/Parameters.json',b'{"parameters":[]}')]))
        closure=dict(exit_confirmed=True,exit_code=0,kind='project-bootstrap')
        write_json_atomic(directory/'session-status.json',closure)
        return dict(model_path=str(model),closure=closure,status='created')
    return ApplicationService(tmp_path,'project-a',installations={'local':tmp_path/'CST.exe'},project_creator=create),calls


def test_creation_is_immutable_inspection_is_readonly_and_replay_does_not_create(tmp_path):
    app,calls=service(tmp_path)
    result=app.create_project(payload(),operation_id='operation-one')
    assert not result['ready'] and result['state']=='empty'
    assert app.inspect_model(result['document_id'],result['document_revision'])==result
    assert app.create_project(payload(),operation_id='operation-one')==result and len(calls)==1
    with pytest.raises(ServiceError,match='DOCUMENT_EXISTS'):app.create_project(payload(),operation_id='operation-two')
    changed=payload();changed['name']='different'
    with pytest.raises(ServiceError,match='REQUEST_CONFLICT'):app.create_project(changed,operation_id='operation-one')
    from pathlib import Path
    Path(result['model_path']).write_bytes(b'changed')
    with pytest.raises(ServiceError,match='STALE_DOCUMENT'):app.inspect_model(result['document_id'],result['document_revision'])


def test_failed_bootstrap_cannot_publish_or_restart_same_operation(tmp_path):
    app,calls=service(tmp_path,fail=True)
    with pytest.raises(OSError):app.create_project(payload(),operation_id='one')
    assert not (tmp_path/'control/document-names/new-mws.json').exists()
    with pytest.raises(ServiceError,match='RUN_RECONCILIATION_REQUIRED'):app.create_project(payload(),operation_id='one')
    assert len(calls)==1


@pytest.mark.parametrize('field,value',[('extra','bad'),('module','ds'),('units',{'frequency':'GHz','length':'mm'}),('name','../escape')])
def test_creation_rejects_unsupported_requests_before_native_calls(tmp_path,field,value):
    app,calls=service(tmp_path)
    request=payload();request[field]=value
    with pytest.raises(ServiceError):app.create_project(request,operation_id='one')
    assert not calls


def test_bridge_stays_in_selected_python36_and_uses_owned_api():
    ast.parse(BRIDGE,feature_version=(3,6))
    assert "DesignEnvironment.new(options=['-i'])" in BRIDGE and 'de.pid()' in BRIDGE
    assert 'project.close()' in BRIDGE and 'de.close()' in BRIDGE
    assert 'Active3D' not in BRIDGE and 'EigenmodeSolver.Start' not in BRIDGE


def test_runner_creation_is_same_async_slot_and_idempotent(tmp_path):
    from csttool.runner import Runner
    app,calls=service(tmp_path)
    runner=Runner(tmp_path);app.project_id=runner.project_id;runner.application_service=app
    try:
        runner.command(dict(schema_version=1,request_id='claim',client_id='client',operation='claim',payload={}))
        command=dict(schema_version=1,request_id='create',client_id='client',operation='start',payload=payload())
        receipt=runner.command(command)
        runner.worker.join(10)
        assert not runner.worker.is_alive()
        assert runner.snapshot()['state']=='COMPLETED',runner.snapshot()
        assert runner.snapshot()['run_kind']=='definition'
        assert runner.command(command)==receipt and len(calls)==1
        assert app.definition_operation_result(receipt['run_id'])['state']=='empty'
    finally:runner.close()


def test_committed_creation_result_gap_reconciles_without_new_de(tmp_path,monkeypatch):
    app,calls=service(tmp_path)
    import csttool.application_service as module
    original=module.write_json_atomic
    def fail(path,value):
        if path.name=='definition-result.json':raise OSError('publication gap')
        return original(path,value)
    monkeypatch.setattr(module,'write_json_atomic',fail)
    with pytest.raises(OSError):app.create_project(payload(),operation_id='gap')
    monkeypatch.setattr(module,'write_json_atomic',original)
    recovered=app.reconcile_project_creation('gap')
    assert app.reconcile_project_creation('gap')==recovered and len(calls)==1
    assert app.definition_operation_result('gap')==recovered


def test_creation_authenticated_http_and_inspect_never_recompute(tmp_path,monkeypatch):
    import threading,time
    import csttool.runner as module
    from csttool.runner_client import RunnerClient
    instances=[]
    class Configured(module.Runner):
        def __init__(self,project,executor_factory=None):
            super().__init__(project,executor_factory)
            app,self.calls=service(tmp_path);app.project_id=self.project_id
            self.application_service=app;instances.append(self)
    monkeypatch.setattr(module,'Runner',Configured)
    thread=threading.Thread(target=module.serve,args=(tmp_path,),daemon=True);thread.start()
    def wait(predicate):
        deadline=time.monotonic()+10
        while not predicate():
            if time.monotonic()>deadline:raise AssertionError('HTTP acceptance timed out')
            time.sleep(.01)
    wait(lambda:(tmp_path/'control/runner.json').exists())
    client=RunnerClient(tmp_path,'http-create');client.connect(launch=False)
    try:
        client.command('claim')
        assert client.installations()['installations'][0]['installation_ref']=='local'
        accepted=client.command('start',payload(),request_id='create-one')
        assert client.command('start',payload(),request_id='create-one')==accepted
        wait(lambda:client.status()['state']=='COMPLETED')
        result=client.definition_result(accepted['run_id'])
        assert client.inspect_model(result['document_id'],result['document_revision'])==result
        assert instances[0].calls==[1]
    finally:
        instances[0].shutdown_requested.set();thread.join(10)
        assert not thread.is_alive()


def test_empty_document_metadata_cannot_claim_ready(tmp_path):
    app,_=service(tmp_path)
    record=app.create_project(payload(),operation_id='one')
    target=tmp_path/'control/documents'/record['document_id']/(record['document_revision']+'.json')
    record['ready']=True
    write_json_atomic(target,record)
    with pytest.raises(ServiceError,match='DOCUMENT_INVALID'):app.inspect_model(record['document_id'],record['document_revision'])


def test_explicit_recovery_can_abandon_uncommitted_creation_without_replaying(tmp_path):
    from csttool.application_service import DefinitionOperationExecution
    from csttool.execution_contract import StopIntent
    app,calls=service(tmp_path,fail=True)
    with pytest.raises(OSError):app.create_project(payload(),operation_id='failed')
    execution=DefinitionOperationExecution(app,'recovery',StopIntent(),lambda **kw:None)
    execution.recover()
    assert len(calls)==1
    assert (tmp_path/'control/runs/failed/definition-abandoned.json').exists()
    with pytest.raises(ServiceError,match='OPERATION_ABANDONED'):app.definition_operation_result('failed')
    execution.recover()
    assert len(calls)==1


def test_native_bootstrap_sets_and_reads_quiet_after_binding_before_project_creation():
    assert BRIDGE.index("binding nonce mismatch") < BRIDGE.index("de.set_quiet_mode(True)")
    assert BRIDGE.index("de.set_quiet_mode(True)") < BRIDGE.index("project=de.new_mws()")
    assert "de.in_quiet_mode()" in BRIDGE
