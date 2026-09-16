import pytest

from csttool.hom_project_profile import HOM_PROFILE_V1
from csttool.protocol_hom_template_evaluation import (
    prepare_hom_template_evaluation_workspace,
    read_result_template_inventory,
)
from csttool.runtime_protocol import Task, new_session_id


RESULT_NAME = "Frequency (Multiple Modes)/Mode 1"


def test_p5_6_worker_uses_supported_template_inventory_and_evaluation(tmp_path):
    source = tmp_path / "source.cst"
    source.write_bytes(b"project")
    task = Task.create(new_session_id(), {"fmin": "720", "fmax": "800"})
    workspace = prepare_hom_template_evaluation_workspace(
        tmp_path / "run", task, source, result_name=RESULT_NAME
    )
    macro = workspace.worker.macro_path.read_text(encoding="ascii")

    assert macro.lower().count("sub main") == 1
    assert macro.count("EigenmodeSolver.Start") == 1
    assert macro.count("EvaluateResultTemplates") == 1
    assert "ResetTemplateIterator" in macro
    assert "GetNextTemplate" in macro
    assert '"PROFILE_CAPABILITY_MISSING"' in macro
    assert "Update Params" not in macro
    assert macro.index("template-inventory-before") < macro.index('stage = "parameters"')
    assert macro.index("template-inventory-before") < macro.index("EigenmodeSolver.Start")
    for requirement in HOM_PROFILE_V1.required_templates:
        assert requirement.result_name in macro
    assert macro.index("EigenmodeSolver.Start") < macro.index(
        "template-evaluate-current-run"
    )
    assert macro.index("template-evaluate-current-run") < macro.index('stage = "flush"')


def test_result_template_inventory_parser_is_strict(tmp_path):
    path = tmp_path / "templates.tsv"
    path.write_text(
        "R over Q beta=1 (Multiple Modes)\tM0D\t3D Eigenmode Result\t\n",
        encoding="ascii",
    )
    records = read_result_template_inventory(path)
    assert records[0].result_name == "R over Q beta=1 (Multiple Modes)"
    assert records[0].template_type == "M0D"
    assert records[0].template_name == "3D Eigenmode Result"

    path.write_text("only\tthree\tfields\n", encoding="ascii")
    with pytest.raises(ValueError, match="expected 4 fields"):
        read_result_template_inventory(path)
