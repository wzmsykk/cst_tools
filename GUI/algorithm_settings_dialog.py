from PyQt5.QtWidgets import QDialog, QGridLayout, QMessageBox, QVBoxLayout
from GUI.ui_algo_pop import Ui_AlgoPopDialog
from GUI.config_models import AlgorithmSettings
from GUI.theme import apply_theme, style_dialog_buttons
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QDoubleValidator


class AlgorithmSettingsDialog(QDialog, Ui_AlgoPopDialog):
    _signal_done = pyqtSignal()

    def __init__(self, Logger=None, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        apply_theme(self)
        style_dialog_buttons(self.buttonBox)
        self.setWindowTitle("扫描与算法设置")
        self.fminLineEdit.setPlaceholderText("最低扫描频率")
        self.fmaxLineEdit.setPlaceholderText("最高扫描频率")
        self.continueFreqLineEdit.setPlaceholderText("断点继续频率")
        self.maxFreqThresholdLineEdit.setPlaceholderText("扫描停止频率")
        self.logger = Logger
        self.data = dict()
        self._committed_data = {}
        validator = QDoubleValidator(self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        for editor in (
            self.fmaxLineEdit,
            self.fminLineEdit,
            self.maxFreqThresholdLineEdit,
            self.continueFreqLineEdit,
        ):
            editor.setValidator(validator)
        self._install_responsive_layout()
        self.buttonBox.accepted.disconnect()
        self.buttonBox.rejected.disconnect()
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _install_responsive_layout(self):
        self.setMinimumSize(520, 360)
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
        )
        for row, (label, editor, unit) in enumerate(rows):
            fields.addWidget(label, row, 0)
            fields.addWidget(editor, row, 1)
            fields.addWidget(unit, row, 2)
        fields.setColumnStretch(1, 1)
        layout.addLayout(fields)
        layout.addWidget(self.continueCheckBox)
        layout.addWidget(self.continueFreqLineEdit)
        layout.addStretch(1)
        layout.addWidget(self.buttonBox)

    def setDefaultValues(self, param_dict):
        self.data = AlgorithmSettings.from_mapping(param_dict).to_legacy_dict()
        self._committed_data = dict(self.data)
        self._load_fields(self.data)

    def _load_fields(self, values):
        self.data = dict(values)
        self.fmaxLineEdit.setText(str(self.data.get("fmax", 700)))
        self.fminLineEdit.setText(str(self.data.get("fmin", 500)))
        self.maxFreqThresholdLineEdit.setText(str(self.data.get("endfreq", 2500)))
        self.continueFreqLineEdit.setText(str(self.data.get("cfreq", 650)))
        self.continueCheckBox.setChecked(bool(self.data.get("cflag", 0)))

    def setValues(self):
        settings = AlgorithmSettings.from_mapping(
            {
                "fmax": self.fmaxLineEdit.text(),
                "fmin": self.fminLineEdit.text(),
                "endfreq": self.maxFreqThresholdLineEdit.text(),
                "cfreq": self.continueFreqLineEdit.text(),
                "cflag": self.continueCheckBox.isChecked(),
            }
        )
        self.data = settings.to_legacy_dict()

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
