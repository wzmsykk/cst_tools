import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication, QWidget

from GUI.algorithm_settings_dialog import AlgorithmSettingsDialog
from GUI.config_models import (
    AlgorithmSettings,
    PostProcessSetting,
    decode_postprocess_document,
    encode_postprocess_document,
)
from GUI.postprocess_settings_dialog import PostProcessListModel, PostProcessSettingsDialog


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
    dialog = AlgorithmSettingsDialog()
    dialog.setDefaultValues({"fmin": 500, "fmax": 700, "endfreq": 2500, "cfreq": 650})
    assert dialog.fminLineEdit.validator() is not None
    dialog.setValues()
    values = dialog.getValues()
    values["fmin"] = 1
    assert dialog.getValues()["fmin"] == 500


def test_algorithm_dialog_validation_blocks_accept_and_cancel_restores_values(
    qapp, monkeypatch
):
    dialog = AlgorithmSettingsDialog()
    dialog.setDefaultValues(
        {"fmin": 500, "fmax": 700, "endfreq": 2500, "cfreq": 650}
    )
    warnings = []
    monkeypatch.setattr(
        "GUI.algorithm_settings_dialog.QMessageBox.warning",
        lambda *args: warnings.append(args),
    )
    completed = QSignalSpy(dialog._signal_done)
    dialog.show()
    dialog.fminLineEdit.setText("800")
    dialog.fmaxLineEdit.setText("700")
    dialog.accept()
    assert dialog.isVisible()
    assert len(completed) == 0
    assert warnings

    dialog.reject()
    assert dialog.fminLineEdit.text() == "500.0"
    assert dialog.fmaxLineEdit.text() == "700.0"


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
    model = PostProcessListModel()
    inserted = QSignalSpy(model.rowsInserted)
    removed = QSignalSpy(model.rowsRemoved)
    model.append(pps())
    assert len(inserted) == 1
    assert model.removeRow(0)
    assert len(removed) == 1


def test_postprocess_model_rejects_duplicate_result_names(qapp):
    model = PostProcessListModel([pps()])
    with pytest.raises(ValueError, match="重复"):
        model.append(pps())
    with pytest.raises(ValueError, match="重复"):
        model.replace([pps(), pps()])


def test_versioned_json_round_trip_and_legacy_list_compatibility():
    legacy = [pps()]
    decoded = decode_postprocess_document(legacy)
    document = encode_postprocess_document(decoded)
    assert document["schemaVersion"] == 1
    assert decode_postprocess_document(json.loads(json.dumps(document))) == decoded


def test_set_pps_list_replaces_instead_of_duplicating(qapp):
    dialog = PostProcessSettingsDialog()
    dialog.setPPSList([pps("first")])
    dialog.setPPSList([pps("second")])
    assert [item["resultName"] for item in dialog.getPPSList()] == ["second"]


def test_postprocess_cancel_rolls_back_and_accept_commits(qapp):
    dialog = PostProcessSettingsDialog()
    dialog.setPPSList([pps("committed")])
    dialog.listModel.append(pps("draft"))
    dialog.reject()
    assert [item["resultName"] for item in dialog.getPPSList()] == ["committed"]

    dialog.listModel.append(pps("saved"))
    dialog.accept()
    dialog.listModel.removeRow(1)
    dialog.reject()
    assert [item["resultName"] for item in dialog.getPPSList()] == [
        "committed",
        "saved",
    ]


def test_existing_postprocess_item_can_be_edited(qapp):
    dialog = PostProcessSettingsDialog()
    dialog.setPPSList([pps("old")])
    changed = QSignalSpy(dialog.listModel.dataChanged)
    dialog.editItem(dialog.listModel.index(0, 0))
    dialog.addDialog.data = pps("new")
    dialog.addItem()
    assert dialog.getPPSList()[0]["resultName"] == "new"
    assert len(changed) == 1


def test_settings_dialogs_have_parent_lifecycle_and_responsive_layouts(qapp):
    parent = QWidget()
    algorithm = AlgorithmSettingsDialog(parent=parent)
    postprocess = PostProcessSettingsDialog(parent=parent)
    assert algorithm.parent() is parent
    assert postprocess.parent() is parent
    assert postprocess.addDialog.parent() is postprocess
    assert algorithm.layout() is not None
    assert postprocess.layout() is not None
    assert postprocess.minimumWidth() >= 780


def test_invalid_postprocess_document_is_rejected():
    with pytest.raises(ValueError, match="版本"):
        decode_postprocess_document({"schemaVersion": 999, "postProcesses": []})
    with pytest.raises(ValueError, match="不支持"):
        PostProcessSetting.from_mapping(
            {"resultName": "x", "method": "UI label", "params": {}}
        )
    with pytest.raises(ValueError, match="重复"):
        decode_postprocess_document([pps(), pps()])
