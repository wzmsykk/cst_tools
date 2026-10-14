import logging
import json
import inspect
from logging.handlers import TimedRotatingFileHandler

import pytest

from csttool.logging_config import ApplicationLogSession, DEFAULT_FORMAT
from csttool.logging_config import ContextLogger
from concurrent.futures import ThreadPoolExecutor


def test_session_creates_an_independent_rotating_file_logger(tmp_path):
    first = ApplicationLogSession(
        tmp_path / "first.log", level="debug", console=False
    )
    second = ApplicationLogSession(tmp_path / "second.log", console=False)
    try:
        assert first.logger is not second.logger
        assert first.logger.propagate is False
        assert len(first.logger.handlers) == 2
        assert isinstance(first.logger.handlers[0], TimedRotatingFileHandler)

        first.logger.info("RUN_TEST value=%d", 7)
        assert "RUN_TEST value=7" in (tmp_path / "first.log").read_text(
            encoding="utf-8"
        )
        assert "MainThread" in (tmp_path / "first.log").read_text(encoding="utf-8")
    finally:
        first.close()
        second.close()

    assert first.logger.handlers == []


def test_console_flag_only_controls_console_handler(tmp_path):
    owner = ApplicationLogSession(tmp_path / "app.log", console=True)
    try:
        assert len(owner.logger.handlers) == 3
        assert sum(
            isinstance(handler, TimedRotatingFileHandler)
            for handler in owner.logger.handlers
        ) == 2
    finally:
        owner.close()


def test_session_rejects_unknown_level(tmp_path):
    with pytest.raises(ValueError, match="unknown logging level"):
        ApplicationLogSession(tmp_path / "app.log", level="verbose")


def test_default_format_contains_concurrency_context():
    assert "%(threadName)s" in DEFAULT_FORMAT


def test_context_is_isolated_between_concurrent_runs(caplog):
    base = logging.getLogger("context-test")
    with caplog.at_level(logging.INFO):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(ContextLogger(base, {"run_id": run, "project": "100% cavity"}).info,
                                   "任务完成 job=%s", run) for run in ("run-a", "run-b")]
            for future in futures:
                future.result()
    records = [record for record in caplog.records if record.name == "context-test"]
    assert {record.run_id for record in records} == {"run-a", "run-b"}
    for record in records:
        assert f"job={record.run_id}" in record.getMessage()
        assert record.project == '100% cavity'
        assert 'project=' not in record.getMessage()
    assert "%(name)s" in DEFAULT_FORMAT


def test_jsonl_has_source_context_error_and_same_record_identity(tmp_path):
    with ApplicationLogSession(tmp_path / "dual.log", console=False) as logger:
        adapter = ContextLogger(ContextLogger(logger, {"run_id": "run-1"}), {"worker": "0"})
        try:
            raise ValueError("模拟失败\n第二行")
        except ValueError:
            source_line = inspect.currentframe().f_lineno + 1
            adapter.exception("读取失败 | value=%s", 7, extra={"event": "RESULT_READ_FAILED", "phase": "readout", "artifacts": {"snapshot": tmp_path / "project.cst"}})
    lines = (tmp_path / "dual.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    item = json.loads(lines[0])
    assert item["event"] == "RESULT_READ_FAILED"
    assert item["phase"] == "readout"
    assert item["context"]["run_id"] == "run-1"
    assert item["context"]["worker"] == "0"
    assert item["source"]["line"] == source_line
    assert item["source"]["function"] == inspect.currentframe().f_code.co_name
    assert item["error"]["type"] == "ValueError"
    assert "ValueError" in item["error"]["traceback"]
    assert str(tmp_path / "project.cst") == item["artifacts"]["snapshot"]
    assert item["record_id"] in (tmp_path / "dual.log").read_text(encoding="utf-8")
    assert set(item["code"]) == {"revision", "dirty"}


def test_clean_summary_and_diagnostic_formatter_keep_context_and_aliases(tmp_path):
    with ApplicationLogSession(tmp_path/'readable.log',console=False) as logger:
        adapter = ContextLogger(logger, {'run_id':'r', 'session':'s', 'worker':'w'})
        adapter.info('任务已提交', extra={'task':'t','event':'WORKER_TASK_DISPATCH','phase':'solve','fmin':500})
    item = json.loads((tmp_path/'readable.jsonl').read_text(encoding='utf-8'))
    assert item['message'] == '任务已提交'
    assert item['context']['task'] == item['context']['task_id'] == 't'
    assert item['context']['session'] == item['context']['session_id'] == 's'
    assert item['context']['worker'] == item['context']['worker_id'] == 'w'
    text = (tmp_path/'readable.log').read_text(encoding='utf-8')
    assert 'context=' in text and 'WORKER_TASK_DISPATCH' in text
    assert '"fmin": 500' in text and 'source=' in text


def test_same_cause_has_one_traceback_and_independent_error_keeps_its_trace(tmp_path):
    from csttool.logging_config import log_failure
    with ApplicationLogSession(tmp_path/'failure.log',console=False) as logger:
        try:
            raise ValueError('root failure')
        except ValueError as root:
            line = inspect.currentframe().f_lineno + 1
            log_failure(logger, '读取失败', root, extra={'phase':'readout'})
            try:
                raise RuntimeError('outer failure') from root
            except RuntimeError as outer:
                log_failure(logger, '运行未完成', outer, extra={'phase':'execute'})
        try:
            raise OSError('separate shutdown failure')
        except OSError as independent:
            log_failure(logger, '退出失败', independent, extra={'phase':'shutdown'})
    rows = [json.loads(text) for text in (tmp_path/'failure.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(rows) == 3
    assert rows[0]['source']['line'] == line
    assert rows[0]['source']['file'] == __file__
    assert rows[0]['error']['type'] == 'ValueError'
    assert rows[1]['error'] is None
    assert rows[1]['context']['error_ref'] == rows[0]['record_id']
    assert rows[1]['context']['reason'] == 'outer failure'
    assert rows[2]['error']['type'] == 'OSError'
    assert rows[2]['context']['error_ref'] != rows[0]['record_id']


def test_failure_source_is_business_call_even_through_nested_adapters(caplog):
    from csttool.logging_config import log_failure
    logger = ContextLogger(ContextLogger(logging.getLogger('failure-source'), {'run_id':'r'}), {'worker':'w'})
    try:
        raise ValueError('test')
    except ValueError as error:
        line = inspect.currentframe().f_lineno + 1
        log_failure(logger, '失败摘要', error)
    captured = [record for record in caplog.records if record.name == 'failure-source'][-1]
    assert captured.lineno == line
    assert captured.pathname == __file__


def test_new_cleanup_error_with_implicit_context_is_not_deduplicated(caplog):
    from csttool.logging_config import log_failure
    logger = logging.getLogger('cleanup-separate')
    try:
        raise ValueError('run failed')
    except ValueError as run_error:
        log_failure(logger, '运行失败', run_error)
        try:
            raise OSError('stop failed')
        except OSError as stop_error:
            assert stop_error.__context__ is run_error
            log_failure(logger, '退出失败', stop_error)
    rows = [record for record in caplog.records if record.name == 'cleanup-separate']
    assert len(rows) == 2
    assert all(record.exc_info for record in rows)
    assert rows[0].error_ref != rows[1].error_ref
