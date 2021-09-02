from PyQt5.QtWidgets import QApplication, QWidget,QMainWindow
from GUI.algo_pop_window import myAlgDialog
from GUI.ui_main import Ui_MainWindow
from PyQt5.QtWidgets import QFileDialog,QPlainTextEdit
from base import TaskType,cst_tools_main
from PyQt5.QtCore import QThread,pyqtSignal
import logging
import os,pathlib
class QPlainTextEditLogger(logging.Handler):
    def __init__(self, parent):
        super().__init__()
        self.widget = QPlainTextEdit(parent)
        self.widget.setReadOnly(True)    

    def emit(self, record):
        msg = self.format(record)
        self.widget.appendPlainText(msg) 
class cst_tools_main_qt(QThread,cst_tools_main):
    _signal_start =pyqtSignal()
    _signal_end =pyqtSignal()
    def __init__(self) -> None:
        super(cst_tools_main_qt,self).__init__()
    def run(self):
        self._signal_start.emit()
        self.starttask()
        self._signal_end.emit()
        
    
class mywindow(QMainWindow, Ui_MainWindow):
    def  __init__ (self):
        super(mywindow, self).__init__()
        self.setupUi(self)
        self.CalcDialogBox=myAlgDialog()

        self.logTextBox = QPlainTextEditLogger(self)
        self.LogBoxLayout.addWidget(self.logTextBox.widget)        
        
        


        self.uiProjectDir=None
        self.uiCSTFilePath=None


        self.freezeStartButtons()
        self.maintool=cst_tools_main_qt()
        self.maintool.glogger.logger.addHandler(self.logTextBox)
        self.logger=self.maintool.glogger.getLogger()
        self.logger.info("使用PyQt5图形窗口运行模式")
        
        self.setSignalNSlots()


        #DATA 
        self.CalcDialogBox.setDefaultValues(self.maintool.getAlgAttrs())    


    def setSignalNSlots(self):
        self.selectProjectDirButton.clicked.connect(self.read_dir)
        self.selectCSTPathButton.clicked.connect(self.read_cst)
        self.StartButton.clicked.connect(self.run)
        self.AlgSettingButton.clicked.connect(self.showCalcDialogBox)


        self.maintool._signal_start.connect(self.freezeAllButtons)
        self.maintool._signal_end.connect(self.unFreezeAllButtons)

        self.CalcDialogBox._signal_done.connect(self.updateAlgSetting)

    def showCalcDialogBox(self):
        self.CalcDialogBox.show()
    def updateAlgSetting(self):
        self.maintool.setAlgAttrs(self.CalcDialogBox.getValues())

    def read_dir(self):
        #选取输出目录
        self.uiProjectDir = QFileDialog.getExistingDirectory(self, "选取文件夹", self.uiProjectDir)

        if self.uiProjectDir==None or self.uiProjectDir=='':
            curcwd=str(pathlib.Path(os.getcwd()).absolute())
            self.uiProjectDir=curcwd        
        self.dirNameLineEdit.setText(self.uiProjectDir)
        self.maintool.setProjectDir(self.uiProjectDir)
        self.unfreezeStartButtons()

    def read_cst(self):
        #选取输入CST
        if self.uiProjectDir==None:
            curcwd=str(pathlib.Path(os.getcwd()))
            self.uiProjectDir=curcwd
        self.uiCSTFilePath,ok =QFileDialog.getOpenFileName(self,"选取CST文件",self.uiProjectDir)
        self.cstFilePathLineEdit.setText(self.uiCSTFilePath)
        self.maintool.setCSTFilePath(self.uiCSTFilePath)



    def freezeStartButtons(self):
        self.StartButton.setEnabled(False)

    def unfreezeStartButtons(self):
        self.StartButton.setEnabled(True)


    def freezeAllButtons(self):
        self.selectProjectDirButton.setEnabled(False)
        self.StartButton.setEnabled(False)
        self.selectCSTPathButton.setEnabled(False)
        self.AlgSettingButton.setEnabled(False)


    def unFreezeAllButtons(self):
        self.selectProjectDirButton.setEnabled(True)
        self.StartButton.setEnabled(True)
        self.selectCSTPathButton.setEnabled(True)
        self.AlgSettingButton.setEnabled(True)



    def uiStartWork(self):       
        self.logger.info('UI:STARTING WORK')              
        self.freezeAllButtons()          
        self.maintool.start()
        self.unFreezeAllButtons()

    def run(self):
        ctn=self.checkBox_CTN.isChecked()
        safe=self.checkBox_SAFE.isChecked()
        self.maintool.setFlags(ctn,safe)
        self.maintool.wininit()
        self.maintool.setRunInfos() 
        self.uiStartWork()



    
