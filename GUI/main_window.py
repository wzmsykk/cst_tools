from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QLabel
from GUI.algorithm_settings_dialog import AlgorithmSettingsDialog
from GUI.application_service import CstApplicationService, ConfigurationService
from GUI.run_controller import GuiRunController, RunState
from GUI.ui_main import Ui_MainWindow
from GUI.postprocess_settings_dialog import PostProcessSettingsDialog
from GUI.theme import apply_theme, set_visual_role
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtCore import QTimer, Qt
from GUI.log_view import QPlainTextEditLogger
from GUI.event_log_view import StructuredLogHandler
from csttool.cst_progress import normalize_cst_stage
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
    "recovery-required": "需要恢复残留会话，未重新开始计算",
    "completed": "本次运行已完成",
    "interrupted": "已安全停止，可从检查点继续",
}

CST_STAGE_PRESENTATION = {
    "feature-collection": "收集模型特征",
    "tetrahedral-mesh": "四面体网格生成",
    "starting": "启动",
    "mesh": "网格生成",
    "mesh-refinement": "网格加密",
    "mesh-refinement-complete": "网格加密完成",
    "eigenmode-solver": "本征模求解",
    "postprocess": "后处理",
}

CST_MESSAGE_PRESENTATION = {
    'Collecting all features': '正在收集模型特征',
    'Mesher initialization': '正在初始化网格生成器',
    'Calculating eigenmode solution.': '正在计算本征模',
    'Creating parametric 1D results.': '正在生成参数化 1D 结果',
}


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
        self.exitFailureLabel = QLabel(self.centralwidget)
        self.exitFailureLabel.setObjectName('exitFailureLabel')
        self.exitFailureLabel.setTextFormat(Qt.PlainText)
        self.exitFailureLabel.setWordWrap(True)
        self.exitFailureLabel.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.exitFailureLabel.setAccessibleName('完整退出失败及恢复方法')
        self.exitFailureLabel.hide()
        self.pageLayout.insertWidget(1, self.exitFailureLabel)
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
        self.pageLayout.setStretch(1, 1)
        self.workspaceSplitter.setSizes([560, 860])

        self.logTextBox = StructuredLogHandler(self)
        self.logTextBox.widget.document().setMaximumBlockCount(5000)
        self.logTextBox.widget.setPlaceholderText("运行日志将在这里显示…")
        self.logTextBox.widget.setAccessibleName("运行日志")
        self.LogBoxLayout.addWidget(self.logTextBox.panel)
        self.runProgressBar.setAccessibleName("运行阶段进度")
        self.stageLabel.setTextFormat(Qt.PlainText)
        self.stageLabel.setWordWrap(True)
        self.stateDetailLabel.setTextFormat(Qt.PlainText)
        self.runSummaryLayout.setStretch(0, 1)
        self.runSummaryLayout.setStretch(1, 1)

        self.uiProjectDir = None
        self.uiCSTFilePath = None
        self._cst_backend_ready = False
        self._new_run_ready = False
        self._resume_ready = False
        self._close_pending = False
        self._close_confirmed = False
        self._confirmation_open = False
        self._stage = ""

        if engine is None:
            from GUI.runner_backend import RunnerBackend
            engine = RunnerBackend()
        self.service = (ConfigurationService(engine) if getattr(engine, 'uses_runner', False)
                        else CstApplicationService(engine))
        if controller is None and getattr(engine, 'uses_runner', False):
            from GUI.runner_controller import RunnerController
            controller = RunnerController(self.service)
        self.controller = controller or GuiRunController(self.service)
        if getattr(engine, 'uses_runner', False):
            from PyQt5.QtWidgets import QPushButton
            self.claimControlButton = QPushButton('申请控制权', self)
            self.claimControlButton.setEnabled(False)
            self.claimControlButton.setToolTip('其他窗口租约有效时会被拒绝；不会重新启动或停止计算')
            self.claimControlButton.clicked.connect(self.controller.request_control)
            self.statusBar().addPermanentWidget(self.claimControlButton)
            self.runnerManagementButton = QPushButton('后台管理', self)
            self.runnerManagementButton.clicked.connect(self.showRunnerManagement)
            self.statusBar().addPermanentWidget(self.runnerManagementButton)
        self.logger = self.service.logger
        self.logger.addHandler(self.logTextBox)
        self.logTextBox.bind_logger(self.logger)
        self.logger.debug("GUI 已初始化")

        self.CalcDialogBox = calc_dialog or AlgorithmSettingsDialog(parent=self)
        self.PPSDialogBox = pps_dialog or PostProcessSettingsDialog(
            logger=self.logger, parent=self
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
        if getattr(self.controller, 'closed', False):
            try:
                self._close_local_resources()
            except Exception as exc:
                self._exit_failed('本地界面资源关闭失败：' + str(exc) + '。后台状态未因此改变，可检查日志后重试退出。')
                event.ignore()
                return
            event.accept()
            return
        if self._confirmation_open:
            event.ignore()
            return
        if hasattr(self.controller, 'detach'):
            self._close_runner_window(event)
            return
        if not self._close_confirmed:
            if not self._confirm_action("确认退出", "确定退出 CST Batch Studio？\n如有后台任务，将先请求安全停止并等待标准收尾；不会强制结束 CST。"):
                event.ignore()
                return
            self._close_confirmed = True
        if self.controller.has_active_work:
            self._close_pending = True
            self.logger.info("窗口等待关闭：正在安全停止后台任务")
            self.controller.request_stop()
            event.ignore()
            return
        if self.controller.state is RunState.RECOVERY_REQUIRED:
            self._close_pending = False
            self._close_confirmed = False
            self.logger.error("取消窗口退出：尚未确认 CST 安全关闭，请先清理残留会话")
            self.statusbar.showMessage("退出未完成：请先清理残留会话并确认安全关闭")
            event.ignore()
            return
        self.logger.info("窗口已关闭")
        self._close_local_resources()
        event.accept()

    def _close_runner_window(self, event):
        event.ignore()
        if getattr(self.controller, 'detaching', False):
            return
        if not self._close_confirmed:
            choice = self._runner_close_choice()
            if choice == 'cancel':
                return
            if choice == 'detach':
                self._close_pending = True
                self.statusbar.showMessage('正在关闭界面：等待本地通信结束，后台保持原状态')
                self.controller.detach()
                self._finishPendingClose()
                return
            self.exitFailureLabel.hide()
            self._close_confirmed = True
        if self.controller.unknown or self.controller.read_only:
            self._exit_failed('连接或控制权未确认，未停止任务或退出后台。可重新连接/申请控制权，或选择仅关闭界面。')
            return
        if self.controller.state is RunState.RECOVERY_REQUIRED:
            self._exit_failed('后台仍需恢复，未确认完整退出。请先恢复；也可选择仅关闭界面并保留后台。')
            return
        self._close_pending = True
        if self.controller.has_active_work:
            if self.controller.pending_operation == 'shutdown':
                return
            if not getattr(self, '_close_stop_sent', False) and self.controller.state not in {RunState.STOPPING, RunState.RECOVERING}:
                self._close_stop_sent = True
                if not self.controller.request_stop():
                    self._exit_failed('停止请求未被接受，后台保持原状态。请检查连接和控制权，或选择仅关闭界面。')
            return
        if self.controller.backend.client and not self.controller.runner_stopped:
            if not self.controller.request_shutdown():
                self._exit_failed('退出后台请求未被接受，尚未释放后台所有权。请检查后台管理。')
            return
        self.controller.detach()
        self._finishPendingClose()

    def _close_local_resources(self):
        if getattr(self, '_gui_resources_closed', False):
            return
        try:
            self.logger.removeHandler(self.logTextBox)
            self.logTextBox.close()
        finally:
            self.service.close_logging()
        self._gui_resources_closed = True

    def _exit_failed(self, message):
        self._close_pending = self._close_confirmed = self._close_stop_sent = False
        self.logger.error('完整退出未完成 | reason=%s', message)
        self.stateDetailLabel.setText('完整退出未完成：' + message)
        self.statusbar.showMessage('完整退出未完成：' + message)
        self.exitFailureLabel.setText('完整退出未完成：' + message)
        self.exitFailureLabel.show()

    def _runner_close_choice(self):
        self._confirmation_open = True
        try:
            box = QMessageBox(self)
            box.setWindowTitle('选择退出方式')
            box.setText('仅关闭界面：保留后台和计算，发布目录可能继续被占用。\n完整退出：停止任务并等待 CST 收尾，然后正常退出后台及界面。\n关闭前请保存其他窗口中的操作；不会强制结束 CST。')
            cancel = box.addButton('取消', QMessageBox.RejectRole)
            background = box.addButton('仅关闭界面（保留后台）', QMessageBox.AcceptRole)
            stop = box.addButton('停止任务并退出后台及界面', QMessageBox.DestructiveRole)
            box.setDefaultButton(cancel)
            box.setEscapeButton(cancel)
            box.exec_()
            return 'detach' if box.clickedButton() is background else ('stop' if box.clickedButton() is stop else 'cancel')
        finally:
            self._confirmation_open = False

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

        self.controller.state_changed.connect(self.renderRunState)
        self.controller.stage_changed.connect(self.renderStage)
        self.controller.progress_changed.connect(self.renderProgress)
        self.controller.error.connect(self.onRunError)
        self.controller.cst_progress.connect(self.renderCstProgress)
        self.controller.settled.connect(self._finishPendingClose)
        if hasattr(self.controller, 'connection_changed'):
            self.controller.connection_changed.connect(self.connectionLabelChanged)
        if hasattr(self.controller, 'snapshot_changed'):
            self.controller.snapshot_changed.connect(self.renderRunnerSnapshot)

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
        if self._close_pending and not getattr(self.controller, 'detaching', False):
            self._exit_failed('后台操作失败：' + str(message) + '。可检查日志后恢复，或仅关闭界面。')
        self.logger.error("后台运行失败 | reason=%s", message)
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

    def renderRunnerSnapshot(self, status):
        """Restore durable task facts; displaying history never starts execution."""
        parts = [STAGE_PRESENTATION.get(status.get('phase', ''), status.get('phase', ''))]
        coverage = status.get('coverage') or {}
        frontier = coverage.get('confirmed_frontier')
        if frontier is not None:
            parts.append(f'已确认覆盖至 {frontier:g} MHz')
        if status.get('mode_count') is not None:
            parts.append(f"已接收 {status['mode_count']} 个模式")
        if status.get('total_tasks', 0):
            self.renderProgress(status.get('completed_tasks', 0), status['total_tasks'])
            parts.append(f"任务 {status.get('completed_tasks', 0)}/{status['total_tasks']}")
        self.stateDetailLabel.setText(' · '.join(part for part in parts if part))

    def renderCstProgress(self, event):
        if self.controller.state is not RunState.RUNNING:
            return
        if not hasattr(self, '_cst_observations'):
            self._cst_observations = {}
        previous = self._cst_observations.get(event.worker_id)
        if previous is not None and event.timestamp < previous.timestamp:
            return
        if (previous is not None and previous.task_id == event.task_id
                and getattr(previous, 'source', 'stdout') == 'progress.log'
                and getattr(event, 'source', 'stdout') == 'stdout'):
            return
        self._cst_observations[event.worker_id] = event
        stage_key = normalize_cst_stage(event.stage)
        stage = CST_STAGE_PRESENTATION.get(stage_key, event.stage)
        interval = ""
        if event.interval_lo is not None and event.interval_hi is not None:
            interval = f" {event.interval_lo:g}–{event.interval_hi:g} MHz"
        pass_text = f" / {event.pass_name}" if event.pass_name else ""
        source = getattr(event, 'source', 'stdout')
        label = f"Worker {event.worker_id}{interval} · {stage}{pass_text}"
        detail = CST_MESSAGE_PRESENTATION.get(event.message.strip(), event.message.strip())
        tooltip = (f"来源：{source}\n原始阶段：{event.native_header or event.stage}\n"
                   f"原始文本：{event.message}\n任务：{event.task_id}\n会话：{event.session_id}\n"
                   '百分比仅为CST报告的局部读数，不代表任务或整个扫描完成。')
        self.stageLabel.setText(label + (f'\n{detail}' if detail else ''))
        self.stateDetailLabel.setText(detail or stage)
        self.stageLabel.setToolTip(tooltip)
        self.stateDetailLabel.setToolTip(tooltip)
        self.runProgressBar.setToolTip(tooltip)
        if event.local_percent is not None:
            self.runProgressBar.setRange(0, 100)
            self.runProgressBar.setValue(event.local_percent)
            self.runProgressBar.setFormat(
                "CST 局部读数 %p%（非任务完成）"
            )
        else:
            self.runProgressBar.setRange(0, 0)
            self.runProgressBar.setFormat("CST 局部进度未知")
        self.statusbar.showMessage(label)

    def _finishPendingClose(self):
        if self._close_pending and (getattr(self.controller, 'closed', False) or (
                not getattr(self.controller, 'detaching', False) and not self.controller.has_active_work)):
            if not hasattr(self.controller, 'detach'):
                self._close_pending = False
            QTimer.singleShot(0, self.close)

    def showRunnerManagement(self):
        if not hasattr(self, '_runner_dialog'):
            from GUI.runner_management_dialog import RunnerManagementDialog
            self._runner_dialog = RunnerManagementDialog(self)
        self._runner_dialog.refresh()
        self._runner_dialog.show()
        self._runner_dialog.raise_()
        self._runner_dialog.activateWindow()

    def connectionLabelChanged(self, text):
        if hasattr(self, 'claimControlButton'):
            self.claimControlButton.setEnabled(self.service.backend.client is not None
                and not self.controller.unknown and not self.controller.pending
                and not self.controller.runner_stopped)
        directory = getattr(self.service.backend, 'log_directory', None)
        if directory:
            self.logTextBox.bind_source_files(directory)
        blocked = (getattr(self.controller, 'unknown', False), getattr(self.controller, 'read_only', False),
                   getattr(self.controller, 'runner_stopped', False))
        if getattr(self, '_runner_connection_blocked', None) != blocked:
            self.renderRunState(self.controller.state)
            self._runner_connection_blocked = blocked
        if any(blocked[:2]):
            for widget in (self.StartButton, self.ResumeButton, self.StopButton, self.RecoverButton,
                           self.selectProjectDirButton, self.selectCSTPathButton,
                           self.AlgSettingButton, self.postProcessButton, self.workerCountSpinBox,
                           self.cstBackendComboBox, self.refreshCstBackendsButton):
                widget.setEnabled(False)
        elif blocked[2]:
            for widget in (self.StartButton, self.ResumeButton, self.StopButton, self.RecoverButton):
                widget.setEnabled(False)
        self.statusbar.showMessage(text)

    def _confirm_action(self, title, message):
        self._confirmation_open = True
        try:
            return QMessageBox.question(
                self, title, message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) == QMessageBox.Yes
        finally:
            self._confirmation_open = False

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
        if state is RunState.RUNNING:
            self._cst_observations = {}
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
        if getattr(self.controller, 'runner_stopped', False):
            for widget in (self.StartButton, self.ResumeButton, self.StopButton, self.RecoverButton):
                widget.setEnabled(False)

    def requestStop(self):
        if self.controller.state is not RunState.RUNNING:
            return
        if not self._confirm_action("确认停止", "确定停止当前运行？\n将请求 Worker 安全收尾，不强制结束 CST；当前阻塞操作返回前仍需等待。\nHOM 后续应通过“继续未完成”恢复已记录的计算进度，不要从头覆盖结果。"):
            return
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
            "运行确认: project=%s, cst=%s, fmin=%s MHz, stop=%s MHz, fixed_mesh_cells=%s, mesh_convergence=%s, workers=%d, background=minimized",
            self.uiProjectDir,
            self.uiCSTFilePath,
            settings.get("fmin", "?"),
            settings.get("endfreq", settings.get("fmax", "?")),
            settings.get("mesh_cells_per_wavelength", "?") if settings.get('preprocess_modify_mesh', True) else "保持原工程（不修改）",
            settings.get("mesh_convergence_enabled", False),
            worker_count,
        )
        if self.controller.start(bool(resume), worker_count):
            self.logger.debug("GUI Worker 数量已确认 | workers=%d", worker_count)
            self.logger.info("GUI 已提交运行请求 | workers=%d", worker_count)

