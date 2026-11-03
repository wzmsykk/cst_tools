"""G03/G04/G08 + N24/N25 durable fake-peer faults; never launches CST.

Fresh service objects model loss of controller memory, not OS process death.
"""
from pathlib import Path
import pytest

from csttool.application_service import ApplicationService
from csttool.configuration import read_json, write_json_atomic
from csttool.execution_contract import StopIntent
from test.single_simulation_service_test import make_service, FakeWorker, reset_fake


def fresh(app):
    def forbidden(*args, **kwargs):
        raise AssertionError('reconciliation must not create a worker')
    return ApplicationService(app.project, app.project_id, installations=app.installations,
                              worker_factory=forbidden)


def execute(app, payload):
    return app.execute_simulation(payload, run_id='matrix', stop=StopIntent(), update=lambda **kw: None)


@pytest.mark.parametrize('phase', ['received', 'completion-written', 'ack-published', 'wrong-session'])
def test_ack_not_confirmed_never_publishes_or_redispatches(tmp_path, phase):
    app, payload, _ = make_service(tmp_path)
    class AckGap(FakeWorker):
        def run_task(self, name, *, params):
            result = super().run_task(name, params=params)
            receipt = read_json(result.receipt_path)
            if phase == 'wrong-session': receipt['session_id'] = 'foreign'
            else: receipt['phase'] = phase
            write_json_atomic(result.receipt_path, receipt)
            return result
    AckGap.calls = 0; app.worker_factory = AckGap
    with pytest.raises(ValueError, match='RESULT_INVALID'): execute(app, payload).run(payload)
    assert AckGap.calls == 1
    assert not (tmp_path/'control/runs/matrix/simulation-result.json').exists()
    restarted = fresh(app)
    with pytest.raises((ValueError, OSError)): restarted.reconcile_simulation('matrix')
    with pytest.raises(ValueError, match='RUN_RECONCILIATION_REQUIRED'): execute(restarted, payload).run(payload)
    assert AckGap.calls == 1


@pytest.mark.parametrize('boundary', ['simulation-received.json', 'simulation-closure.json',
                                     'simulation-result.json'])
def test_controller_write_gap_repeated_recovery_has_no_new_solver(tmp_path, monkeypatch, boundary):
    import csttool.application_service as module
    app, payload, _ = make_service(tmp_path)
    original = module.write_json_atomic
    def fail(path, value):
        if Path(path).name == boundary: raise OSError('injected durable write gap')
        return original(path, value)
    monkeypatch.setattr(module, 'write_json_atomic', fail)
    with pytest.raises(OSError): execute(app, payload).run(payload)
    monkeypatch.setattr(module, 'write_json_atomic', original)
    restarted = fresh(app)
    if boundary == 'simulation-result.json':
        first = restarted.reconcile_simulation('matrix')
        journal = (tmp_path/'control/runs/matrix/events.jsonl').read_bytes()
        assert fresh(app).reconcile_simulation('matrix') == first
        assert (tmp_path/'control/runs/matrix/events.jsonl').read_bytes() == journal
    else:
        for _ in range(2):
            with pytest.raises((ValueError, OSError)): restarted.reconcile_simulation('matrix')
        assert not (tmp_path/'control/runs/matrix/simulation-result.json').exists()
    assert FakeWorker.calls == 1


@pytest.mark.parametrize('fault', ['receipt-missing', 'snapshot-missing', 'db-missing', 'db-changed',
                                  'nonce', 'project', 'definition', 'unclosed', 'unacked'])
def test_archived_capture_gap_cannot_adopt_after_restart(tmp_path, monkeypatch, fault):
    import csttool.application_service as module
    app, payload, _ = make_service(tmp_path)
    original = module.write_json_atomic
    def fail(path, value):
        if Path(path).name == 'simulation-result.json': raise OSError('publication gap')
        return original(path, value)
    monkeypatch.setattr(module, 'write_json_atomic', fail)
    with pytest.raises(OSError): execute(app, payload).run(payload)
    monkeypatch.setattr(module, 'write_json_atomic', original)
    run = tmp_path/'control/runs/matrix'; received = read_json(run/'simulation-received.json')
    task = run/'tasks'/received['task_id']; native = task/'execution'
    if fault in ('receipt-missing', 'snapshot-missing', 'db-missing'):
        (native/{'receipt-missing':'receipt.json', 'snapshot-missing':'snapshot.json',
                 'db-missing':'native-Model.db'}[fault]).unlink()
    elif fault == 'db-changed': (native/'native-Model.db').write_bytes(b'foreign database')
    else:
        path = run/'simulation-closure.json' if fault == 'unclosed' else task/'attempt.json' if fault == 'unacked' else native/'receipt.json'
        value = read_json(path)
        if fault == 'unclosed': value['standard_closed'] = False
        elif fault == 'unacked': value['event'] = 'received'
        elif fault == 'nonce': value['nonce'] = 'foreign'
        elif fault == 'project': value['binding']['project_id'] = 'foreign'
        elif fault == 'definition': value['binding']['definition_revision'] = '0'*64
        write_json_atomic(path, value)
    before = (run/'events.jsonl').read_bytes()
    for _ in range(2):
        with pytest.raises((ValueError, OSError)): fresh(app).reconcile_simulation('matrix')
    assert not (run/'simulation-result.json').exists()
    assert (run/'events.jsonl').read_bytes() == before
    assert FakeWorker.calls == 1


@pytest.mark.parametrize('outcome', ['solver-failed', 'missing-mode', 'missing-rq'])
def test_failed_or_incomplete_result_is_not_success(tmp_path, outcome):
    from dataclasses import replace
    app, payload, _ = make_service(tmp_path)
    class Failed(FakeWorker):
        def run_task(self, name, *, params):
            result = super().run_task(name, params=params)
            if outcome == 'solver-failed': result = replace(result, status='Failure')
            else: result = replace(result, postprocess=result.postprocess[1:] if outcome == 'missing-mode' else result.postprocess[:1])
            receipt = read_json(result.receipt_path)
            receipt.update(status=result.status, postprocess=result.postprocess)
            write_json_atomic(result.receipt_path, receipt)
            return result
    Failed.calls = 0; app.worker_factory = Failed
    with pytest.raises((ValueError, KeyError)): execute(app, payload).run(payload)
    assert Failed.calls == 1 and not (tmp_path/'control/runs/matrix/simulation-result.json').exists()


@pytest.mark.parametrize('code',['SOLVER_FAILED','REBUILD_FAILED','INVALID_TASK','RESULT_FLUSH_FAILED','INTERNAL_ERROR','UNKNOWN'])
def test_original_solver_failure_survives_missing_post_capture(tmp_path,code):
    from dataclasses import replace
    app, payload, _ = make_service(tmp_path)
    class MissingPost(FakeWorker):
        def run_task(self, name, *, params):
            result=super().run_task(name, params=params)
            result=replace(result,status='Failure',failure=code+': original native failure')
            receipt=read_json(result.receipt_path);receipt.update(status='Failure',failure=result.failure)
            write_json_atomic(result.receipt_path,receipt)
            return result
        def finalize_execution_capture(self):raise FileNotFoundError('native-post.tsv missing')
    app.worker_factory=MissingPost
    with pytest.raises(ValueError,match=code+': original native failure') as error:
        execute(app,payload).run(payload)
    assert error.value.code == ('TASK_FAILED' if code=='UNKNOWN' else code)
