import pytest

from csttool.protocol_warm_worker import prepare_warm_worker_workspace
from csttool.runtime_protocol import Task, new_session_id


def make_tasks(session_id):
    return (
        Task.create(session_id, {"R": "229", "L": "R + 30"}, expression_names=frozenset({"L"})),
        Task.create(session_id, {"R": "230", "L": "R + 29"}, expression_names=frozenset({"L"})),
    )


def test_warm_workspace_has_two_independent_result_roots(tmp_path):
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    tasks = make_tasks(new_session_id())

    workspace = prepare_warm_worker_workspace(
        tmp_path / "warm", tasks, source,
        result_name="Frequency (Multiple Modes)/Mode 1",
    )

    assert workspace.tasks[0].result_root != workspace.tasks[1].result_root
    assert tasks[0].task_id in str(workspace.tasks[0].result_path)
    assert tasks[1].task_id in str(workspace.tasks[1].result_path)
    macro = workspace.macro_path.read_text(encoding="ascii")
    assert macro.lower().count("sub main") == 1
    assert macro.count("If Not CSTPWW_RunTask(") == 2
    assert "CSTP_ReadStopRequest" in macro


def test_warm_workspace_rejects_mixed_sessions(tmp_path):
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    with pytest.raises(ValueError, match="same worker session"):
        prepare_warm_worker_workspace(
            tmp_path / "warm",
            (Task.create(new_session_id(), {"x": 1}), Task.create(new_session_id(), {"x": 2})),
            source,
            result_name="Frequency/Mode 1",
        )
