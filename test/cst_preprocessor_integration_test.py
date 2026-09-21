import hashlib
from pathlib import Path

import pytest

from csttool.cst_preprocessor import CstProjectPreprocessor


pytestmark = pytest.mark.integration


def test_cst_preprocessor_adds_hom_parameters_without_modifying_source(
    cst_executable,
    tmp_path,
):
    root = Path(__file__).parents[1]
    source = root / "model" / "Pillbox_2015.cst"
    output = tmp_path / "prepared.cst"
    parameter_json = tmp_path / "params.json"
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    result = CstProjectPreprocessor(
        cst_executable,
        root / "data" / "preprocess_hom_parameters_v1.vb",
        timeout=180,
    ).preprocess(
        source,
        output,
        parameter_json,
        tmp_path / "runtime",
        mesh_cells_per_wavelength=24,
    )

    after = hashlib.sha256(source.read_bytes()).hexdigest()
    values = {item["name"]: item["value"] for item in result.parameters}
    assert before == after
    assert output.is_file()
    assert output != source
    assert values["fmin"] == "400"
    assert values["fmax"] == "550"
    assert values["nmodes"] == "1"
    assert values["cell"] == "24"
