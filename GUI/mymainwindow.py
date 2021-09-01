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
        self.defaultAlgParamDict=None

        self.freezeStartButtons()
        self.maintool=cst_tools_main_qt()
        self.maintool.glogger.logger.addHandler(self.logTextBox)
        self.logger=self.maintool.glogger.getLogger()
        self.logger.info("使用PyQt5图形窗口运行模式")
        self.maintool.startGlobalConfig()

        
        self.setSignalNSlots()

    def translate_algdict_to_uidict(self,algdict):
        uidict={'fmin':500,'fmax':1000,'cfreq':500,'cflag':False}
        vcfreq=algdict.get('continue_flag')[1]
        vcflag=algdict.get('continue_flag')[0]
        vfmin=algdict.get('input_min')[1]
        vfmax=algdict.get('input_min')[2]

        if vcfreq:uidict.update({'cfreq':vcfreq})
        if vcflag:uidict.update({'cflag':vcflag})
        if vfmin:uidict.update({'fmin':vfmin})
        if vfmax:uidict.update({'fmax':vfmax})
        return uidict
    
    def translate_uidict_to_algdict(self,uidict):
        vcflag=uidict.get('cflag')
        vcfreq=uidict.get('cfreq')        
        vfmin=uidict.get('fmin')
        vfmax=uidict.get('fmax')
        algdict=self.defaultAlgParamDict.copy()
        continue_flag_list=algdict.get('continue_flag')
        continue_flag_list[0]=vcflag
        continue_flag_list[1]=vcfreq
        input_min_list=algdict.get('input_min')
        input_min_list[1]=vfmin
        input_min_list[2]=vfmax
        algdict.update({'continue_flag':continue_flag_list})
        algdict.update({'input_min':input_min_list})
        return algdict

    def setSignalNSlots(self):
        self.selectProjectDirButton.clicked.connect(self.read_dir)
        self.StartButton.clicked.connect(self.run)
        self.GenerateOnlyButton.clicked.connect(self.genonly)
        self.GenerateAndRunButton.clicked.connect(self.rungen)
        self.AlgSettingButton.clicked.connect(self.showCalcDialogBox)


        self.maintool._signal_start.connect(self.freezeAllButtons)
        self.maintool._signal_end.connect(self.unFreezeAllButtons)

        self.CalcDialogBox._signal_done.connect(self.updateAlgSetting)

    def showCalcDialogBox(self):
        self.CalcDialogBox.show()
    def updateAlgSetting(self):
        self.maintool.changeAlgSetting(self.translate_uidict_to_algdict(self.CalcDialogBox.createUDict()))

    def read_dir(self):
        #选取输出目录
        if self.uiProjectDir==None:
            curcwd=str(pathlib.Path(os.getcwd()))
            self.uiProjectDir=curcwd
        self.uiProjectDir = QFileDialog.getExistingDirectory(self, "选取文件夹", self.uiProjectDir)
        self.dirNameLineEdit.setText(self.uiProjectDir)
        self.maintool.setProjectDir(self.uiProjectDir)
        self.maintool.wininit()
        self.defaultAlgParamDict=self.maintool.prepareAlgorithmAndParams_Win()    
        dfd=self.translate_algdict_to_uidict(self.defaultAlgParamDict)
        print(dfd)
        self.CalcDialogBox.setDefaultValues(dfd)
        self.unfreezeStartButtons()

    def read_cst(self):
        #选取输入CST
        if self.uiProjectDir==None:
            curcwd=str(pathlib.Path(os.getcwd()))
            self.uiProjectDir=curcwd
        self.uiCSTFilePath =QFileDialog.getOpenFileName(self,"选取CST文件",self.uiProjectDir)
        self.cstFilePathLineEdit.setText(self.uiCSTFilePath)



    def freezeStartButtons(self):
        self.StartButton.setEnabled(False)

    def unfreezeStartButtons(self):
        self.StartButton.setEnabled(True)


    def freezeAllButtons(self):
        self.selectProjectDirButton.setEnabled(False)
        self.StartButton.setEnabled(False)


    def unFreezeAllButtons(self):
        self.selectProjectDirButton.setEnabled(True)
        self.StartButton.setEnabled(True)


    def uiStartWork(self):                     
        self.freezeAllButtons()
        self.maintool.createJobManager()        
        self.maintool.pretask_win()
        self.maintool.start()
        self.unFreezeAllButtons()

    def run(self):
        self.maintool.taskType=TaskType.RunFromExistingProject
        self.uiStartWork()



    
