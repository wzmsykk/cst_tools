from PyQt5.QtWidgets import QMainWindow
from GUI.algo_pop_window import myAlgDialog
from GUI.run_controller import GuiBackend, GuiRunController, RunState
from GUI.ui_main import Ui_MainWindow
from GUI.postprocess_dialog import myPPSDialog
from PyQt5.QtWidgets import QFileDialog, QPlainTextEdit, QProgressBar
from base import cst_tools_main
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
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


class mywindow(QMainWindow, Ui_MainWindow):
    def __init__(
        self,
        maintool: GuiBackend | None = None,
        calc_dialog=None,
        pps_dialog=None,
        controller: GuiRunController | None = None,
    ):
        super(mywindow, self).__init__()
        self.setupUi(self)

        self.logTextBox = QPlainTextEditLogger(self)
        self.LogBoxLayout.addWidget(self.logTextBox.widget)
        self.runProgressBar = QProgressBar(self)
        self.runProgressBar.setRange(0, 4)
        self.runProgressBar.setValue(0)
        self.runProgressBar.setTextVisible(True)
        self.statusbar.addPermanentWidget(self.runProgressBar)

        self.uiProjectDir = None
        self.uiCSTFilePath = None
        self._close_pending = False
        self._stage = ""

        self.maintool = maintool or cst_tools_main()
        self.controller = controller or GuiRunController(self.maintool)
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
        self._sync_readiness()
        self.renderRunState(self.controller.state)

    def closeEvent(self, event):
        if self.controller.has_active_work:
            self._close_pending = True
            self.logger.info("主窗口关闭请求：等待后台任务标准停止")
            self.controller.request_stop()
            event.ignore()
            return
        self.logger.info("主窗口被用户关闭")
        self.logger.removeHandler(self.logTextBox)
        event.accept()

    def setSignalNSlots(self):
        self.selectProjectDirButton.clicked.connect(self.read_dir)
        self.selectCSTPathButton.clicked.connect(self.read_cst)
        self.StartButton.clicked.connect(self.run)
        self.AlgSettingButton.clicked.connect(self.showCalcDialogBox)
        self.postProcessButton.clicked.connect(self.showPPSDialogBox)

        self.controller.state_changed.connect(self.renderRunState)
        self.controller.stage_changed.connect(self.renderStage)
        self.controller.progress_changed.connect(self.renderProgress)
        self.controller.error.connect(self.onRunError)
        self.controller.settled.connect(self._finishPendingClose)

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
        self.statusbar.showMessage(f"FAILED: {message}")

    def renderStage(self, stage):
        self._stage = stage
        self.statusbar.showMessage(f"{self.controller.state.name}: {stage}")

    def renderProgress(self, current, total):
        self.runProgressBar.setRange(0, total)
        self.runProgressBar.setValue(current)
        self.runProgressBar.setFormat(f"%v/%m {self._stage}")

    def _finishPendingClose(self):
        if self._close_pending and not self.controller.has_active_work:
            self._close_pending = False
            QTimer.singleShot(0, self.close)

    def read_dir(self):
        # 选取输出目录
        self.uiProjectDir = QFileDialog.getExistingDirectory(
            self, "选取文件夹", self.uiProjectDir
        )

        if not self.uiProjectDir:
            return
        self.dirNameLineEdit.setText(self.uiProjectDir)
        self.maintool.setProjectDir(self.uiProjectDir)
        self._sync_readiness()

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
        self._sync_readiness()

    def _sync_readiness(self):
        self.controller.set_inputs_ready(
            bool(self.uiProjectDir and self.uiCSTFilePath)
        )

    def renderRunState(self, state):
        controls_enabled = state not in {RunState.RUNNING, RunState.STOPPING}
        for widget in (
            self.selectProjectDirButton,
            self.selectCSTPathButton,
            self.AlgSettingButton,
            self.postProcessButton,
            self.workerCountSpinBox,
        ):
            widget.setEnabled(controls_enabled)
        self.StartButton.setEnabled(
            controls_enabled
            and self.controller.inputs_ready
            and state in {RunState.READY, RunState.FAILED}
        )
        suffix = f": {self._stage}" if self._stage else ""
        self.statusbar.showMessage(f"{state.name}{suffix}")

    def run(self):
        if not self.uiProjectDir or not self.uiCSTFilePath:
            self.logger.error("请先选择项目目录和 CST 文件")
            self._sync_readiness()
            return
        ctn = self.checkBox_CTN.isChecked()
        safe = self.checkBox_SAFE.isChecked()
        worker_count = self.workerCountSpinBox.value()
        if self.controller.start(ctn, safe, worker_count):
            self.logger.info("本次运行使用 %d 个 CST Worker", worker_count)
            self.logger.info("UI:STARTING WORK")

