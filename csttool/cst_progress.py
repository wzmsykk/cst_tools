"""Incremental, best-effort progress extraction from redirected CST output."""

from __future__ import annotations

import codecs
from dataclasses import dataclass
import locale
from pathlib import Path
import re
import threading
import time
from typing import Callable


_PERCENT = re.compile(r"\]\s*(\d{1,3})\s*%")
_PASS = re.compile(r"Eigenmodes,\s*(Pass\s+\d+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CstProgressEvent:
    worker_id: str
    task_id: str | None
    interval_lo: float | None
    interval_hi: float | None
    stage: str
    pass_name: str | None
    local_percent: int | None
    message: str
    timestamp: float


class CstLogProgressParser:
    def __init__(self, worker_id: str, task_context: Callable[[], dict]):
        self.worker_id = worker_id
        self.task_context = task_context
        self.stage = "starting"
        self.pass_name = None
        self._last_key = None

    def feed_line(self, line: str) -> CstProgressEvent | None:
        message = line.strip()
        if not message:
            return None
        pass_match = _PASS.search(message)
        percent_match = _PERCENT.search(message)
        if pass_match:
            self.stage = "eigenmode-solver"
            self.pass_name = pass_match.group(1)
        elif "Marked " in message and "refinement" in message:
            self.stage = "mesh-refinement"
        elif "Refinement successful" in message:
            self.stage = "mesh-refinement-complete"
        elif "TetMesh" in message or "mesh generation" in message.casefold():
            self.stage = "mesh"
        elif "postprocess" in message.casefold():
            self.stage = "postprocess"

        percent = None
        if percent_match:
            percent = min(100, int(percent_match.group(1)))
        elif not pass_match and self.stage == "starting":
            return None

        context = self.task_context()
        key = (self.stage, self.pass_name, percent, context.get("task_id"))
        if key == self._last_key:
            return None
        self._last_key = key
        return CstProgressEvent(
            worker_id=self.worker_id,
            task_id=context.get("task_id"),
            interval_lo=context.get("interval_lo"),
            interval_hi=context.get("interval_hi"),
            stage=self.stage,
            pass_name=self.pass_name,
            local_percent=percent,
            message=message,
            timestamp=time.time(),
        )


class CstLogProgressMonitor:
    def __init__(
        self,
        path: str | Path,
        parser: CstLogProgressParser,
        callback: Callable[[CstProgressEvent], None],
        *,
        poll_interval: float = 0.2,
        encoding: str | None = None,
    ):
        self.path = Path(path)
        self.parser = parser
        self.callback = callback
        self.poll_interval = poll_interval
        self.encoding = encoding or locale.getpreferredencoding(False) or "utf-8"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name=f"cst-progress-{self.parser.worker_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

    def _run(self) -> None:
        decoder = codecs.getincrementaldecoder(self.encoding)(errors="replace")
        buffer = ""
        position = 0
        while not self._stop.wait(self.poll_interval):
            if not self.path.exists():
                continue
            size = self.path.stat().st_size
            if size < position:
                position = 0
                decoder.reset()
                buffer = ""
            if size == position:
                continue
            with self.path.open("rb") as stream:
                stream.seek(position)
                chunk = stream.read()
                position = stream.tell()
            buffer += decoder.decode(chunk).replace("\r", "\n")
            lines = buffer.split("\n")
            buffer = lines.pop()
            for line in lines:
                event = self.parser.feed_line(line)
                if event is not None:
                    try:
                        self.callback(event)
                    except Exception:
                        # Progress is observational and must never fail a solve.
                        pass
