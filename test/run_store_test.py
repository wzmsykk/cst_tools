import json
from csttool.run_store import RunStore
from csttool.run_store import logical_job_id
import pytest


def test_run_index_updates_state_and_preserves_events_and_relative_paths(tmp_path):
    store = RunStore(tmp_path, tmp_path / 'logs' / 'run')
    store.event('task', 'submitted', job='mode')
    store.event('task', 'received')
    store.artifacts('task', snapshot=tmp_path / 'result' / 'model.cst')
    assert len((store.directory / 'events.jsonl').read_text().splitlines()) == 2
    assert json.loads((store.directory / 'tasks/task/attempt.json').read_text())['job'] == 'mode'
    artifact = json.loads((store.directory / 'tasks/task/artifacts.json').read_text())['snapshot']
    assert artifact['relative_to'] == 'project'
    assert not artifact['exists_at_registration']


def test_job_identity_is_stable_but_changes_with_parameters_or_definition():
    assert logical_job_id('job', {'a': 1, 'b': 2}, 'model') == logical_job_id('job', {'b': 2, 'a': 1}, 'model')
    assert logical_job_id('job', {'a': 1}, 'model') != logical_job_id('job', {'a': 2}, 'model')


def test_invalid_state_transition_is_rejected(tmp_path):
    store = RunStore(tmp_path, tmp_path / 'logs/run')
    store.event('task', 'submitted')
    with pytest.raises(ValueError):
        store.event('task', 'algorithm_adopted')
