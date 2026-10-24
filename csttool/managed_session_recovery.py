"""Protocol-level recovery for a controller lost during a managed CST task."""

from __future__ import annotations

from pathlib import Path
import time

from .runtime_protocol import (
    Acknowledge,
    Completion,
    FileProtocol,
    atomic_publish,
    decode_completion,
    encode_ack,
    publish_ack_idempotently,
)


def recover_and_stop_session(
    protocol_root: str | Path,
    session_id: str,
    *,
    timeout: float = 1200.0,
    poll_interval: float = 0.1,
    peer_exited=None,
) -> Completion | None:
    """Await StopAck or an owned peer's observed exit; caller must verify closure."""
    protocol = FileProtocol(protocol_root)
    stop_path = protocol.root / "stop.request"
    if not stop_path.exists():
        protocol.request_stop(session_id)
    else:
        protocol.read_stop_request(session_id)
    completion_path = protocol.root / "current.completion"
    ack_path = protocol.root / "current.ack"
    deadline = time.monotonic() + timeout
    completion = None

    while time.monotonic() < deadline:
        if completion is None and completion_path.exists():
            completion = decode_completion(
                completion_path.read_text(encoding="utf-8")
            )
            if completion.session_id != session_id:
                raise ValueError("completion belongs to another worker session")
            publish_ack_idempotently(
                ack_path, Acknowledge(completion.task_id, completion.session_id)
            )
        if protocol.read_stop_ack(session_id) is not None:
            return completion
        if peer_exited is not None and peer_exited():
            return completion  # Exit is NOT a fabricated StopAck or success.
        time.sleep(poll_interval)
    raise TimeoutError("timed out recovering managed CST session")
