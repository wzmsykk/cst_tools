from pathlib import Path
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.worker_models import WorkerConfig


def test_observation_files_are_separate_from_live_protocol(tmp_path, monkeypatch):
    project = tmp_path / 'input.cst'
    project.write_bytes(b'fixture')
    monkeypatch.setattr(ManagedCSTWorker, '_start', lambda self: None)
    run = tmp_path / 'logs' / 'run'
    worker = ManagedCSTWorker('0', WorkerConfig(tmp_path / 'temp', tmp_path / 'result',
        Path('CST.exe'), project, (), run_directory=run, project_directory=tmp_path))
    assert worker.protocol.root.is_relative_to(tmp_path / 'temp')
    assert worker.log_path.is_relative_to(run / 'workers')
    assert (worker.observation_root / 'diagnostics.json').exists()
    assert str(worker.observation_root / 'lifecycle.log') in worker.macro_path.read_text()
