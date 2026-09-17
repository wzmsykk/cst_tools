"""Shared visual theme for the CST Tools desktop interface."""

from __future__ import annotations

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QDialogButtonBox, QPushButton, QWidget


APP_STYLE_SHEET = """
QWidget {
    background-color: #f4f7fb;
    color: #172033;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 10pt;
}
QMainWindow, QDialog {
    background-color: #f4f7fb;
}
QLabel {
    background: transparent;
    color: #344054;
}
QLabel#titleLabel {
    color: #102a43;
    font-size: 22pt;
    font-weight: 700;
}
QLabel#subtitleLabel {
    color: #667085;
    font-size: 10pt;
}
QLabel#sectionLabel {
    color: #344054;
    font-size: 10pt;
    font-weight: 700;
}
QFrame#setupPanel, QFrame#logPanel {
    background-color: #ffffff;
    border: 1px solid #d8e1eb;
    border-radius: 10px;
}
QLineEdit, QSpinBox, QPlainTextEdit, QListView {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 9px;
    selection-background-color: #0f7ea8;
    selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus, QListView:focus {
    border: 2px solid #168aad;
    padding: 5px 8px;
}
QLineEdit:read-only {
    background-color: #eef3f8;
    color: #475467;
}
QPlainTextEdit {
    background-color: #101828;
    color: #d0d5dd;
    border-color: #1d2939;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 9pt;
}
QListView::item {
    min-height: 30px;
    padding: 5px 8px;
    border-bottom: 1px solid #edf1f5;
}
QListView::item:selected {
    background-color: #d9f0f6;
    color: #075985;
}
QPushButton {
    background-color: #ffffff;
    color: #25324a;
    border: 1px solid #b8c4d4;
    border-radius: 7px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #eaf4f8;
    border-color: #168aad;
}
QPushButton:pressed {
    background-color: #d9edf3;
}
QPushButton:disabled {
    background-color: #e9eef4;
    color: #98a2b3;
    border-color: #d5dde7;
}
QPushButton[visualRole="primary"] {
    background-color: #0f7ea8;
    color: #ffffff;
    border-color: #0f7ea8;
}
QPushButton[visualRole="primary"]:hover {
    background-color: #0b6d93;
    border-color: #0b6d93;
}
QPushButton[visualRole="danger"] {
    background-color: #fff5f5;
    color: #b42318;
    border-color: #f1b5b1;
}
QPushButton[visualRole="danger"]:hover {
    background-color: #fee4e2;
    border-color: #d92d20;
}
QPushButton[visualRole="quiet"] {
    background-color: #eef3f8;
    border-color: #d6dee8;
}
QCheckBox {
    spacing: 8px;
    background: transparent;
}
QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border: 1px solid #98a2b3;
    border-radius: 4px;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background-color: #0f7ea8;
    border-color: #0f7ea8;
}
QFrame#AdvSettingframe {
    background-color: #eaf0f6;
    border: 1px solid #d0d9e5;
    border-radius: 8px;
}
QStatusBar {
    background-color: #e8eef5;
    color: #344054;
    border-top: 1px solid #d0d9e5;
}
QStatusBar[state="running"], QStatusBar[state="stopping"] {
    background-color: #e1f2f6;
    color: #075985;
}
QStatusBar[state="failed"] {
    background-color: #fee4e2;
    color: #b42318;
}
QProgressBar {
    background-color: #d7e0ea;
    border: 0;
    border-radius: 5px;
    min-width: 180px;
    max-height: 10px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background-color: #16a3b6;
    border-radius: 5px;
}
QToolTip {
    background-color: #172033;
    color: #ffffff;
    border: 0;
    padding: 5px;
}
"""


def set_visual_role(button: QPushButton, role: str) -> None:
    button.setProperty("visualRole", role)
    button.style().unpolish(button)
    button.style().polish(button)


def style_dialog_buttons(button_box: QDialogButtonBox) -> None:
    accept = button_box.button(QDialogButtonBox.Ok)
    cancel = button_box.button(QDialogButtonBox.Cancel)
    if accept is not None:
        accept.setText("保存")
        set_visual_role(accept, "primary")
    if cancel is not None:
        cancel.setText("取消")
        set_visual_role(cancel, "quiet")


def apply_theme(widget: QWidget) -> None:
    widget.setFont(QFont("Microsoft YaHei UI", 9))
    widget.setStyleSheet(APP_STYLE_SHEET)
