from PyQt5.QtWidgets import QApplication, QMainWindow
from GUI.algorithm_settings_dialog import AlgorithmSettingsDialog
from GUI.application_service import CstApplicationService
from GUI.run_controller import GuiRunController, RunState
from GUI.ui_main import Ui_MainWindow
from GUI.postprocess_settings_dialog import PostProcessSettingsDialog
from GUI.theme import apply_theme, set_visual_role
from PyQt5.QtWidgets import QFileDialog, QPlainTextEdit
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
import logging
import pathlib


STATE_PRESENTATION = {
    RunState.IDLE: ("等待配置", "请选择项目目录和 CST 工程"),
    RunState.READY: ("可以运行", "配置完整，等待启动"),
    RunState.RUNNING: ("正在运行", "CST 任务正在后台执行"),
    RunState.STOPPING: ("正在停止", "等待 Worker 安全保存并退出"),
    RunState.RECOVERING: ("正在恢复", "检查残留会话并完成协议收尾"),
    RunState.RECOVERY_REQUIRED: (
        "需要恢复",
        "检测到未闭合 CST 会话；恢复完成前不能重新运行",
    ),
    RunState.FAILED: ("运行失败", "检查日志后可重新运行"),
}

STAGE_PRESENTATION = {
    "": "尚未开始",
    "initializing": "初始化运行环境",
    "preparing": "准备工程副本",
    "running": "执行仿真任务",
    "stopping": "安全停止 Worker",
    "recovering": "恢复残留 CST 会话",
    "recovered": "会话恢复完成",
    "completed": "本次运行已完成",
    "interrupted": "已安全停止，可从检查点继续",
}

CST_STAGE_PRESENTATION = {
    "starting": "启动",
    "mesh": "网格生成",
    "mesh-refinement": "网格加密",
    "mesh-refinement-complete": "网格加密完成",
    "eigenmode-solver": "本征模求解",
    "postprocess": "后处理",
}


class _LogEmitter(QObject):
    message = pyqtSignal(str)


