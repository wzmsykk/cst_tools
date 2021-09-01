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
        self.fmax=None
        self.fmin=None
        self.cflag=False
        self.cfreq=None
        self.buttonBox.accepted.connect(self.saveAndHide)
        
    def setDefaultValues(self,param_dict):

        self.fmax=param_dict['fmax']
        self.fmaxLineEdit.setText(str(self.fmax))
        self.fmin=param_dict['fmin']
        self.fminLineEdit.setText(str(self.fmin))
        self.cfreq=param_dict['cfreq']
        self.continueFreqLineEdit.setText(str(self.cfreq))
        self.cflag=param_dict['cflag']
        self.continueCheckBox.setTristate(self.cflag)

    def setValues(self):
        self.fmax=float(self.fmaxLineEdit.text())
        self.fmin=float(self.fminLineEdit.text())
        self.cflag=self.continueCheckBox.isTristate()
        self.cfreq=self.continueFreqLineEdit.text()

    def saveAndHide(self):
        self.setValues()
        self.hide()
        self._signal_done.emit()
    def createUDict(self):
        attr_list=['fmin','fmax','cfreq','cflag']
        udict=dict()
        for k in attr_list:
            v=getattr(self,k)
            dict.update({k:v})
        return udict