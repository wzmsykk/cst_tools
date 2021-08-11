from PyQt5.QtWidgets import QApplication, QWidget,QMainWindow
from GUI.ui_main import Ui_MainWindow
from PyQt5.QtWidgets import QFileDialog,QPlainTextEdit
from base import TaskType,cst_tools_main
from PyQt5.QtCore import QThread
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
    def __init__(self) -> None:
        super(cst_tools_main_qt,self).__init__()
    def run(self):
        self.starttask()
    
class mywindow(QMainWindow, Ui_MainWindow):
    def  __init__ (self):
        super(mywindow, self).__init__()
        self.setupUi(self)


        self.logTextBox = QPlainTextEditLogger(self)
        self.LogBoxLayout.addWidget(self.logTextBox.widget)        
        self.selectProjectDirButton.clicked.connect(self.read_dir)
        self.RunOnlyButton.clicked.connect(self.runonly)
        self.GenerateOnlyButton.clicked.connect(self.genonly)
        self.GenerateAndRunButton.clicked.connect(self.rungen)
        self.uiProjectDir=None
        self.freezeStartButtons()
        self.maintool=cst_tools_main_qt()
        self.maintool.glogger.logger.addHandler(self.logTextBox)
        self.logger=self.maintool.glogger.getLogger()
        self.logger.info("使用PyQt5图形窗口运行模式")
        self.maintool.startGlobalConfig()

    def read_dir(self):
        #选取文件
        if self.uiProjectDir==None:
            curcwd=str(pathlib.Path(os.getcwd()) / 'project')
            self.uiProjectDir=curcwd
        self.uiProjectDir = QFileDialog.getExistingDirectory(self, "选取文件夹", self.uiProjectDir)
        self.dirNameLineEdit.setText(self.uiProjectDir)
        self.maintool.setProjectDir(self.uiProjectDir)
        self.unfreezeStartButtons()

    def freezeStartButtons(self):
        self.RunOnlyButton.setEnabled(False)
        self.GenerateOnlyButton.setEnabled(False)
        self.GenerateAndRunButton.setEnabled(False)  

    def unfreezeStartButtons(self):
        self.RunOnlyButton.setEnabled(True)
        self.GenerateOnlyButton.setEnabled(True)
        self.GenerateAndRunButton.setEnabled(True) 

    def freezeAllButtons(self):
        self.selectProjectDirButton.setEnabled(False)
        self.RunOnlyButton.setEnabled(False)
        self.GenerateOnlyButton.setEnabled(False)
        self.GenerateAndRunButton.setEnabled(False)

    def unFreezeAllButtons(self):
        self.selectProjectDirButton.setEnabled(True)
        self.RunOnlyButton.setEnabled(True)
        self.GenerateOnlyButton.setEnabled(True)
        self.GenerateAndRunButton.setEnabled(True)

    def uiStartWork(self):
        self.maintool.initAfterDirAndTaskTypeSet()
        self.freezeAllButtons()
        self.maintool.start()
        self.unFreezeAllButtons()

    def runonly(self):
        self.maintool.taskType=TaskType.RunFromExistingProject
        self.uiStartWork()

    def genonly(self):
        self.maintool.taskType=TaskType.GenerateProjectFromCST
        self.uiStartWork()
    def rungen(self):
        self.maintool.taskType=TaskType.GenerateAndRunProject
        self.uiStartWork()


    
