from PyQt5.QtWidgets import QApplication, QWidget,QMainWindow,QDialog
from GUI.ui_algo_pop import Ui_AlgoPopDialog
from PyQt5.QtWidgets import QFileDialog,QPlainTextEdit
from base import TaskType,cst_tools_main
from PyQt5.QtCore import QThread,pyqtSignal
import logging
import os,pathlib

class myAlgDialog(QDialog, Ui_AlgoPopDialog):
    _signal_done =pyqtSignal()
    def  __init__ (self,Logger=None):
        super(myAlgDialog, self).__init__()
        self.setupUi(self)
        self.logger=Logger
        self.data=dict()
        self.buttonBox.accepted.connect(self.saveAndHide)
        
    def setDefaultValues(self,param_dict):
        self.data.update(param_dict)
        self.fmaxLineEdit.setText(str(self.data.get('fmax',700)))
        self.fminLineEdit.setText(str(self.data.get('fmin',500)))
        self.maxFreqThresholdLineEdit.setText(str(self.data.get('endfreq',2500)))
        self.continueFreqLineEdit.setText(str(self.data.get('cfreq',650)))
        self.continueCheckBox.setChecked(bool(self.data.get('cflag',0)))

    def setValues(self):
        self.data.update({'fmax':float(self.fmaxLineEdit.text())})
        self.data.update({'fmin':float(self.fminLineEdit.text())})
        self.data.update({'endfreq':float(self.maxFreqThresholdLineEdit.text())})
        self.data.update({'cfreq':float(self.continueFreqLineEdit.text())})
        self.data.update({'cflag':int(self.continueCheckBox.isChecked())})

    def saveAndHide(self):
        self.setValues()
        self.hide()
        self._signal_done.emit()
    def getValues(self):
        return self.data