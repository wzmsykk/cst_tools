"""Persisted project/Backend/Runner recovery reconciliation; no CST execution."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest

from csttool.application_backend import BackendState, BackendPreparationError
from csttool.configuration import GlobalSettings, ProjectSettings, read_ini, write_ini_atomic, write_json_atomic
from csttool.hom_scan import ModeResult, ScanCheckpointStore, ScanInterval, ScanPolicy, ScanReport
from csttool.projectconfmanager import ProjectConfigManager
from csttool.project_recovery_state import persisted_project_status
from csttool.project_run_lock import ProjectRunLock
from csttool.runner import Runner, LocalExecution
from test.application_backend_test import make_backend
from test.runner_test import command


def real_project_backend(project, status='RECOVERY_REQUIRED'):
    project = Path(project)
    project.mkdir(parents=True, exist_ok=True)
    source = project / 'processed.cst'
    source.write_bytes(b'original prepared snapshot')
    (project / 'params.json').write_text('[]', encoding='utf-8')
    (project / 'pps.json').write_text('[]', encoding='utf-8')
    manager = ProjectConfigManager(SimpleNamespace(settings=GlobalSettings()))
    manager.select_project_directory(project)
    settings = ProjectSettings(name='261012', cst_filename=Path('processed.cst'),
        cells_per_wavelength=4, project_digest=manager.file_digest(source), task_status=status)
    write_ini_atomic(project / 'project.ini', settings.to_parser())
    backend, _, _, _, calls = make_backend()
    backend.pconfman = manager
    return backend, manager, calls


@pytest.mark.parametrize('status', ['RECOVERY_REQUIRED', 'RUNNING', 'STOP_REQUESTED'])
def test_prepare_keeps_persisted_recovery_gate_not_generic_failure(tmp_path, status):
    backend, manager, calls = real_project_backend(tmp_path, status)
    backend.initialize_run(True, 1)
    with pytest.raises(BackendPreparationError, match='显式恢复'):
        backend.prepare_run()
    assert backend.state is BackendState.RECOVERY_REQUIRED
    assert backend.is_recovery_required()
    assert persisted_project_status(tmp_path) == status
    assert not calls
    assert ProjectRunLock.active_owner(tmp_path) is None


def test_fresh_recovery_loads_config_and_writes_under_lock(tmp_path, monkeypatch):
    backend, manager, _ = real_project_backend(tmp_path)
    assert manager.settings is None
    original = manager.update_task_status
    def update(status):
        assert ProjectRunLock.active_owner(tmp_path) is not None
        return original(status)
    monkeypatch.setattr(manager, 'update_task_status', update)
    assert backend.recover_project_sessions() == []
    assert backend.state is BackendState.INTERRUPTED
    assert not backend.is_recovery_required()
    assert persisted_project_status(tmp_path) == 'INTERRUPTED'
    settings = ProjectSettings.from_parser(read_ini(tmp_path / 'project.ini'))
    assert settings.cells_per_wavelength == 4
    assert settings.cst_filename == Path('processed.cst')
    assert ProjectRunLock.active_owner(tmp_path) is None


def test_recovery_write_failure_stays_recoverable_and_can_retry(tmp_path, monkeypatch):
    backend, manager, _ = real_project_backend(tmp_path)
    original = manager.update_task_status
    def denied(status):
        raise PermissionError('injected project status write failure')
    monkeypatch.setattr(manager, 'update_task_status', denied)
    with pytest.raises(PermissionError):
        backend.recover_project_sessions()
    assert backend.state is BackendState.RECOVERY_REQUIRED
    assert persisted_project_status(tmp_path) == 'RECOVERY_REQUIRED'
    assert ProjectRunLock.active_owner(tmp_path) is None
    monkeypatch.setattr(manager, 'update_task_status', original)
    backend.recover_project_sessions()
    assert persisted_project_status(tmp_path) == 'INTERRUPTED'


def checkpoint(project):
    policy = ScanPolicy(700, 800, 2500)
    modes = [ModeResult(1, 701 + i, {'frequency': 701 + i}) for i in range(188)]
    report = ScanReport(modes=modes, completed=[ScanInterval(700, 1165.8231853449101),
        ScanInterval(1170, 1215.17243800861)])
    path = project / 'save/csv/hom_scan_checkpoint.json'
    ScanCheckpointStore(path).save(policy, {'fixture': 'recovery-state'}, report,
        [ScanInterval(1165.8231853449101, 1170)], project / 'processed.cst')
    return path


def test_recovery_verifies_snapshot_preserves_188_modes_pending_and_coverage(tmp_path):
    backend, _, _ = real_project_backend(tmp_path)
    path = checkpoint(tmp_path)
    before = path.read_bytes()
    model = (tmp_path / 'processed.cst').read_bytes()
    backend.recover_project_sessions()
    assert path.read_bytes() == before
    assert (tmp_path / 'processed.cst').read_bytes() == model
    assert persisted_project_status(tmp_path) == 'INTERRUPTED'


def test_broken_snapshot_does_not_clear_recovery_gate(tmp_path):
    backend, _, _ = real_project_backend(tmp_path)
    checkpoint(tmp_path)
    (tmp_path / 'processed.cst').write_bytes(b'changed externally')
    with pytest.raises(ValueError, match='snapshot'):
        backend.recover_project_sessions()
    assert persisted_project_status(tmp_path) == 'RECOVERY_REQUIRED'
    assert backend.state is BackendState.RECOVERY_REQUIRED


def test_runner_startup_repairs_user_failed_status_without_changing_project(tmp_path):
    real_project_backend(tmp_path)
    write_json_atomic(tmp_path / 'control/status.json', dict(state='FAILED', run_id='previous',
        session_safety='confirmed-closed', error='BackendPreparationError: 运行配置准备失败'))
    runner = Runner(tmp_path)
    try:
        status = runner.snapshot()
        assert status['state'] == 'RECOVERY_REQUIRED'
        assert status['phase'] == 'recovery-required'
        assert status['session_safety'] == 'confirmed-closed'
        assert status['project_task_status'] == 'RECOVERY_REQUIRED'
        runner.command(command('claim'))
        with pytest.raises(ValueError, match='recover'):
            runner.command(command('start', {'resume': True}))
        assert runner.worker is None
        assert persisted_project_status(tmp_path) == 'RECOVERY_REQUIRED'
    finally:
        runner.close()


def test_live_runner_notices_persisted_gate_without_restart(tmp_path):
    _, manager, _ = real_project_backend(tmp_path, 'READY')
    runner = Runner(tmp_path)
    try:
        assert runner.snapshot()['state'] == 'IDLE'
        settings = ProjectSettings.from_parser(read_ini(tmp_path / 'project.ini'))
        write_ini_atomic(tmp_path / 'project.ini', replace(settings, task_status='RECOVERY_REQUIRED').to_parser())
        assert runner.snapshot()['state'] == 'RECOVERY_REQUIRED'
    finally:
        runner.close()


def test_explicit_recover_then_resume_does_not_repeat_the_gate(tmp_path):
    real_project_backend(tmp_path)
    calls = []
    class Execution:
        def __init__(self, project, stop, run_id, update):
            self.backend, _, _ = real_project_backend(project, persisted_project_status(project))
        def recover(self):
            self.backend.recover_project_sessions()
        def run(self, payload):
            assert payload['resume'] is True
            assert persisted_project_status(tmp_path) == 'INTERRUPTED'
            calls.append('resumed')
        def recovery_required(self):
            return self.backend.is_recovery_required()
        def close(self):
            pass
    runner = Runner(tmp_path, Execution)
    try:
        runner.command(command('claim'))
        runner.command(command('recover'))
        runner.worker.join(5)
        assert runner.snapshot()['state'] == 'IDLE'
        assert persisted_project_status(tmp_path) == 'INTERRUPTED'
        runner.command(command('start', {'resume': True}))
        runner.worker.join(5)
        assert runner.snapshot()['state'] == 'COMPLETED'
        assert calls == ['resumed']
    finally:
        runner.close()


def test_preprocessing_process_blocks_recovery_before_project_status_changes(tmp_path, monkeypatch):
    backend, _, _ = real_project_backend(tmp_path)
    execution = object.__new__(LocalExecution)
    execution.project, execution.backend = tmp_path, backend
    monkeypatch.setattr(execution, '_preprocessor_recovery_required', lambda: True)
    with pytest.raises(RuntimeError, match='预处理'):
        execution.recover()
    assert persisted_project_status(tmp_path) == 'RECOVERY_REQUIRED'


def test_missing_preparation_config_can_reconcile_without_creating_one(tmp_path):
    backend, manager, _ = real_project_backend(tmp_path)
    (tmp_path / 'project.ini').unlink()
    backend.recover_project_sessions()
    assert backend.state is BackendState.INTERRUPTED
    assert not (tmp_path / 'project.ini').exists()


def test_unreadable_configuration_blocks_runner_and_recovery(tmp_path):
    backend, _, _ = real_project_backend(tmp_path)
    path = tmp_path / 'project.ini'
    path.write_text('not an ini document', encoding='utf-8')
    original = path.read_bytes()
    runner = Runner(tmp_path)
    try:
        assert runner.snapshot()['state'] == 'RECOVERY_REQUIRED'
        assert runner.snapshot()['project_task_status'] == 'UNREADABLE'
        with pytest.raises(Exception):
            backend.recover_project_sessions()
        assert backend.state is BackendState.RECOVERY_REQUIRED
        assert path.read_bytes() == original
    finally:
        runner.close()
