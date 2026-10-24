from types import SimpleNamespace
from csttool.runner import Runner
import pytest
from pathlib import Path
from csttool.configuration import write_json_atomic, read_json
from csttool.result_reconciliation import recover_completed_result, file_hash
from csttool.runtime_protocol import new_session_id


def test_terminal_label_does_not_hide_undisposed_executor(tmp_path):
    runner = Runner(tmp_path)
    try:
        runner.status['state'] = 'IDLE'
        runner.executor = object()
        assert runner.snapshot()['execution_active'] is True
        runner.executor = None
        assert runner.snapshot()['execution_active'] is False
        runner.worker = SimpleNamespace(is_alive=lambda: True)
        assert runner.snapshot()['execution_active'] is True
        runner.worker = None
    finally:
        runner.close()


@pytest.mark.parametrize('fault', [None, 'hash', 'identity', 'ambiguous', 'missing-index'])
def test_archive_crash_rebinds_only_exact_index_and_original_hash(tmp_path, fault):
    sid, task_id = new_session_id(), new_session_id()
    root = tmp_path / 'session'
    original = tmp_path / 'results' / task_id
    renamed = original.parent / ('second__' + task_id)
    renamed.mkdir(parents=True)
    snapshot = renamed / 'second.cst'
    snapshot.write_bytes(b'confirmed snapshot')
    receipt_path = root / 'received' / (task_id + '.json')
    context = dict(task_id=task_id, session_id=sid, job='second', result_root=str(original),
                   receipt_path=str(receipt_path))
    write_json_atomic(root / 'task-context.json', context)
    receipt = dict(task_id=task_id, session_id=sid, status='Success', phase='acknowledged',
                   job='second', parameters={}, execution_fingerprint='fp', workspace=str(root),
                   snapshot=str(original / 'project.cst'), snapshot_sha256=file_hash(snapshot), postprocess=[])
    write_json_atomic(receipt_path, receipt)
    index = dict(schemaVersion=1, taskId=task_id, sessionId=sid, taskName='second',
                 projectSnapshot='second.cst', postprocess=[])
    if fault == 'identity': index['sessionId'] = new_session_id()
    if fault != 'missing-index': write_json_atomic(renamed / 'task_result.json', index)
    if fault == 'hash': snapshot.write_bytes(b'changed')
    if fault == 'ambiguous': write_json_atomic(original.parent / ('other__' + task_id) / 'task_result.json', index)
    before = receipt_path.read_bytes()
    if fault:
        with pytest.raises(ValueError): recover_completed_result(root)
        assert receipt_path.read_bytes() == before
    else:
        assert recover_completed_result(root) == receipt_path
        restored = read_json(receipt_path)
        assert Path(restored['snapshot']) == snapshot.resolve()
        assert restored['phase'] == 'acknowledged'
        after = receipt_path.read_bytes()
        recover_completed_result(root)
        assert receipt_path.read_bytes() == after
        # A cached old physical recovery decision still permits proven relocation.
        write_json_atomic(receipt_path, receipt)
        write_json_atomic(root / 'recovery.json', dict(disposition='abandoned-dead'))
        from csttool.result_reconciliation import find_received_result
        candidate = find_received_result([root], 'second', {}, 'fp')
        assert Path(candidate[1]['snapshot']) == snapshot.resolve()
