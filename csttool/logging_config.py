"""Application logging configuration built on the Python standard library."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import json
from datetime import datetime, timezone
import subprocess
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import os
from uuid import uuid4


DEFAULT_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s "
    "| source=%(pathname)s:%(lineno)d function=%(funcName)s record_id=%(record_id)s"
)


class RecordIdentity(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "record_id"):
            record.record_id = uuid4().hex
        return True


def normalized_context(fields):
    """Add canonical identities without removing compatibility aliases."""
    fields = dict(fields)
    for old, new in (('task', 'task_id'), ('session', 'session_id'), ('worker', 'worker_id')):
        if old in fields and new not in fields:
            fields[new] = fields[old]
    return fields


class DiagnosticTextFormatter(logging.Formatter):
    """Human summary first; full structured details on a separate line."""
    def format(self, record):
        rendered = super().format(record)
        standard = logging.makeLogRecord({}).__dict__
        details = normalized_context({key: value for key, value in record.__dict__.items()
            if key not in standard and key not in {'message', 'asctime', 'exc_text', 'record_id'}})
        if details:
            rendered += '\n  context=' + json.dumps(details, ensure_ascii=False, default=str)
        return rendered


def log_failure(logger, message, error, *, extra=None):
    """Retain the first traceback; refer to it when the same cause is propagated."""
    cursor, seen, reference = error, set(), None
    while cursor is not None and id(cursor) not in seen:
        seen.add(id(cursor))
        reference = getattr(cursor, '_cst_log_failure_id', None)
        if reference:
            break
        # Implicit context can be a *different* cleanup failure, not propagation.
        cursor = cursor.__cause__
    identity = reference or uuid4().hex
    fields = {**(extra or {}), 'error_ref':identity, 'reason':str(error),
              'error_type':type(error).__name__, 'traceback_repeated':bool(reference)}
    if not reference:
        fields['record_id'] = identity
    logger.error(message, extra=fields,
                 exc_info=None if reference else (type(error), error, error.__traceback__), stacklevel=2)
    try:
        error._cst_log_failure_id = identity
    except (AttributeError, TypeError):
        pass  # Non-extensible exception types safely retain duplicate diagnostics.


def _code_version():
    root = Path(__file__).resolve().parent.parent
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                  capture_output=True, text=True, timeout=2, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                                    cwd=root, capture_output=True, text=True, timeout=2, check=True).stdout.strip())
        return {"revision": revision, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"revision": None, "dirty": None}


class JsonLineFormatter(logging.Formatter):
    def __init__(self, code_version):
        super().__init__()
        self.code_version = code_version

    def format(self, record):
        error = None
        if record.exc_info:
            error = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }
        fields = normalized_context({key: value for key, value in record.__dict__.items()
                  if key not in logging.makeLogRecord({}).__dict__
                  and key not in {"message", "asctime", "exc_text", "record_id"}})
        payload = {
            "schema_version": 1,
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "record_id": record.record_id,
            "level": record.levelname,
            "logger": record.name,
            "thread": record.threadName,
            "process": record.process,
            "message": record.getMessage(),
            "event": fields.pop("event", None),
            "phase": fields.pop("phase", None),
            "artifacts": fields.pop("artifacts", {
                key: fields[key] for key in ("snapshot", "path", "json", "csv") if key in fields
            }),
            "source": {"file": record.pathname, "line": record.lineno, "function": record.funcName},
            "code": self.code_version,
            "context": fields,
            "error": error,
        }
        return json.dumps(payload, ensure_ascii=False, default=str)


class ContextLogger(logging.LoggerAdapter):
    """Attach correlation fields without altering the human message."""

    def log(self, level, msg, *args, **kwargs):
        if self.isEnabledFor(level):
            kwargs["stacklevel"] = kwargs.get("stacklevel", 1) + 1
            super().log(level, msg, *args, **kwargs)

    def process(self, msg, kwargs):
        kwargs["extra"] = normalized_context({**kwargs.get("extra", {}), **self.extra})
        return msg, kwargs


def _coerce_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    value = logging.getLevelName(str(level).upper())
    if not isinstance(value, int):
        raise ValueError(f"unknown logging level: {level!r}")
    return value


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    path: Path
    level: str | int = logging.INFO
    console: bool = True
    when: str = "midnight"
    backup_count: int = 7
    format_string: str = DEFAULT_FORMAT


class ApplicationLogSession:
    """Own the handlers for one application logging session."""

    def __init__(
        self,
        path: str | Path,
        *,
        level: str | int = "info",
        console: bool = True,
        when: str = "midnight",
        backup_count: int = 7,
        format_string: str = DEFAULT_FORMAT,
        name: str | None = None,
    ) -> None:
        config = LoggingConfig(
            path=Path(path),
            level=level,
            console=console,
            when=when,
            backup_count=backup_count,
            format_string=format_string,
        )
        config.path.parent.mkdir(parents=True, exist_ok=True)
        logger_name = name or f"cst_tools.session.{os.getpid()}.{uuid4().hex[:8]}"
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(_coerce_level(config.level))
        self.logger.propagate = False
        self._handlers: list[logging.Handler] = []
        self.path = config.path
        self.jsonl_path = config.path.with_suffix(".jsonl")
        if self.jsonl_path == self.path:
            self.jsonl_path = config.path.with_name(config.path.name + ".jsonl")
        identity = RecordIdentity()

        formatter = DiagnosticTextFormatter(config.format_string)
        file_handler = TimedRotatingFileHandler(
            filename=config.path,
            when=config.when,
            backupCount=config.backup_count,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(identity)
        self._add_handler(file_handler)

        json_handler = TimedRotatingFileHandler(
            filename=self.jsonl_path, when=config.when, backupCount=config.backup_count,
            encoding="utf-8", delay=True,
        )
        json_handler.setFormatter(JsonLineFormatter(_code_version()))
        json_handler.addFilter(identity)
        self._add_handler(json_handler)

        if config.console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.addFilter(identity)
            self._add_handler(console_handler)

        self._closed = False

    def _add_handler(self, handler: logging.Handler) -> None:
        handler.setLevel(self.logger.level)
        self.logger.addHandler(handler)
        self._handlers.append(handler)

    def close(self) -> None:
        if self._closed:
            return
        for handler in self._handlers:
            self.logger.removeHandler(handler)
            handler.close()
        self._handlers.clear()
        self._closed = True

    def __enter__(self) -> logging.Logger:
        return self.logger

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
