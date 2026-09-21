import logging

from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)
from GUI.ui_algo_pop import Ui_AlgoPopDialog
from GUI.config_models import AlgorithmSettings
from GUI.theme import apply_theme, style_dialog_buttons
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QDoubleValidator, QIntValidator


class AlgorithmSettingsDialog(QDialog, Ui_AlgoPopDialog):
    _signal_done = pyqtSignal()

    def __init__(self, logger: logging.Logger | None = None, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        apply_theme(self)
        style_dialog_buttons(self.buttonBox)
        self.setWindowTitle("扫描与算法设置")
        self.fminLineEdit.setPlaceholderText("最低扫描频率")
        self.fmaxLineEdit.setPlaceholderText("最高扫描频率")
        self.maxFreqThresholdLineEdit.setPlaceholderText("扫描停止频率")
        self.meshCellsLineEdit.setPlaceholderText("例如 20")
        self.logger = logger
        self.data = dict()
        self._committed_data = {}
        validator = QDoubleValidator(self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        for editor in (
            self.fmaxLineEdit,
            self.fminLineEdit,
            self.maxFreqThresholdLineEdit,
        ):
            editor.setValidator(validator)
        self.meshCellsLineEdit.setValidator(QIntValidator(1, 999999, self))
        self.meshConvergenceCheckBox = QCheckBox("运行前执行 Mesh 收敛分析", self)
        self.meshConvergenceStartSpinBox = QSpinBox(self)
        self.meshConvergenceStopSpinBox = QSpinBox(self)
        self.meshConvergenceStepSpinBox = QSpinBox(self)
        for editor in (
            self.meshConvergenceStartSpinBox,
            self.meshConvergenceStopSpinBox,
            self.meshConvergenceStepSpinBox,
        ):
            editor.setRange(1, 999999)
        self.meshConvergenceToleranceSpinBox = QDoubleSpinBox(self)
        self.meshConvergenceToleranceSpinBox.setRange(0.001, 99.999)
        self.meshConvergenceToleranceSpinBox.setDecimals(3)
        self.meshConvergenceToleranceSpinBox.setSuffix(" %")
        self._convergence_editors = (
            self.meshConvergenceStartSpinBox,
            self.meshConvergenceStopSpinBox,
            self.meshConvergenceStepSpinBox,
            self.meshConvergenceToleranceSpinBox,
        )
        self.meshConvergenceCheckBox.toggled.connect(
            self._set_convergence_controls_enabled
        )
        self._install_responsive_layout()
        self.buttonBox.accepted.disconnect()
        self.buttonBox.rejected.disconnect()
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _install_responsive_layout(self):
        self.setMinimumSize(620, 680)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)
        fields = QGridLayout()
        fields.setHorizontalSpacing(12)
        fields.setVerticalSpacing(14)
        rows = (
            (self.fminlabel, self.fminLineEdit, self.label),
            (self.fmaxlabel, self.fmaxLineEdit, self.label_2),
            (self.dstFreqLabel, self.maxFreqThresholdLineEdit, self.label_3),
            (self.meshCellsLabel, self.meshCellsLineEdit, None),
        )
        for row, (label, editor, unit) in enumerate(rows):
            fields.addWidget(label, row, 0)
            fields.addWidget(editor, row, 1)
            if unit is not None:
                fields.addWidget(unit, row, 2)
        fields.setColumnStretch(1, 1)
        layout.addLayout(fields)
        layout.addWidget(self.meshConvergenceCheckBox)
        convergence_fields = QGridLayout()
        convergence_rows = (
            ("起始单元数", self.meshConvergenceStartSpinBox),
            ("最大单元数", self.meshConvergenceStopSpinBox),
            ("递增步长", self.meshConvergenceStepSpinBox),
            ("结果变化容差", self.meshConvergenceToleranceSpinBox),
        )
        for row, (text, editor) in enumerate(convergence_rows):
            convergence_fields.addWidget(QLabel(text, self), row, 0)
            convergence_fields.addWidget(editor, row, 1)
        layout.addLayout(convergence_fields)
        layout.addStretch(1)
        layout.addWidget(self.buttonBox)

    def setDefaultValues(self, param_dict):
        self.data = AlgorithmSettings.from_mapping(param_dict).to_backend_payload()
        self._committed_data = dict(self.data)
        self._load_fields(self.data)

    def _load_fields(self, values):
        self.data = dict(values)
        self.fmaxLineEdit.setText(str(self.data.get("fmax", 700)))
        self.fminLineEdit.setText(str(self.data.get("fmin", 500)))
        self.maxFreqThresholdLineEdit.setText(str(self.data.get("endfreq", 2500)))
        self.meshCellsLineEdit.setText(
            str(self.data.get("mesh_cells_per_wavelength", 20))
        )
        self.meshConvergenceCheckBox.setChecked(
            bool(self.data.get("mesh_convergence_enabled", False))
        )
        self.meshConvergenceStartSpinBox.setValue(
            int(self.data.get("mesh_convergence_start", 10))
        )
        self.meshConvergenceStopSpinBox.setValue(
            int(self.data.get("mesh_convergence_stop", 30))
        )
        self.meshConvergenceStepSpinBox.setValue(
            int(self.data.get("mesh_convergence_step", 5))
        )
        self.meshConvergenceToleranceSpinBox.setValue(
            float(self.data.get("mesh_convergence_tolerance", 0.01)) * 100
        )
        self._set_convergence_controls_enabled(
            self.meshConvergenceCheckBox.isChecked()
        )

    def _set_convergence_controls_enabled(self, enabled):
        for editor in self._convergence_editors:
            editor.setEnabled(bool(enabled))

    def setValues(self):
        settings = AlgorithmSettings.from_mapping(
            {
                "fmax": self.fmaxLineEdit.text(),
                "fmin": self.fminLineEdit.text(),
                "endfreq": self.maxFreqThresholdLineEdit.text(),
                "mesh_cells_per_wavelength": self.meshCellsLineEdit.text(),
                "mesh_convergence_enabled": self.meshConvergenceCheckBox.isChecked(),
                "mesh_convergence_start": self.meshConvergenceStartSpinBox.value(),
                "mesh_convergence_stop": self.meshConvergenceStopSpinBox.value(),
                "mesh_convergence_step": self.meshConvergenceStepSpinBox.value(),
                "mesh_convergence_tolerance": (
                    self.meshConvergenceToleranceSpinBox.value() / 100
                ),
            }
        )
        self.data = settings.to_backend_payload()

    def accept(self):
        try:
            self.setValues()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "算法设置无效", str(exc))
            return
        self._committed_data = dict(self.data)
        self._signal_done.emit()
        super().accept()

    def reject(self):
        if self._committed_data:
            self._load_fields(self._committed_data)
        super().reject()

    def getValues(self):
        return dict(self.data)
