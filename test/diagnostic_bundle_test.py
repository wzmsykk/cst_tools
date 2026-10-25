import json
from pathlib import Path
import zipfile

import pytest

from csttool.diagnostic_bundle import export_failure_bundle


def project_files(root):
    run = root / 'logs/current'
    observation = run / 'workers/0/session-a'
    worker = root / 'temp/worker_0/session-a'
    for path, content in {
        root / 'control/status.json': json.dumps({'state': 'FAILED', 'run_id': 'run-a',
            'log_directory': str(run), 'error': 'solver failed'}),
        root / 'control/endpoint.json': 'SECRET_RUNNER_TOKEN',
        run / 'application.jsonl': '{"task":"task-a","error":"failed"}\n',
        observation / 'diagnostics.json': '{"session":"session-a"}',
        observation / 'lifecycle.log': 'restore-batch returned\n',
        observation / 'failures/task-a.json': '{"error":"REBUILD_FAILED"}',
        worker / 'protocol/close.receipt': 'CST_CLOSE_RECEIPT_V2\n',
        worker / 'worker-input/Result/output.txt': 'maximal number of iterations\n',
        worker / 'worker-input/Result/progress.log': 'Progress:int:100\n',
        worker / 'worker-input.cst': 'MODEL_PAYLOAD',
        worker / 'worker-input/Result/e-field.m3t': 'LARGE_FIELD_PAYLOAD',
        root / 'logs/old/application.log': 'UNRELATED_OLD_RUN',
    }.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return run, worker


def read_bundle(result):
    with zipfile.ZipFile(result['path']) as archive:
        assert archive.testzip() is None
        return json.loads(archive.read('manifest.json')), {n: archive.read(n) for n in archive.namelist()}


def test_bundle_links_current_run_native_failure_and_protocol_without_tokens_or_models(tmp_path):
    project_files(tmp_path)
    manifest, files = read_bundle(export_failure_bundle(tmp_path))
    assert manifest['run_id'] == 'run-a'
    assert files['files/temp/worker_0/session-a/worker-input/Result/output.txt'].startswith(b'maximal')
    assert 'files/temp/worker_0/session-a/protocol/close.receipt' in files
    assert 'files/logs/current/workers/0/session-a/failures/task-a.json' in files
    assert 'files/logs/current/application.jsonl' in files
    assert not any(n.endswith(('.cst', '.m3t', 'endpoint.json')) for n in files)
    assert not any('UNRELATED_OLD_RUN' in v.decode(errors='replace') for v in files.values())
    assert any(f['status'] == 'unavailable' for f in manifest['files'])
    assert (tmp_path / 'control/endpoint.json').read_text() == 'SECRET_RUNNER_TOKEN'


def test_bounded_tails_and_total_budget_are_explicit(tmp_path):
    run, _ = project_files(tmp_path)
    (run / 'application.log').write_bytes(b'x' * 500 + b'TAIL')
    manifest, files = read_bundle(export_failure_bundle(tmp_path, file_limit=80, total_limit=200))
    records = manifest['files']
    assert manifest['captured_bytes'] <= 200
    assert all(f.get('captured_bytes', 0) <= 80 for f in records)
    assert any(f.get('truncated') for f in records)
    assert any(f['status'] == 'omitted-budget' for f in records)


def test_offline_no_status_uses_newest_run_and_marks_fallback(tmp_path):
    run, _ = project_files(tmp_path)
    (tmp_path / 'control/status.json').unlink()
    # Filename ordering is the documented fallback for run folders.
    newer = tmp_path / 'logs/zz-new'
    newer.mkdir()
    (newer / 'application.log').write_text('latest run')
    manifest, files = read_bundle(export_failure_bundle(tmp_path))
    assert manifest['runs'] == [str(newer)]
    assert manifest['warnings']
    assert files['files/logs/zz-new/application.log'] == b'latest run'


def test_untrusted_external_log_pointer_is_not_read(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + '-private')
    outside.mkdir()
    (outside / 'private.log').write_text('PRIVATE')
    (tmp_path / 'control').mkdir()
    (tmp_path / 'control/status.json').write_text(json.dumps({'log_directory': str(outside)}))
    manifest, files = read_bundle(export_failure_bundle(tmp_path))
    assert any('outside logs' in w for w in manifest['warnings'])
    assert not any(n.endswith('private.log') for n in files)


def test_custom_temp_and_preprocess_outputs(tmp_path):
    (tmp_path / 'project.ini').write_text('[paths]\ntemp_dir=work-temp\n')
    probe = tmp_path / 'work-temp/cst-preprocess-a'
    probe.mkdir(parents=True)
    (probe / 'output.txt').write_text('preprocess error')
    (probe / 'stage.txt').write_text('rebuild')
    manifest, files = read_bundle(export_failure_bundle(tmp_path))
    assert files['files/work-temp/cst-preprocess-a/output.txt'] == b'preprocess error'


def test_collision_preserves_existing_archive_and_removes_temporary_file(tmp_path, monkeypatch):
    from datetime import datetime
    import csttool.diagnostic_bundle as module
    fixed = datetime(2026, 10, 25, 12, 0).astimezone()
    class Clock:
        @staticmethod
        def now():
            return fixed
    monkeypatch.setattr(module, 'datetime', Clock)
    first = export_failure_bundle(tmp_path)
    before = Path(first['path']).read_bytes()
    with pytest.raises(FileExistsError):
        export_failure_bundle(tmp_path)
    assert Path(first['path']).read_bytes() == before
    assert not list((tmp_path / 'diagnostics').glob('*.tmp'))


def test_discovery_file_limit_is_reported(tmp_path):
    project_files(tmp_path)
    manifest, _ = read_bundle(export_failure_bundle(tmp_path, max_files=3))
    assert len(manifest['files']) <= 3
    assert 'file-count-limit' in manifest['warnings']


def test_correlated_previous_run_and_external_temp_exclusion(tmp_path):
    run, _ = project_files(tmp_path)
    status = json.loads((tmp_path / 'control/status.json').read_text())
    status['log_history'] = [{'directory': str(tmp_path / 'logs/old')}]
    (tmp_path / 'control/status.json').write_text(json.dumps(status))
    (tmp_path / 'project.ini').write_text('[paths]\ntemp_dir=../external-temp\n')
    manifest, files = read_bundle(export_failure_bundle(tmp_path))
    assert 'files/logs/old/application.log' in files
    assert 'configured temp outside project; excluded' in manifest['warnings']


def test_large_log_reads_only_a_bounded_tail(tmp_path):
    run, _ = project_files(tmp_path)
    log = run / 'large.log'
    with log.open('wb') as stream:
        stream.seek(16 * 1024**2 - 4)
        stream.write(b'TAIL')
    manifest, files = read_bundle(export_failure_bundle(tmp_path))
    record = next(f for f in manifest['files'] if f['source'] == str(log))
    assert record['original_bytes'] == 16 * 1024**2
    assert record['captured_bytes'] == 4 * 1024**2
    assert record['truncated']
    assert files[record['archive']].endswith(b'TAIL')
