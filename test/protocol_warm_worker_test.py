from dataclasses import replace

import pytest

from csttool.hom_project_profile import HOM_PROFILE_V1, ProfileValidationError
from csttool.project_profile import ProjectProfile
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
    assert "stage:profile-preflight" not in macro
    assert workspace.profile_inventory_path is None


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


def test_hom_profile_is_checked_once_before_warm_task_loop(tmp_path):
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    session_id = new_session_id()
    tasks = (
        Task.create(session_id, {"fmin": "720", "fmax": "800"}),
        Task.create(session_id, {"fmin": "800", "fmax": "880"}),
    )
    workspace = prepare_warm_worker_workspace(
        tmp_path / "warm",
        tasks,
        source,
        result_name="Frequency (Multiple Modes)/Mode 1",
        profile=HOM_PROFILE_V1,
    )
    macro = workspace.macro_path.read_text(encoding="ascii")

    assert workspace.profile_inventory_path is not None
    assert macro.count("stage:profile-preflight") == 1
    assert macro.index("stage:profile-preflight") < macro.index("CSTPWW_RunTask")
    assert macro.count("CSTPWW_WriteTemplateInventory") == 2
    assert macro.count("EigenmodeSolver.Start") == 1
    for requirement in HOM_PROFILE_V1.required_templates:
        assert requirement.result_name in macro


def test_hom_profile_rejects_unsupported_warm_parameters(tmp_path):
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    tasks = make_tasks(new_session_id())
    with pytest.raises(ProfileValidationError, match="does not allow parameters"):
        prepare_warm_worker_workspace(
            tmp_path / "warm",
            tasks,
            source,
            result_name="Frequency (Multiple Modes)/Mode 1",
            profile=replace(HOM_PROFILE_V1, profile_id="hom-invalid-task"),
        )


def test_warm_worker_accepts_domain_independent_project_profile(tmp_path):
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    session_id = new_session_id()
    tasks = (
        Task.create(session_id, {"fmin": "1"}),
        Task.create(session_id, {"fmin": "2"}),
    )
    profile = ProjectProfile(
        profile_id="generic-worker-test",
        cst_year=2022,
        source_project=source,
        mutable_parameters=frozenset({"fmin"}),
        required_templates=(),
        native_scalars=(),
        runtime_vba_metrics=frozenset(),
    )

    workspace = prepare_warm_worker_workspace(
        tmp_path / "warm",
        tasks,
        source,
        result_name="Frequency/Mode 1",
        profile=profile,
    )

    macro = workspace.macro_path.read_text(encoding="ascii")
    assert macro.count("stage:profile-preflight") == 1
    assert workspace.profile_inventory_path is not None
