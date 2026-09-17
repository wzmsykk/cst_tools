from PyQt5.QtWidgets import QMainWindow
from GUI.algo_pop_window import myAlgDialog
from GUI.ui_main import Ui_MainWindow
from GUI.postprocess_dialog import myPPSDialog
from PyQt5.QtWidgets import QFileDialog, QPlainTextEdit
from base import TaskType, cst_tools_main
from PyQt5.QtCore import QObject, QThread, pyqtSignal
import logging
import pathlib


class _LogEmitter(QObject):
    message = pyqtSignal(str)


class QPlainTextEditLogger(logging.Handler):
    def __init__(self, parent):
        super().__init__()
        self.widget = QPlainTextEdit(parent)
        self.widget.setReadOnly(True)
        self._emitter = _LogEmitter()
        self._emitter.message.connect(self.widget.appendPlainText)

    def emit(self, record):
        self._emitter.message.emit(self.format(record))


class cst_tools_main_qt(QThread, cst_tools_main):
    _signal_start = pyqtSignal()
    _signal_end = pyqtSignal()
    _signal_error = pyqtSignal(str)

    def __init__(self) -> None:
        QThread.__init__(self)
        cst_tools_main.__init__(self)

    def run(self):
        self._signal_start.emit()
        try:
            self.starttask()
        except Exception as exc:
            self.logger.exception("GUI 后台任务失败")
            self._signal_error.emit(str(exc))
        finally:
            self._signal_end.emit()


class mywindow(QMainWindow, Ui_MainWindow):
    def __init__(self, maintool=None, calc_dialog=None, pps_dialog=None):
        super(mywindow, self).__init__()
        self.setupUi(self)

        self.logTextBox = QPlainTextEditLogger(self)
        self.LogBoxLayout.addWidget(self.logTextBox.widget)

        self.uiProjectDir = None
        self.uiCSTFilePath = None

        self.maintool = maintool or cst_tools_main_qt()
        self.logger = self.maintool.logger
        self.logger.addHandler(self.logTextBox)
        self.logger.info("使用PyQt5图形窗口运行模式")

        self.CalcDialogBox = calc_dialog or myAlgDialog()
        self.PPSDialogBox = pps_dialog or myPPSDialog(Logger=self.logger)

        ppslist = self.maintool.getCurrPostProcessList()
        self.PPSDialogBox.setPPSList(ppslist)
        self.setSignalNSlots()

        # DATA
        self.CalcDialogBox.setDefaultValues(self.maintool.getAlgAttrs())
        self._update_start_enabled()

    def closeEvent(self, event):
        self.logger.info("主窗口被用户关闭")
        event.accept()

    def setSignalNSlots(self):
        self.selectProjectDirButton.clicked.connect(self.read_dir)
        self.selectCSTPathButton.clicked.connect(self.read_cst)
        self.StartButton.clicked.connect(self.run)
        self.AlgSettingButton.clicked.connect(self.showCalcDialogBox)
        self.postProcessButton.clicked.connect(self.showPPSDialogBox)

        self.maintool._signal_start.connect(self.freezeAllButtons)
        self.maintool._signal_end.connect(self.unFreezeAllButtons)
        if hasattr(self.maintool, "_signal_error"):
            self.maintool._signal_error.connect(self.onRunError)

        self.CalcDialogBox._signal_done.connect(self.updateAlgSetting)
        self.PPSDialogBox._signal_done.connect(self.updatePPSSetting)

    def showCalcDialogBox(self):
        self.CalcDialogBox.show()

    def showPPSDialogBox(self):
        self.PPSDialogBox.show()

    def updateAlgSetting(self):
        self.maintool.setAlgAttrs(self.CalcDialogBox.getValues())

    def updatePPSSetting(self):
        self.maintool.setCurrPostProcessList(self.PPSDialogBox.getPPSList())

    def onRunError(self, message):
        self.logger.error("后台任务失败: %s", message)

    def read_dir(self):
        # 选取输出目录
        self.uiProjectDir = QFileDialog.getExistingDirectory(
            self, "选取文件夹", self.uiProjectDir
        )

        if not self.uiProjectDir:
            return
        self.dirNameLineEdit.setText(self.uiProjectDir)
        self.maintool.setProjectDir(self.uiProjectDir)
        self._update_start_enabled()

    def read_cst(self):
        # 选取输入CST
        initial_dir = self.uiProjectDir or str(pathlib.Path.cwd())
        self.uiCSTFilePath, ok = QFileDialog.getOpenFileName(
            self, "选取CST文件", initial_dir
        )
        if not self.uiCSTFilePath:
            return
        self.cstFilePathLineEdit.setText(self.uiCSTFilePath)
        self.maintool.setCSTFilePath(self.uiCSTFilePath)
        self._update_start_enabled()

    def _update_start_enabled(self):
        self.StartButton.setEnabled(bool(self.uiProjectDir and self.uiCSTFilePath))

    def freezeStartButtons(self):
        self.StartButton.setEnabled(False)

    def unfreezeStartButtons(self):
        self._update_start_enabled()

    def freezeAllButtons(self):
        self.selectProjectDirButton.setEnabled(False)
        self.StartButton.setEnabled(False)
        self.selectCSTPathButton.setEnabled(False)
        self.AlgSettingButton.setEnabled(False)
        self.postProcessButton.setEnabled(False)

    def unFreezeAllButtons(self):
        self.selectProjectDirButton.setEnabled(True)
        self.StartButton.setEnabled(True)
        self.selectCSTPathButton.setEnabled(True)
        self.AlgSettingButton.setEnabled(True)
        self.postProcessButton.setEnabled(True)
        self._update_start_enabled()

    def uiStartWork(self):
        self.logger.info("UI:STARTING WORK")
        self.freezeAllButtons()
        try:
            self.maintool.start()
        except Exception:
            self.unFreezeAllButtons()
            raise

    def run(self):
        if not self.uiProjectDir or not self.uiCSTFilePath:
            self.logger.error("请先选择项目目录和 CST 文件")
            self._update_start_enabled()
            return
        ctn = self.checkBox_CTN.isChecked()
        safe = self.checkBox_SAFE.isChecked()
        self.maintool.setFlags(ctn, safe)
        if self.maintool.wininit() is False:
            self.logger.error("CST 环境初始化失败")
            return
        if self.maintool.setRunInfos() == 0:
            self.logger.error("运行配置准备失败")
            return
        self.uiStartWork()

