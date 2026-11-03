"""Fake-peer fault boundaries; these do not assert native solver acceptance."""
import hashlib
import json
import re
import pytest

from csttool.configuration import write_json_atomic,read_json
from csttool.definition_editing import edit_document,reconcile_edit,render_history
from csttool.execution_contract import StopIntent
from test.definition_editing_test import draft,request
from test.saved_project_source_test import container
from test.single_simulation_service_test import make_service,FakeWorker


@pytest.fixture(autouse=True)
def reset_fake_state():
    FakeWorker.calls=0;FakeWorker.stop_error=False;FakeWorker.metrics=(500.,1.2);FakeWorker.capture_bad=False


@pytest.mark.parametrize('fault',['partial-raise','partial-return','response-loss','unconfirmed-close'])
def test_failed_required_step_cannot_publish_or_replay_native_edit(tmp_path,monkeypatch,fault):
    # Isolate publication semantics from the separately tested native gate.
    monkeypatch.setattr('csttool.definition_editing.require_calibration',lambda: {'fake_only':True})
    app,empty,model,configured,calls=draft(tmp_path)
    count=[]
    pointer=tmp_path/'control/documents'/configured['document_id']/'current.json'
    before=pointer.read_bytes()
    def editor(exe,path,directory,macro):
        count.append('one native attempt')
        history=render_history(configured['spec'])[0]
        if fault=='partial-raise':
            (directory/'partial-step.txt').write_text('simulated parameter/setting already changed')
            raise RuntimeError('required property failed after earlier steps')
        if fault=='partial-return': history=history.split('With Cylinder')[0]
        path.write_bytes(container([('Model/3D/Model.mod',history.encode()),
            ('Model/Parameters.json',json.dumps({'parameters':[dict(name=k,expr=v['expression'],descr=v['description'])
                for k,v in configured['spec']['parameters'].items()]}).encode())]))
        nonce=re.search(r'Print #f, "([a-f0-9]{32})"',macro)[1]
        (directory/'completed.txt').write_text(nonce)
        if fault=='response-loss':raise TimeoutError('native response lost after save')
        return dict(exit_confirmed=fault!='unconfirmed-close',exit_code=0)
    app.definition_editor=editor
    command=request(configured,'save_project')
    with pytest.raises((RuntimeError,ValueError,OSError)):
        edit_document(app,command,operation_id='fault-save')
    assert pointer.read_bytes()==before and len(count)==1
    assert not (tmp_path/'control/runs/fault-save/definition-commit.json').exists()
    assert not (tmp_path/'control/runs/fault-save/definition-result.json').exists()
    with pytest.raises(ValueError,match='RUN_RECONCILIATION_REQUIRED'):reconcile_edit(app,'fault-save')
    with pytest.raises(ValueError,match='RUN_RECONCILIATION_REQUIRED'):edit_document(app,command,operation_id='fault-save')
    assert len(count)==1 and calls==[1]


@pytest.mark.parametrize('field',['project_id','definition_sha256'])
def test_wrong_worker_identity_is_zero_dispatch(tmp_path,field):
    service,payload,_=make_service(tmp_path)
    class WrongIdentity(FakeWorker):
        @property
        def execution_identity(self):return {**super().execution_identity,field:'wrong'}
    WrongIdentity.calls=0;service.worker_factory=WrongIdentity
    execution=service.execute_simulation(payload,run_id='identity',stop=StopIntent(),update=lambda **kw:None)
    with pytest.raises(ValueError):execution.run(payload)
    assert WrongIdentity.calls==0 and execution.session_safety()=='confirmed-closed'
    assert not (tmp_path/'control/runs/identity/simulation-result.json').exists()


@pytest.mark.parametrize('after_response',[False,True])
def test_solver_exception_or_lost_completion_response_never_retries_dispatch(tmp_path,after_response):
    service,payload,_=make_service(tmp_path)
    class Broken(FakeWorker):
        def run_task(self,name,*,params):
            if after_response: super().run_task(name,params=params)
            else:type(self).calls+=1
            raise TimeoutError('injected solver exception or lost response')
    Broken.calls=0;service.worker_factory=Broken
    execution=service.execute_simulation(payload,run_id='once',stop=StopIntent(),update=lambda **kw:None)
    with pytest.raises(TimeoutError):execution.run(payload)
    assert Broken.calls==1 and execution.recovery_required()
    with pytest.raises(ValueError,match='RUN_RECONCILIATION_REQUIRED'):
        service.execute_simulation(payload,run_id='once',stop=StopIntent(),update=lambda **kw:None).run(payload)
    assert Broken.calls==1 and not (tmp_path/'control/runs/once/simulation-result.json').exists()


def test_stop_timeout_keeps_unknown_safety_and_recovery_not_success(tmp_path):
    service,payload,_=make_service(tmp_path)
    class StopTimeout(FakeWorker):
        def stop(self):raise TimeoutError('stop deadline expired')
    StopTimeout.calls=0;service.worker_factory=StopTimeout
    execution=service.execute_simulation(payload,run_id='stop',stop=StopIntent(),update=lambda **kw:None)
    with pytest.raises(TimeoutError):execution.run(payload)
    assert StopTimeout.calls==1 and execution.session_safety()=='unknown' and execution.recovery_required()
    assert not (tmp_path/'control/runs/stop/simulation-result.json').exists()
