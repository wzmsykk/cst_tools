from pathlib import Path

from csttool.protocol_contract import prepare_contract_workspace
from csttool.runtime_protocol import ParameterAssignment, ParameterKind, Task


TASK_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"


def contract_task():
    return Task(
        TASK_ID,
        SESSION_ID,
        (
            ParameterAssignment("Rx", ParameterKind.LITERAL, "90.0"),
            ParameterAssignment("L", ParameterKind.EXPRESSION, "2 * Rx = L"),
        ),
    )


def test_contract_workspace_is_deterministic_and_isolated(tmp_path):
    workspace = prepare_contract_workspace(tmp_path, contract_task())
    macro = workspace.macro_path.read_text(encoding="ascii")

    assert workspace.protocol.task_path(TASK_ID).is_file()
    assert not workspace.completion_path.exists()
    assert not workspace.ack_path.exists()
    assert macro.lower().count("sub main") == 1
    assert "%TASK_PATH%" not in macro
    assert str(workspace.protocol.task_path(TASK_ID)) in macro
    assert "Public Function CSTP_ReadTask" in macro
    assert "CSTP_WriteCompletion" in macro
    assert "CSTP_ReadAck" in macro