class QPlainTextEditLogger(logging.Handler):
    def __init__(self, parent):
        super().__init__()
        self.widget = QPlainTextEdit(parent)
        self.widget.setReadOnly(True)
        self._emitter = _LogEmitter()
        self._emitter.message.connect(self.widget.appendPlainText)
        self.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S")
        )

    def emit(self, record):
        try:
            self._emitter.message.emit(self.format(record))
        except Exception:
            self.handleError(record)


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(
        self,
        engine=None,
        calc_dialog=None,
        pps_dialog=None,
        controller: GuiRunController | None = None,
    ):
        super().__init__()
        self.setupUi(self)
        apply_theme(self)
        self._fit_initial_window_to_screen()
        self.setWindowTitle("CST Batch Studio")
        self.dirNameLineEdit.setReadOnly(True)
        self.dirNameLineEdit.setPlaceholderText("选择用于保存任务和结果的项目目录")
        self.cstFilePathLineEdit.setReadOnly(True)
        self.cstFilePathLineEdit.setPlaceholderText("选择作为计算模板的 CST 工程文件")
        self.workerCountSpinBox.setToolTip("默认 1 个 CST 实例；可按本机资源和许可证调高")
        self.cstBackendComboBox.setToolTip("选择启动 Worker 时使用的 CST 安装版本")
        self.refreshCstBackendsButton.setToolTip("重新扫描本机 CST 安装")
        self.StartButton.setToolTip("使用当前工程、算法与后处理设置启动任务")
        self.StopButton.setToolTip("请求 Worker 保存当前状态并通过标准流程退出")
        self.RecoverButton.setToolTip("通过标准协议关闭项目中未闭合的 Managed CST 会话")
        self.ResumeButton.setToolTip("立即使用已有项目、HOM 检查点和已确认安全快照续跑")
        set_visual_role(self.StartButton, "primary")
        set_visual_role(self.StopButton, "danger")
        set_visual_role(self.RecoverButton, "quiet")
        set_visual_role(self.AlgSettingButton, "quiet")
        set_visual_role(self.postProcessButton, "quiet")
        set_visual_role(self.clearLogButton, "quiet")
        self.pageLayout.setStretch(1, 1)
        self.workspaceSplitter.setSizes([560, 860])

        self.logTextBox = QPlainTextEditLogger(self)
        self.logTextBox.widget.document().setMaximumBlockCount(5000)
        self.logTextBox.widget.setPlaceholderText("运行日志将在这里显示…")
        self.logTextBox.widget.setAccessibleName("运行日志")
        self.LogBoxLayout.addWidget(self.logTextBox.widget)
        self.runProgressBar.setAccessibleName("运行阶段进度")

        self.uiProjectDir = None
        self.uiCSTFilePath = None
        self._cst_backend_ready = False
        self._new_run_ready = False
        self._resume_ready = False
        self._close_pending = False
        self._stage = ""

        self.service = CstApplicationService(engine)
        self.controller = controller or GuiRunController(self.service)
        self.logger = self.service.logger
        self.logger.addHandler(self.logTextBox)
        self.logger.info("使用PyQt5图形窗口运行模式")

        self.CalcDialogBox = calc_dialog or AlgorithmSettingsDialog(parent=self)
        self.PPSDialogBox = pps_dialog or PostProcessSettingsDialog(
            Logger=self.logger, parent=self
        )
        self.refreshCstBackends()

        ppslist = self.service.get_postprocess_settings()
        self.PPSDialogBox.setPPSList(ppslist)
        self.setSignalNSlots()

        # DATA
        self.CalcDialogBox.setDefaultValues(self.service.get_algorithm_settings())
        self._sync_readiness()
        self.renderRunState(self.controller.state)

    def _fit_initial_window_to_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        width = min(1480, max(self.minimumWidth(), int(available.width() * 0.90)))
        height = min(920, max(self.minimumHeight(), int(available.height() * 0.90)))
        self.resize(width, height)
        self.move(
            available.x() + max(0, (available.width() - width) // 2),
            available.y() + max(0, (available.height() - height) // 2),
        )

    def closeEvent(self, event):
        if self.controller.has_active_work:
            self._close_pending = True
            self.logger.info("主窗口关闭请求：等待后台任务标准停止")
            self.controller.request_stop()
            event.ignore()
            return
        self.logger.info("主窗口被用户关闭")
        self.logger.removeHandler(self.logTextBox)
        self.logTextBox.close()
        self.service.close_logging()
        event.accept()

    def setSignalNSlots(self):
        self.selectProjectDirButton.clicked.connect(self.read_dir)
        self.selectCSTPathButton.clicked.connect(self.read_cst)
        self.refreshCstBackendsButton.clicked.connect(self.refreshCstBackends)
        self.cstBackendComboBox.currentIndexChanged.connect(self.selectCstBackend)
        self.StartButton.clicked.connect(lambda: self.run(resume=False))
        self.ResumeButton.clicked.connect(lambda: self.run(resume=True))
        self.AlgSettingButton.clicked.connect(self.showCalcDialogBox)
        self.postProcessButton.clicked.connect(self.showPPSDialogBox)
        self.StopButton.clicked.connect(self.requestStop)
        self.RecoverButton.clicked.connect(self.requestRecovery)
        self.clearLogButton.clicked.connect(self.logTextBox.widget.clear)

        self.controller.state_changed.connect(self.renderRunState)
        self.controller.stage_changed.connect(self.renderStage)
        self.controller.progress_changed.connect(self.renderProgress)
        self.controller.error.connect(self.onRunError)
        self.controller.cst_progress.connect(self.renderCstProgress)
        self.controller.settled.connect(self._finishPendingClose)

        self.CalcDialogBox._signal_done.connect(self.updateAlgSetting)
        self.PPSDialogBox._signal_done.connect(self.updatePPSSetting)

    def showCalcDialogBox(self):
        self.CalcDialogBox.show()
        self.CalcDialogBox.raise_()
        self.CalcDialogBox.activateWindow()

    def showPPSDialogBox(self):
        self.PPSDialogBox.show()
        self.PPSDialogBox.raise_()
        self.PPSDialogBox.activateWindow()

    def updateAlgSetting(self):
        self.service.update_algorithm_settings(self.CalcDialogBox.getValues())

    def updatePPSSetting(self):
        self.service.update_postprocess_settings(self.PPSDialogBox.getPPSList())

    def onRunError(self, message):
        self.logger.error("后台任务失败: %s", message)
        self.stateDetailLabel.setText(message)
        self.statusbar.showMessage(f"运行失败：{message}")

    def renderStage(self, stage):
        self._stage = stage
        stage_text = STAGE_PRESENTATION.get(stage, stage)
        self.stageLabel.setText(stage_text)
        self.stateDetailLabel.setText(stage_text)
        self.statusbar.showMessage(stage_text)

    def renderProgress(self, current, total):
        self.runProgressBar.setRange(0, total)
        self.runProgressBar.setValue(current)
        self.runProgressBar.setFormat(f"%v / %m　{STAGE_PRESENTATION.get(self._stage, self._stage)}")

    def renderCstProgress(self, event):
        stage = CST_STAGE_PRESENTATION.get(event.stage, event.stage)
        interval = ""
        if event.interval_lo is not None and event.interval_hi is not None:
            interval = f" {event.interval_lo:g}–{event.interval_hi:g} MHz"
        pass_text = f" / {event.pass_name}" if event.pass_name else ""
        label = f"Worker {event.worker_id}{interval} · {stage}{pass_text}"
        self.stageLabel.setText(label)
        self.stateDetailLabel.setText(label)
        if event.local_percent is not None:
            self.runProgressBar.setRange(0, 100)
            self.runProgressBar.setValue(event.local_percent)
            self.runProgressBar.setFormat(
                f"当前 CST 阶段 %p%　{stage}{pass_text}"
            )
        self.statusbar.showMessage(label)

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
        self.service.select_project_directory(self.uiProjectDir)
        try:
            count = self.controller.inspect_recovery_state()
        except Exception as exc:
            self.logger.error("检查残留 CST 会话失败: %s", exc)
            self.controller.mark_recovery_required()
            count = 0
        if count:
            self.logger.warning("检测到 %d 个需要恢复的 CST 会话", count)
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
        self.service.select_cst_file(self.uiCSTFilePath)
        self._sync_readiness()

    def _sync_readiness(self):
        project_ready = bool(self.uiProjectDir and self._cst_backend_ready)
        self._new_run_ready = bool(project_ready and self.uiCSTFilePath)
        self._resume_ready = project_ready
        self.controller.set_inputs_ready(self._new_run_ready or self._resume_ready)
        self.renderRunState(self.controller.state)

    def refreshCstBackends(self):
        self.cstBackendComboBox.blockSignals(True)
        self.cstBackendComboBox.clear()
        if not self.service.supports_cst_backend_selection:
            self.cstBackendComboBox.addItem("当前固定后端", None)
            self.cstBackendComboBox.setEnabled(False)
            self.refreshCstBackendsButton.setEnabled(False)
            self._cst_backend_ready = True
            self.cstBackendComboBox.blockSignals(False)
            return
        try:
            installations = self.service.get_cst_installations()
            selected = self.service.get_selected_cst_installation()
        except Exception as exc:
            self.logger.error("扫描 CST 安装失败: %s", exc)
            installations = ()
            selected = None
        selected_index = -1
        for index, installation in enumerate(installations):
            executable = str(installation.executable)
            self.cstBackendComboBox.addItem(
                f"{installation.display_name}  ·  {executable}",
                (installation.version, executable),
            )
            if selected is not None and installation.executable == selected.executable:
                selected_index = index
        if installations:
            self.cstBackendComboBox.setCurrentIndex(
                selected_index if selected_index >= 0 else 0
            )
            if selected_index < 0:
                first = installations[0]
                try:
                    self.service.select_cst_installation(
                        first.version, str(first.executable)
                    )
                except Exception as exc:
                    self.logger.error("自动选择 CST 后端失败: %s", exc)
                    self._cst_backend_ready = False
                    self.cstBackendComboBox.blockSignals(False)
                    return
            self._cst_backend_ready = True
        else:
            self.cstBackendComboBox.addItem("未发现可用的 CST 安装", None)
            self._cst_backend_ready = False
        self.cstBackendComboBox.blockSignals(False)
        if hasattr(self, "controller"):
            self._sync_readiness()

    def selectCstBackend(self, index):
        selection = self.cstBackendComboBox.itemData(index)
        if selection is None:
            self._cst_backend_ready = False
            self._sync_readiness()
            return
        version, executable = selection
        try:
            selected = self.service.select_cst_installation(version, executable)
        except Exception as exc:
            self._cst_backend_ready = False
            self.logger.error("切换 CST 后端失败: %s", exc)
        else:
            self._cst_backend_ready = True
            self.logger.info(
                "GUI 已选择 CST %s 后端: %s",
                selected.version,
                selected.executable,
            )
        self._sync_readiness()

    def renderRunState(self, state):
        state_name = state.name.lower()
        for widget in (self.statusbar, self.stateBadge, self.runSummaryFrame):
            widget.setProperty("state", state_name)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        controls_enabled = state not in {
            RunState.RUNNING,
            RunState.STOPPING,
            RunState.RECOVERING,
            RunState.RECOVERY_REQUIRED,
        }
        for widget in (
            self.selectProjectDirButton,
            self.selectCSTPathButton,
            self.AlgSettingButton,
            self.postProcessButton,
            self.workerCountSpinBox,
        ):
            widget.setEnabled(controls_enabled)
        backend_controls_enabled = (
            controls_enabled and self.service.supports_cst_backend_selection
        )
        self.cstBackendComboBox.setEnabled(backend_controls_enabled)
        self.refreshCstBackendsButton.setEnabled(backend_controls_enabled)
        self.CalcDialogBox.setEnabled(controls_enabled)
        self.PPSDialogBox.setEnabled(controls_enabled)
        self.StartButton.setEnabled(
            controls_enabled
            and self._new_run_ready
            and state in {RunState.READY, RunState.FAILED}
        )
        self.ResumeButton.setEnabled(
            controls_enabled
            and self._resume_ready
            and state in {RunState.READY, RunState.FAILED}
        )
        self.StopButton.setEnabled(state is RunState.RUNNING)
        self.RecoverButton.setEnabled(
            bool(self.uiProjectDir)
            and (
                bool(self.controller.recovery_count)
                or state is RunState.RECOVERY_REQUIRED
            )
            and state
            in {
                RunState.IDLE,
                RunState.READY,
                RunState.FAILED,
                RunState.RECOVERY_REQUIRED,
            }
        )
        self.RecoverButton.setText(
            f"清理残留会话 ({self.controller.recovery_count})"
            if self.controller.recovery_count
            else "清理残留会话"
        )
        self.StartButton.setText(
            "重新开始新扫描" if state is RunState.FAILED else "开始新扫描"
        )
        badge, detail = STATE_PRESENTATION[state]
        self.stateBadge.setText(badge)
        if not self._stage or state in {RunState.IDLE, RunState.READY, RunState.FAILED}:
            self.stateDetailLabel.setText(detail)
        status_text = STAGE_PRESENTATION.get(self._stage, self._stage) if self._stage else detail
        self.statusbar.showMessage(status_text)

    def requestStop(self):
        if self.controller.request_stop():
            self.logger.info("用户请求安全停止当前运行")

    def requestRecovery(self):
        if self.controller.request_recovery():
            self.logger.info("用户请求清理项目中的残留 CST 会话")

    def run(self, resume=False):
        if not self.uiProjectDir or (not resume and not self.uiCSTFilePath):
            self.logger.error("新建运行需要项目目录和 CST 模板；继续运行只需已有项目")
            self._sync_readiness()
            return
        worker_count = self.workerCountSpinBox.value()
        settings = self.service.get_algorithm_settings()
        self.logger.info(
            "运行确认: project=%s, cst=%s, fmin=%s MHz, stop=%s MHz, workers=%d, background=minimized",
            self.uiProjectDir,
            self.uiCSTFilePath,
            settings.get("fmin", "?"),
            settings.get("endfreq", settings.get("fmax", "?")),
            worker_count,
        )
        if self.controller.start(bool(resume), worker_count):
            self.logger.info("本次运行使用 %d 个 CST Worker", worker_count)
            self.logger.info("UI:STARTING WORK")

