from dataclasses import replace

import pytest

from csttool.hom_project_profile import HOM_PROFILE_V1, ProfileValidationError
from csttool.protocol_hom_runtime_postprocess import (
    prepare_hom_runtime_postprocess_workspace,
)
from csttool.runtime_protocol import Task, new_session_id


RESULT_NAME = "Frequency (Multiple Modes)/Mode 1"


def _task(parameters=None):
    return Task.create(
        new_session_id(), parameters or {"fmin": "720", "fmax": "800"}
    )


def test_runtime_r_over_q_workspace_accepts_declared_profile(tmp_path):
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")

    workspace = prepare_hom_runtime_postprocess_workspace(
        tmp_path / "run",
        _task(),
        source,
        result_name=RESULT_NAME,
        profile=HOM_PROFILE_V1,
    )

    macro = workspace.worker.macro_path.read_text(encoding="ascii")
    assert macro.count("EigenResult_Complex_output") == 5
    assert 'stage = "runtime-postprocess"' in macro


def test_runtime_r_over_q_workspace_rejects_undeclared_capability(tmp_path):
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    profile = replace(
        HOM_PROFILE_V1,
        profile_id="no-dynamic-r-over-q",
        runtime_vba_metrics=frozenset({"voltage"}),
    )

    with pytest.raises(ProfileValidationError, match="does not declare dynamic R/Q"):
        prepare_hom_runtime_postprocess_workspace(
            tmp_path / "run",
            _task(),
            source,
            result_name=RESULT_NAME,
            profile=profile,
        )


def test_runtime_r_over_q_workspace_rejects_profile_parameters(tmp_path):
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")

    with pytest.raises(ProfileValidationError, match="does not allow parameters: R"):
        prepare_hom_runtime_postprocess_workspace(
            tmp_path / "run",
            _task({"R": "229"}),
            source,
            result_name=RESULT_NAME,
            profile=HOM_PROFILE_V1,
        )
