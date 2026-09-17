import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from GUI.algo_pop_window import myAlgDialog
from GUI.config_models import (
    AlgorithmSettings,
    PostProcessSetting,
    decode_postprocess_document,
    encode_postprocess_document,
)
from GUI.postprocess_dialog import myPostProcessDataModel, myPPSDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pps(name="frequency", method="Frequency"):
    return {"resultName": name, "method": method, "params": {"iModeNumber": 1}}


def test_algorithm_settings_are_typed_and_cross_validated():
    settings = AlgorithmSettings.from_mapping(
        {"fmin": "500", "fmax": "700", "endfreq": "2500", "cfreq": "650", "cflag": 1}
    )
    assert settings.to_legacy_dict()["cflag"] == 1
    with pytest.raises(ValueError, match="最低频率"):
        AlgorithmSettings.from_mapping(
            {"fmin": 800, "fmax": 700, "endfreq": 2500, "cfreq": 650}
        )


def test_algorithm_dialog_installs_numeric_validators_and_returns_copy(qapp):
    dialog = myAlgDialog()
    dialog.setDefaultValues({"fmin": 500, "fmax": 700, "endfreq": 2500, "cfreq": 650})
    assert dialog.fminLineEdit.validator() is not None
    dialog.setValues()
    values = dialog.getValues()
    values["fmin"] = 1
    assert dialog.getValues()["fmin"] == 500


def test_postprocess_uses_stable_key_and_separate_display_name():
    setting = PostProcessSetting.from_mapping(
        {
            "resultName": "impedance",
            "method": "Shunt_Inpedence",
            "params": {"iModeNumber": 1, "xoffset": 0, "yoffset": 5},
        }
    )
    assert setting.method == "Shunt_Inpedence"
    assert "Shunt Impedance" in setting.display_text


def test_postprocess_model_emits_structural_row_signals(qapp):
    model = myPostProcessDataModel()
    inserted = QSignalSpy(model.rowsInserted)
    removed = QSignalSpy(model.rowsRemoved)
    model.append(pps())
    assert len(inserted) == 1
    assert model.removeRow(0)
    assert len(removed) == 1


def test_postprocess_model_rejects_duplicate_result_names(qapp):
    model = myPostProcessDataModel([pps()])
    with pytest.raises(ValueError, match="重复"):
        model.append(pps())


def test_versioned_json_round_trip_and_legacy_list_compatibility():
    legacy = [pps()]
    decoded = decode_postprocess_document(legacy)
    document = encode_postprocess_document(decoded)
    assert document["schemaVersion"] == 1
    assert decode_postprocess_document(json.loads(json.dumps(document))) == decoded


def test_set_pps_list_replaces_instead_of_duplicating(qapp):
    dialog = myPPSDialog()
    dialog.setPPSList([pps("first")])
    dialog.setPPSList([pps("second")])
    assert [item["resultName"] for item in dialog.getPPSList()] == ["second"]


def test_invalid_postprocess_document_is_rejected():
    with pytest.raises(ValueError, match="版本"):
        decode_postprocess_document({"schemaVersion": 999, "postProcesses": []})
    with pytest.raises(ValueError, match="不支持"):
        PostProcessSetting.from_mapping(
            {"resultName": "x", "method": "UI label", "params": {}}
        )
