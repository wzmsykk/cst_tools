from threading import Thread
import json
import time

import pytest

from csttool.project_session_recovery import (
    discover_managed_sessions,
    project_runtime_directory,
    recover_project_sessions,
)
from csttool import project_session_recovery
from csttool.configuration import ProjectDirectorySettings, ProjectSettings, write_ini_atomic
from csttool.runtime_protocol import (
    Completion,
    CompletionStatus,
    FileProtocol,
    StopAcknowledge,
    atomic_publish,
    encode_completion,
    encode_stop_ack,
    new_session_id,
)


def _session(project, marker="dispatched:task"):
    session_id = new_session_id()
    root = project / "temp" / "worker_0" / session_id
    protocol = FileProtocol(root / "protocol")
    (root / "worker.state").write_text(marker, encoding="ascii")
    return session_id, root, protocol


def test_discovers_only_sessions_that_need_protocol_recovery(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    active_id, _active_root, _active_protocol = _session(project)
    stopped_id, stopped_root, stopped_protocol = _session(project, "stopped")
    atomic_publish(
        stopped_protocol.root / "stop.ack",
        encode_stop_ack(StopAcknowledge(stopped_id)),
    )

    records = discover_managed_sessions(project)

    assert project_runtime_directory(project) == project / "temp"
    assert {item.session_id for item in records if item.needs_recovery} == {
        active_id
    }
    assert stopped_root.is_dir()


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("absolute", [False, True])
def test_session_discovery_uses_migrated_runtime_directory(tmp_path, legacy, absolute):
    project = tmp_path / "project"
    project.mkdir()
    configured = tmp_path / "custom-runtime" if absolute else "custom-runtime"
    settings = ProjectSettings(
        name="recovery", directories=ProjectDirectorySettings(temp=configured)
    )
    parser = settings.to_parser()
    if legacy:
        parser.remove_section("paths")
        parser["DIRS"] = {"tempdir": str(configured), "resultdir": "result"}
    write_ini_atomic(project / "project.ini", parser)
    runtime = tmp_path / "custom-runtime" if absolute else project / "custom-runtime"
    session_id = new_session_id()
    root = runtime / "worker_0" / session_id
    FileProtocol(root / "protocol")
    (root / "worker.state").write_text("dispatched:task", encoding="ascii")

    assert project_runtime_directory(project) == runtime
    records = discover_managed_sessions(project)
    assert len(records) == 1
    assert records[0].session_id == session_id
    assert records[0].needs_recovery


def test_project_recovery_stops_and_acks_an_active_session(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    session_id, root, protocol = _session(project)
    task_id = new_session_id()

    def worker_side():
        while not (protocol.root / "stop.request").exists():
            time.sleep(0.01)
        atomic_publish(
            protocol.root / "current.completion",
            encode_completion(
                Completion(task_id, session_id, CompletionStatus.SUCCESS)
            ),
        )
        while not (protocol.root / "current.ack").exists():
            time.sleep(0.01)
        atomic_publish(
            protocol.root / "stop.ack",
            encode_stop_ack(StopAcknowledge(session_id)),
        )
        (root / "worker.state").write_text(
            "stopped-with-completion", encoding="ascii"
        )

    thread = Thread(target=worker_side)
    thread.start()
    recovered = recover_project_sessions(project, timeout_per_session=2)
    thread.join(2)

    assert [item.session_id for item in recovered] == [session_id]
    assert not [
        item for item in discover_managed_sessions(project) if item.needs_recovery
    ]
    assert not thread.is_alive()
    receipt = json.loads((root / "recovery.json").read_text(encoding="utf-8"))
    assert receipt["disposition"] == "standard-stop"
    assert receipt["completion_task_id"] == task_id


def test_dead_session_without_stop_ack_is_abandoned_for_checkpoint_replay(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    session_id, root, _protocol = _session(project)
    (root / "worker.pid").write_text("99999999", encoding="ascii")

    recovered = recover_project_sessions(project, timeout_per_session=10)

    assert [item.session_id for item in recovered] == [session_id]
    assert (root / "worker.state").read_text(encoding="ascii") == "abandoned-dead"
    receipt = (root / "recovery.json").read_text(encoding="utf-8")
    assert '"disposition": "abandoned-dead"' in receipt
    assert not [
        item for item in discover_managed_sessions(project) if item.needs_recovery
    ]


def test_live_unresponsive_session_is_not_killed_or_marked_recovered(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    project.mkdir()
    session_id, root, _protocol = _session(project)
    (root / "worker.pid").write_text("12345", encoding="ascii")
    monkeypatch.setattr(
        "csttool.project_session_recovery._process_is_alive", lambda _pid: True
    )

    with pytest.raises(RuntimeError, match=session_id):
        recover_project_sessions(project, timeout_per_session=0.05)

    assert not (root / "recovery.json").exists()
    assert (root / "worker.state").read_text(encoding="ascii") == "dispatched:task"


def test_process_tree_remains_alive_when_launcher_exits_but_child_survives(
    monkeypatch,
):
    monkeypatch.setattr(
        project_session_recovery,
        "_windows_descendant_process_ids",
        lambda _pid: {222},
    )
    monkeypatch.setattr(
        project_session_recovery,
        "_process_is_alive",
        lambda pid: pid == 222,
    )

    assert project_session_recovery._process_tree_is_alive(111)
