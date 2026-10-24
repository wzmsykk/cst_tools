"""Acceptance probe checks; synthetic records do not establish CST behavior."""
from pathlib import Path
import pytest
from csttool.configuration import write_json_atomic
from test.support.validate_hom_exit_l5 import adoption, evidence
from csttool.result_reconciliation import file_hash


def test_independent_solve_comparison_only_tolerates_roundoff_not_extra_tasks():
    from test.support.validate_hom_exit_l5 import equivalent_numbers
    assert equivalent_numbers([{'fmax': 738.745670980914}], [{'fmax': 738.745670980913}])
    assert not equivalent_numbers([{'fmax': 738.7}], [{'fmax': 739.7}])
    assert not equivalent_numbers([{'fmax': 530}, {'fmax': 530}], [{'fmax': 530}])


def test_hom_evidence_binds_project_relative_snapshot_and_native_fields(tmp_path, monkeypatch):
    snapshot = tmp_path / 'result/mode.cst'
    snapshot.parent.mkdir()
    snapshot.write_bytes(b'confirmed')
    field = snapshot.with_suffix('') / 'Result/e.m3t'
    field.parent.mkdir(parents=True)
    field.write_bytes(b'field')
    monkeypatch.chdir(tmp_path.parent)
    result = evidence(tmp_path, {'report': {'modes': [{'project_snapshot': 'result/mode.cst'}]}})
    assert result == {str(snapshot): file_hash(snapshot), str(field): file_hash(field)}


@pytest.mark.parametrize('count', [0, 1, 2])
def test_probe_rejects_missing_or_duplicate_adoption_events(tmp_path, count):
    import json
    task = 'task'
    run = tmp_path / 'logs/run'
    write_json_atomic(run / 'workers/0/session/received/task.json', {'phase': 'algorithm_adopted'})
    write_json_atomic(run / 'tasks/task/attempt.json', {'event': 'algorithm_adopted'})
    (run / 'events.jsonl').write_text(''.join(json.dumps(dict(task_id=task, event='algorithm_adopted')) + '\n' for _ in range(count)))
    if count == 1:
        assert adoption(tmp_path, [task]) == {'task': [1]}
    else:
        with pytest.raises(AssertionError): adoption(tmp_path, [task])
