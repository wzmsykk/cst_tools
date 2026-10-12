import json
import threading
from pathlib import Path
import pytest

from csttool.diagnostics import write_run_manifest
from csttool.worker_models import WorkerConfig, SimulationResult
from csttool.diagnostics import archive_task
from csttool.diagnostics import write_failure_report
from csttool.diagnostics import collect_windows_events
from types import SimpleNamespace
from csttool.runtime_protocol import Task, new_session_id, encode_task


def test_manifest_excludes_callback_without_copying_owner(tmp_path):
    class Listener:
        def __init__(self):
            self.lock = threading.Lock()

        def progress(self, event):
            pass

    config = WorkerConfig(tmp_path, tmp_path, Path('cst.exe'), Path('model.cst'),
                          ({'name': 'R', 'value': '100'},),
                          progress_callback=Listener().progress)
    destination = write_run_manifest(tmp_path / 'diagnostics.json', config,
                                     {'completion': tmp_path / 'completion.txt'})
    document = json.loads(destination.read_text(encoding='utf-8'))
    assert document['schema_version'] == 1
    assert 'progress_callback' not in document['config']
    assert document['config']['parameters'][0]['name'] == 'R'
    assert len(document['source_sha256']['csttool/managed_cstworker.py']) == 64


def test_result_serialization_keeps_algorithm_contract(tmp_path):
    result = SimulationResult('1', 'Success', 'job', {'R': 100}, [],
                              snapshot=tmp_path / 'snapshot.cst')
    assert dict(result) == result.to_mapping()
    assert result['RunParameters'] == {'R': 100}
    assert result['ProjectSnapshot'] == str(tmp_path / 'snapshot.cst')


def test_typed_result_preserves_remote_archive_identity(tmp_path):
    result = SimulationResult('1', 'Success', 'job', {}, [],
                              snapshot=tmp_path / 'snapshot.cst',
                              task_id='task-123', result_directory=tmp_path)
    assert result['TaskID'] == 'task-123'
    assert result['ResultDirectory'] == str(tmp_path)
    assert len(result) == len(dict(result))


def test_manifest_keeps_original_project(tmp_path):
    source = tmp_path / 'original.cst'
    source.write_bytes(b'original project')
    config = WorkerConfig(tmp_path, tmp_path, Path('cst.exe'), source, ())
    manifest = write_run_manifest(tmp_path / 'session' / 'diagnostics.json', config, {})
    document = json.loads(manifest.read_text(encoding='utf-8'))
    backup = Path(document['source_project']['backup'])
    source.write_bytes(b'changed')
    assert backup.read_bytes() == b'original project'
    assert document['installation']['file_version'] is None
    with pytest.raises(FileExistsError):
        write_run_manifest(manifest, config, {})


def test_archive_retains_exact_expression_protocol_and_job(tmp_path):
    task = Task.create(new_session_id(), {'R': '100', 'L': '2 * R'},
                       expression_names=frozenset({'L'}))
    payload = archive_task(tmp_path, task, '../不是路径')
    destination = tmp_path / 'tasks' / task.task_id
    assert payload == encode_task(task)
    assert (destination / 'input.task').read_text(encoding='utf-8') == payload
    assert json.loads((destination / 'context.json').read_text(encoding='utf-8'))['job'] == '../不是路径'
    with pytest.raises(FileExistsError):
        archive_task(tmp_path, task, 'overwrite')


def test_failure_report_is_bounded_and_preserves_previous_reports(tmp_path):
    path = tmp_path / 'cst.log'
    path.write_bytes(b'x' * 20000)
    first = write_failure_report(tmp_path, phase='completion', paths={'log': path})
    second = write_failure_report(tmp_path, phase='ack', paths={'missing': tmp_path / 'absent'})
    report = json.loads(first.read_text(encoding='utf-8'))
    assert len(report['files']['log']['tail']) == 8192
    assert report['files']['log']['size'] == 20000
    assert report['process']['exit_code'] is None
    assert first != second and first.exists()


def test_failure_report_captures_original_exception(tmp_path):
    try:
        raise RuntimeError('original failure')
    except RuntimeError:
        path = write_failure_report(tmp_path, phase='startup')
    report = json.loads(path.read_text(encoding='utf-8'))
    assert report['error']['type'] == 'RuntimeError'
    assert report['error']['message'] == 'original failure'
    assert 'test_failure_report_captures_original_exception' in report['error']['traceback']


def test_windows_query_keeps_actual_stderr(monkeypatch):
    monkeypatch.setattr('csttool.diagnostics.subprocess.run', lambda *a, **kw:
                        SimpleNamespace(returncode=1, stdout='', stderr='拒绝访问'))
    report = collect_windows_events()
    assert report['status'] == 'unavailable'
    assert report['stderr'] == '拒绝访问'
    assert report['events'] == []


def test_windows_query_no_events_is_success(monkeypatch):
    monkeypatch.setattr('csttool.diagnostics.subprocess.run', lambda *a, **kw:
                        SimpleNamespace(returncode=0, stdout='{"status":"ok","events":[]}', stderr=''))
    assert collect_windows_events() == {'status': 'ok', 'events': []}
