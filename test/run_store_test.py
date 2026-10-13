import json
from csttool.run_store import RunStore


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
