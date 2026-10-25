"""Real Windows file-release checks on production resource owners; no CST."""
import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
from csttool.execution_contract import StopIntent
from csttool.runner import LocalExecution
from csttool.hom_scan_algorithm import HomScanAlgorithm


def test_invalid_config_constructor_releases_both_log_files(tmp_path):
    config = tmp_path / 'control/config/current.ini'
    config.parent.mkdir(parents=True)
    config.write_text('not an INI document\n')
    with pytest.raises(Exception, match='section headers'):
        LocalExecution(tmp_path, StopIntent(), uuid4().hex, lambda **kw: None)
    paths = list(tmp_path.glob('logs/*/application.log')) + list(tmp_path.glob('logs/*/application.jsonl'))
    assert len(paths) == 2
    for path in paths:
        path.rename(path.with_suffix(path.suffix + '.released'))  # Windows denies while open.
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            assert not any(isinstance(h, logging.FileHandler) and str(tmp_path) in h.baseFilename for h in logger.handlers)


def test_hom_preflight_failure_does_not_open_unused_result_log(tmp_path):
    manager = SimpleNamespace(currProjectDir=tmp_path, result_directory=tmp_path / 'result', logger=logging.getLogger('exit-test'))
    manager.result_directory.mkdir()
    algorithm = HomScanAlgorithm(manager, params=[])
    checkpoint = Path(algorithm.relative_location) / 'hom_scan_checkpoint.json'
    checkpoint.write_text('{}')
    with pytest.raises(RuntimeError, match='检查点'):
        algorithm.start()
    assert not (manager.result_directory / 'result.log').exists()
    manager.result_directory.rmdir()


@pytest.mark.parametrize('fault', ['overview', 'backend'])
def test_execution_close_runs_all_cleanup_after_failure(tmp_path, monkeypatch, fault):
    execution = LocalExecution(tmp_path, StopIntent(), uuid4().hex, lambda **kw: None)
    execution.log.logger.info('open both outputs')
    if fault == 'overview':
        monkeypatch.setattr(execution.overview, 'update', lambda **kw: (_ for _ in ()).throw(OSError('overview unavailable')))
    else:
        monkeypatch.setattr(execution.backend, 'close_logging', lambda: (_ for _ in ()).throw(OSError('backend close failed')))
    with pytest.raises(OSError): execution.close()
    assert not execution.log.logger.handlers
    execution.log.path.rename(execution.log.path.with_name('application.log.released'))
    execution.log.jsonl_path.rename(execution.log.jsonl_path.with_name('application.jsonl.released'))


def test_one_failing_handler_does_not_leave_other_handlers_open(tmp_path, monkeypatch):
    from csttool.logging_config import ApplicationLogSession
    owner = ApplicationLogSession(tmp_path / 'application.log')
    owner.logger.info('open')
    original = owner._handlers[0].close
    def failing_close():
        original()
        raise OSError('injected close failure')
    monkeypatch.setattr(owner._handlers[0], 'close', failing_close)
    with pytest.raises(OSError): owner.close()
    assert not owner.logger.handlers
    for path in tmp_path.iterdir(): path.unlink()
    assert not owner._closed  # Failed cleanup remains explicitly retryable.
    monkeypatch.setattr(owner._handlers[0], 'close', original)
    owner.close()
    assert owner._closed and not owner._handlers
