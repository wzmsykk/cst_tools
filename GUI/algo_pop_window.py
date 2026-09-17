from PyQt5.QtWidgets import QDialog, QMessageBox
from GUI.ui_algo_pop import Ui_AlgoPopDialog
from GUI.config_models import AlgorithmSettings
from GUI.theme import apply_theme, style_dialog_buttons
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QDoubleValidator


class myAlgDialog(QDialog, Ui_AlgoPopDialog):
    _signal_done = pyqtSignal()

    def __init__(self, Logger=None):
        super(myAlgDialog, self).__init__()
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
        validator = QDoubleValidator(self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        for editor in (
            self.fmaxLineEdit,
            self.fminLineEdit,
            self.maxFreqThresholdLineEdit,
            self.continueFreqLineEdit,
        ):
            editor.setValidator(validator)
        self.buttonBox.accepted.connect(self.saveAndHide)

    def setDefaultValues(self, param_dict):
        self.data.update(param_dict)
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

    def saveAndHide(self):
        try:
            self.setValues()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "算法设置无效", str(exc))
            return
        self.hide()
        self._signal_done.emit()

    def getValues(self):
        return dict(self.data)
