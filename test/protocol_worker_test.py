from csttool.protocol_worker import prepare_worker_workspace
from csttool.runtime_protocol import ParameterKind, Task, new_session_id


def test_worker_workspace_is_independent_and_keeps_parameter_kinds(tmp_path):
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    task = Task.create(
        new_session_id(), {"nmodes": "1", "L": "R + 30"},
        expression_names=frozenset({"L"}),
    )

    workspace = prepare_worker_workspace(
        tmp_path / "run", task, source,
        result_name="Frequency (Multiple Modes)/Mode 1",
    )

    assert workspace.project_path.read_bytes() == b"project"
    assert workspace.project_path != source
    assert [p.kind for p in task.parameters] == [ParameterKind.LITERAL, ParameterKind.EXPRESSION]
    macro = workspace.macro_path.read_text(encoding="ascii")
    assert macro.lower().count("sub main") == 1
    assert "EigenmodeSolver.Start" in macro
    assert str(workspace.result_path) in macro
    assert "legacy worker.vb" in macro
