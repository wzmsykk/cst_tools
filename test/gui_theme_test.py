import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QPushButton, QWidget

from GUI.algo_pop_window import myAlgDialog
from GUI.postprocess_dialog import myPPSDialog
from GUI.theme import APP_STYLE_SHEET, apply_theme, set_visual_role


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_shared_theme_contains_interaction_and_state_styles(qapp):
    widget = QWidget()
    apply_theme(widget)
    sheet = widget.styleSheet()
    assert sheet == APP_STYLE_SHEET
    assert 'QStatusBar[state="failed"]' in sheet
    assert 'QPushButton[visualRole="primary"]' in sheet
    assert "QPlainTextEdit" in sheet


def test_visual_roles_are_semantic_properties(qapp):
    button = QPushButton()
    set_visual_role(button, "danger")
    assert button.property("visualRole") == "danger"


def test_algorithm_dialog_uses_theme_and_localized_actions(qapp):
    dialog = myAlgDialog()
    assert dialog.windowTitle() == "扫描与算法设置"
    assert dialog.styleSheet() == APP_STYLE_SHEET
    assert dialog.buttonBox.button(QDialogButtonBox.Ok).text() == "保存"
    assert dialog.buttonBox.button(QDialogButtonBox.Ok).property("visualRole") == "primary"


def test_postprocess_dialog_marks_destructive_and_file_actions(qapp):
    dialog = myPPSDialog()
    assert dialog.windowTitle() == "后处理结果设置"
    assert dialog.DeleteButton.property("visualRole") == "danger"
    assert dialog.SaveJsonButton.property("visualRole") == "quiet"
    assert dialog.LoadJsonButton.property("visualRole") == "quiet"
