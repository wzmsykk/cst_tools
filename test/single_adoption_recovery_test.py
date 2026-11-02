"""Result publication and protocol adoption are separate durable facts."""
import pytest
from csttool.application_service import SimulationRecoveryExecution,ServiceError
from csttool.configuration import read_json,write_json_atomic
from csttool.execution_contract import StopIntent
from test.single_simulation_service_test import make_service,FakeWorker,reset_fake


def test_published_result_receipt_gap_repairs_without_recompute_or_revision_change(tmp_path,monkeypatch):
    import csttool.checkpoint_adoption as module
    app,payload,_=make_service(tmp_path)
    original=module.write_json_atomic
    def fail(path,value):
        if path.name=='received.json' and value.get('phase')=='algorithm_adopted':raise OSError('receipt adoption gap')
        return original(path,value)
    monkeypatch.setattr(module,'write_json_atomic',fail)
    with pytest.raises(OSError,match='receipt adoption gap'):
        app.execute_simulation(payload,run_id='gap',stop=StopIntent(),update=lambda **kw:None).run(payload)
    result=app.get_simulation_results('gap')
    directory=tmp_path/'control/runs/gap'
    before=(directory/'events.jsonl').read_bytes()
    monkeypatch.setattr(module,'write_json_atomic',original)
    repaired=app.reconcile_simulation('gap')
    assert repaired==result and app.reconcile_simulation('gap')==result
    assert (directory/'events.jsonl').read_bytes()==before
    assert FakeWorker.calls==1
    refs=read_json(directory/'tasks'/result['task_id']/'artifacts.json')
    assert read_json(tmp_path/refs['received']['path'])['phase']=='algorithm_adopted'


def test_existing_result_does_not_authorize_a_different_protocol_receipt(tmp_path):
    app,payload,_=make_service(tmp_path)
    app.execute_simulation(payload,run_id='one',stop=StopIntent(),update=lambda **kw:None).run(payload)
    result=app.get_simulation_results('one')
    refs=read_json(tmp_path/'control/runs/one/tasks'/result['task_id']/'artifacts.json')
    path=tmp_path/refs['received']['path'];receipt=read_json(path)
    receipt.update(phase='acknowledged',session_id='wrong')
    write_json_atomic(path,receipt)
    with pytest.raises(ServiceError,match='RESULT_INVALID'):app.reconcile_simulation('one')
    assert read_json(path)['phase']=='acknowledged'
