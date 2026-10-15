import json
import threading
from pathlib import Path
import pytest
from csttool.configuration import read_json, write_json_atomic, open_shared_read
from csttool.execution_contract import StopIntent
from csttool.hom_scan import ScanInterrupted
from csttool.result_reconciliation import recover_completed_result
from csttool.runtime_protocol import Completion, CompletionStatus, encode_completion, new_session_id, Task
from test.application_backend_test import make_backend
from test.cstmanager_test import FakeProjectConfig, FakeGlobalConfig
from csttool.cstmanager import CSTManager


@pytest.mark.parametrize('when', ['before-prepare', 'during-preprocess'])
def test_stop_before_manager_registration_never_starts_pool(tmp_path, monkeypatch, when):
    backend, _, project, _, calls = make_backend()
    backend.select_project_directory(str(tmp_path))
    backend.initialize_run(False, 1)
    if when == 'before-prepare':
        backend.request_stop()
    else:
        original = project.prepare_project
        def prepare(*args, **kwargs):
            original(*args, **kwargs)
            backend.request_stop()
        monkeypatch.setattr(project, 'prepare_project', prepare)
    with pytest.raises(ScanInterrupted):
        backend.prepare_run()
    assert not calls
    assert backend.jm is None


def test_stop_during_worker_creation_prevents_next_worker(tmp_path):
    token = StopIntent()
    made = []
    class Worker:
        def __init__(self):
            self.stopped = False
        def request_stop(self):
            token.request()
        def stop(self):
            self.stopped = True
    def create(*args):
        worker = Worker()
        made.append(worker)
        token.request()  # Emulate stop received during a blocking constructor.
        return worker
    manager = CSTManager(FakeGlobalConfig(tmp_path), FakeProjectConfig(tmp_path), [],
                         worker_factory=create, maxTask=3, stop_check=token.is_set)
    manager.stop()
    assert len(made) == 1 and made[0].stopped


@pytest.mark.parametrize('missing', [False, True])
def test_completion_without_python_receipt_is_verified_before_recovery(tmp_path, monkeypatch, missing):
    task = Task.create(new_session_id(), {})
    root = tmp_path / 'session'
    results = tmp_path / 'results'
    results.mkdir()
    if not missing:
        (results / 'project.cst').write_bytes(b'synthetic snapshot, not CST acceptance')
    write_json_atomic(root / 'task-context.json', {
        'task_id': task.task_id, 'session_id': task.session_id, 'result_root': str(results),
        'job': 'hom_empty', 'parameters': {}, 'postprocess': [], 'execution_fingerprint': 'expected'})
    path = root / 'protocol/current.completion'
    path.parent.mkdir()
    path.write_text(encode_completion(Completion(task.task_id, task.session_id, CompletionStatus.SUCCESS)))
    monkeypatch.setattr('csttool.postprocess_cst.CstPostProcessor.read_all_results', lambda self: [])
    if missing:
        with pytest.raises(ValueError, match='no usable'):
            recover_completed_result(root)
        assert not (root / 'received').exists()
    else:
        receipt = recover_completed_result(root)
        assert read_json(receipt)['postprocess'] == []
        assert read_json(receipt)['recovered_from_completion']
        assert recover_completed_result(root) == receipt
    assert path.exists(), 'Import must not ACK/delete completion before validating results'


def test_shared_reader_does_not_block_atomic_checkpoint_replacement(tmp_path):
    target = tmp_path / 'status.json'
    write_json_atomic(target, {'version': 1})
    with open_shared_read(target) as old:
        write_json_atomic(target, {'version': 2})
        assert json.load(old)['version'] == 1
    assert read_json(target)['version'] == 2


def test_vba_unicode_paths_remain_ascii_source():
    from csttool.vb_codec import quote_vb_string
    result = quote_vb_string('D:/后台/"x"/😀')
    assert result.isascii()
    assert 'ChrW(21518)' in result and 'ChrW(-10179)' in result
    assert '""x""' in result


def test_corrupt_project_ownership_is_not_reclaimed_by_age(tmp_path):
    import os
    from csttool.project_run_lock import ProjectRunLock, ProjectRunBusyError
    lease = ProjectRunLock(tmp_path)
    lease.path.parent.mkdir(parents=True, exist_ok=True)
    lease.path.write_text('corrupt ownership')
    os.utime(lease.path, (1, 1))
    assert ProjectRunLock.active_owner(tmp_path).token == 'unknown'
    with pytest.raises(ProjectRunBusyError):
        lease.acquire()
    assert lease.path.read_text() == 'corrupt ownership'


@pytest.mark.parametrize('failures', [2, 5])
def test_atomic_publish_retries_are_bounded_and_do_not_erase_old_data(tmp_path, monkeypatch, failures):
    import os
    from csttool.configuration import replace_file_atomic
    if os.name != 'nt':
        pytest.skip('Windows sharing errors')
    source, destination = tmp_path / 'source', tmp_path / 'destination'
    source.write_text('new')
    destination.write_text('old')
    actual = os.replace
    calls = []
    def replace(*args):
        calls.append(args)
        if len(calls) <= failures:
            error = PermissionError('injected sharing conflict')
            error.winerror = 32
            raise error
        return actual(*args)
    monkeypatch.setattr(os, 'replace', replace)
    if failures == 5:
        with pytest.raises(PermissionError):
            replace_file_atomic(source, destination)
        assert destination.read_text() == 'old' and source.read_text() == 'new'
        assert len(calls) == 5
    else:
        replace_file_atomic(source, destination)
        assert destination.read_text() == 'new'
        assert len(calls) == 3
