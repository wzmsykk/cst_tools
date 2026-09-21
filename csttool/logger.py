"""Application logging configuration built on the Python standard library."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import os
from uuid import uuid4


DEFAULT_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s"
)


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
    format: str = DEFAULT_FORMAT


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
            format=format_string,
        )
        config.path.parent.mkdir(parents=True, exist_ok=True)
        logger_name = name or f"cst_tools.session.{os.getpid()}.{uuid4().hex[:8]}"
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(_coerce_level(config.level))
        self.logger.propagate = False
        self._handlers: list[logging.Handler] = []

        formatter = logging.Formatter(config.format)
        file_handler = TimedRotatingFileHandler(
            filename=config.path,
            when=config.when,
            backupCount=config.backup_count,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(formatter)
        self._add_handler(file_handler)

        if config.console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self._add_handler(console_handler)

        self._closed = False

    def _add_handler(self, handler: logging.Handler) -> None:
        handler.setLevel(self.logger.level)
        self.logger.addHandler(handler)
        self._handlers.append(handler)

    def getLogger(self) -> logging.Logger:
        return self.logger

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


class Logger(ApplicationLogSession):
    """Compatibility adapter for the historical constructor and ``getLogger`` API."""

    def __init__(
        self,
        filename: str | Path,
        level: str | int = "info",
        when: str = "midnight",
        backCount: int = 7,
        fmt: str = DEFAULT_FORMAT,
        console: bool = True,
        *,
        name: str | None = None,
    ) -> None:
        super().__init__(
            filename,
            level=level,
            console=console,
            when=when,
            backup_count=backCount,
            format_string=fmt,
            name=name,
        )


def get_logger(name: str) -> logging.Logger:
    """Return a library logger without configuring global logging."""
    return logging.getLogger(name)
