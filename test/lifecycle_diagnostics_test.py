from dataclasses import dataclass
from pathlib import Path
import pytest
from csttool.session_closure import CloseEvidence, evaluate_closure
from csttool.lifecycle_diagnostics import lifecycle_facts, error_diagnostic, result_observation
from csttool.configuration import write_json_atomic
from GUI.lifecycle_display import lifecycle_lines, runner_error_text


@dataclass
class Record:
    closure: object
    root: Path
    worker_id: str = '0'
    session_id: str = 's'


@pytest.mark.parametrize('alive,code,unresolved,safety,recovery', [
    (False, 0, True, 'confirmed-closed', True),
    (False, 1, False, 'exited-unverified', True),
    (True, None, False, 'running', True),
    (None, None, False, 'unknown', True),
    (False, 0, False, 'confirmed-closed', False),
])
def test_physical_exit_and_reconciliation_are_independent(tmp_path, alive, code, unresolved, safety, recovery):
    assessment = evaluate_closure(CloseEvidence('s', alive, code, stop_ack='valid',
        unresolved_completion=unresolved, task_outcome='failure', model_state='restored-saved'))
    facts = lifecycle_facts([Record(assessment, tmp_path)])
    assert facts['session_safety'] == safety
    assert facts['recovery_required'] is recovery
    assert facts['sessions'][0]['task_outcome'] == 'failure'
    assert facts['sessions'][0]['model_state'] == 'restored-saved'
    assert 'completion-not-reconciled' in facts['sessions'][0]['missing_evidence'] if unresolved else True
    text = '\n'.join(lifecycle_lines({'lifecycle': facts}))
    assert str(tmp_path) in text and '退出码' in text


def test_error_cause_and_source_survive_json_without_lifecycle():
    import json
    try:
        try:
            raise ValueError('wrong session')
        except ValueError as exc:
            raise RuntimeError('prepare failed') from exc
    except RuntimeError as exc:
        diagnostic = error_diagnostic(exc, 'prepare')
    status = json.loads(json.dumps(dict(error='prepare failed', error_diagnostic=diagnostic)))
    assert 'wrong session' in runner_error_text(status)
    assert 'lifecycle_diagnostics_test.py' in runner_error_text(status)
    assert any('ValueError' in line for line in lifecycle_lines(status))


@pytest.mark.parametrize('phase', ['received', 'acknowledged', 'algorithm_adopted'])
def test_result_receipt_observation_is_not_adoption(tmp_path, phase):
    path = tmp_path / 'receipt.json'
    write_json_atomic(tmp_path / 'task-context.json', dict(session_id='s', task_id='t', receipt_path=str(path)))
    write_json_atomic(path, dict(session_id='s', task_id='t', phase=phase, status='Success'))
    before = path.read_bytes()
    result = result_observation(tmp_path, 's')
    assert result['state'] == phase
    assert result['validation'] == 'receipt-observation-only'
    assert before == path.read_bytes()
    assert result_observation(tmp_path, 'other')['state'] == 'unknown'


def test_local_execution_does_not_use_recovery_list_as_process_safety(tmp_path, monkeypatch):
    from csttool.runner import LocalExecution
    import csttool.lifecycle_diagnostics as module
    execution = LocalExecution.__new__(LocalExecution)
    execution.project = tmp_path
    monkeypatch.setattr(module, 'project_lifecycle', lambda _: dict(session_safety='confirmed-closed', recovery_required=True))
    assert execution.session_safety() == 'confirmed-closed'


def test_runner_persists_final_facts_and_root_cause(tmp_path):
    from csttool.runner import Runner
    class Execution:
        def __init__(self, *args): pass
        def run(self, payload):
            try:
                raise ValueError('actual failure')
            except ValueError as exc:
                raise RuntimeError('wrapper') from exc
        def close(self): pass
        def recovery_required(self): return True
        def session_safety(self): return 'confirmed-closed'
        def lifecycle_facts(self): return dict(schema_version=1, session_safety='confirmed-closed', sessions=[])
    runner = Runner(tmp_path, Execution)
    from csttool.execution_contract import StopIntent
    runner.stop_intent = StopIntent()
    try:
        runner.update(coverage=dict(confirmed_frontier=900, calculated_upper=950), mode_count=12)
        runner._execute('start', {})
        status = runner.snapshot()
        assert status['state'] == 'RECOVERY_REQUIRED'
        assert status['session_safety'] == 'confirmed-closed'
        assert status['error_diagnostic']['chain'][-1]['message'] == 'actual failure'
        assert status['lifecycle']['schema_version'] == 1
        assert status['coverage'] == dict(confirmed_frontier=900, calculated_upper=950)
        assert status['mode_count'] == 12
    finally:
        runner.close()
    restarted = Runner(tmp_path, Execution)
    try:
        assert restarted.snapshot()['lifecycle']['historical'] is True
        assert restarted.snapshot()['error_diagnostic']['chain'][-1]['message'] == 'actual failure'
    finally:
        restarted.close()


def test_bounded_details_never_drop_a_bad_session_from_summary(tmp_path):
    good = evaluate_closure(CloseEvidence('s', False, 0, stop_ack='valid'))
    bad = evaluate_closure(CloseEvidence('s', None))
    records = [Record(good, tmp_path) for _ in range(105)] + [Record(bad, tmp_path)]
    facts = lifecycle_facts(records)
    assert facts['session_safety'] == 'unknown'
    assert facts['session_count'] == 106 and facts['omitted_sessions'] == 6
    assert len(facts['sessions']) == 100
    assert facts['sessions'][0]['process_state'] == 'unknown'


def test_runner_recovery_gate_never_has_an_empty_top_level_reason(tmp_path):
    from csttool.runner import Runner
    from csttool.execution_contract import StopIntent
    class Execution:
        def __init__(self, *args): pass
        def run(self, payload): pass
        def close(self): pass
        def recovery_required(self): return True
        def session_safety(self): return 'exited-unverified'
        def lifecycle_facts(self):
            return dict(session_safety='exited-unverified', recovery_required=True,
                        sessions=[dict(session_id='failed-session', needs_recovery=True,
                                       missing_evidence=['exit-code-not-accepted'])])
    runner = Runner(tmp_path, Execution)
    runner.stop_intent = StopIntent()
    try:
        runner._execute('start', {})
        status = runner.snapshot()
        assert status['state'] == 'RECOVERY_REQUIRED'
        assert 'exit-code-not-accepted' in status['error']
        assert status['recovery_reason'] == status['error']
    finally:
        runner.close()


@pytest.mark.parametrize('broken', [False, True])
def test_final_probe_cannot_clear_recovery_and_keeps_cleanup_separate(tmp_path, broken):
    from csttool.runner import Runner
    from csttool.execution_contract import StopIntent
    class Execution:
        def __init__(self, *args): pass
        def run(self, payload): raise ValueError('first failure')
        def close(self): raise RuntimeError('cleanup failed')
        def recovery_required(self): return False
        def lifecycle_facts(self):
            if broken:
                raise OSError('evidence unreadable')
            return dict(schema_version=1, session_safety='exited-unverified', recovery_required=True)
    runner = Runner(tmp_path, Execution)
    runner.stop_intent = StopIntent()
    try:
        runner._execute('start', {})
        status = runner.snapshot()
        assert status['state'] == 'RECOVERY_REQUIRED'
        assert status['error_diagnostic']['chain'][0]['message'] == 'first failure'
        assert status['cleanup_diagnostic']['chain'][0]['message'] == 'cleanup failed'
        assert status['session_safety'] == ('unknown' if broken else 'exited-unverified')
    finally:
        runner.close()
