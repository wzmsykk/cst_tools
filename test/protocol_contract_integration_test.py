import subprocess

import pytest

from csttool.protocol_contract import prepare_contract_workspace
from csttool.runtime_protocol import (
    CompletionStatus,
    ParameterAssignment,
    ParameterKind,
    Task,
    new_session_id,
)


pytestmark = pytest.mark.integration


def test_cst_wwb_executes_protocol_golden_contract(cst_executable, tmp_path):
    session_id = new_session_id()
    task = Task.create(
        session_id,
        {"Rx": "90.0", "L": "2 * Rx = L"},
        expression_names=frozenset({"L"}),
    )
    workspace = prepare_contract_workspace(tmp_path, task)
    log_path = tmp_path / "cst-contract.log"

    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [str(cst_executable), "-m", str(workspace.macro_path)],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            completion = workspace.protocol.wait_completion(task, timeout=60)
            assert completion.status is CompletionStatus.SUCCESS
            workspace.protocol.acknowledge(completion)
            process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

    assert process.returncode == 0
    assert workspace.marker_path.read_text(encoding="ascii").strip() == "success"
