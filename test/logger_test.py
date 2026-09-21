import logging
from logging.handlers import TimedRotatingFileHandler

import pytest

from csttool.logger import ApplicationLogSession, DEFAULT_FORMAT, Logger


def test_logger_creates_an_independent_rotating_file_session(tmp_path):
    first = ApplicationLogSession(
        tmp_path / "first.log", level="debug", console=False
    )
    second = ApplicationLogSession(tmp_path / "second.log", console=False)
    try:
        assert first.logger is not second.logger
        assert first.logger.propagate is False
        assert len(first.logger.handlers) == 1
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


def test_logger_console_flag_only_controls_console_handler(tmp_path):
    owner = ApplicationLogSession(tmp_path / "app.log", console=True)
    try:
        assert len(owner.logger.handlers) == 2
        assert sum(
            isinstance(handler, TimedRotatingFileHandler)
            for handler in owner.logger.handlers
        ) == 1
    finally:
        owner.close()


def test_logger_rejects_unknown_level(tmp_path):
    with pytest.raises(ValueError, match="unknown logging level"):
        ApplicationLogSession(tmp_path / "app.log", level="verbose")


def test_legacy_logger_adapter_keeps_get_logger_api(tmp_path):
    owner = Logger(tmp_path / "legacy.log", backCount=2, console=False)
    try:
        assert owner.getLogger() is owner.logger
    finally:
        owner.close()


def test_default_format_contains_concurrency_context():
    assert "%(threadName)s" in DEFAULT_FORMAT
    assert "%(name)s" in DEFAULT_FORMAT
