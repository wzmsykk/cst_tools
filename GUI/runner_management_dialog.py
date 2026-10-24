"""Project-scoped Runner controls; never operates on arbitrary Python/CST processes."""
from pathlib import Path
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                            QPlainTextEdit, QPushButton)
from GUI.run_controller import RunState
from GUI.lifecycle_display import lifecycle_lines


class RunnerManagementDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window, self.controller = window, window.controller
        self.setWindowTitle('后台 Runner 管理')
        self.resize(760, 460)
        layout = QVBoxLayout(self)
        description = QLabel('仅管理当前项目后台。停止计算会等待CST安全收尾；退出后台不会关闭其他用户的CST。')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName('Runner身份、状态和诊断信息')
        layout.addWidget(self.details)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.connectButton = QPushButton('连接/启动')
        self.claimButton = QPushButton('申请控制权')
        self.stopButton = QPushButton('停止计算…')
        self.recoverButton = QPushButton('恢复检查…')
        self.shutdownButton = QPushButton('退出后台…')
        for button in (self.connectButton, self.claimButton, self.stopButton,
                       self.recoverButton, self.shutdownButton):
            row.addWidget(button)
        self.connectButton.clicked.connect(self.controller.connect_runner)
        self.claimButton.clicked.connect(self.controller.request_control)
        self.stopButton.clicked.connect(window.requestStop)
        self.recoverButton.clicked.connect(window.requestRecovery)
        self.shutdownButton.clicked.connect(self.request_shutdown)
        close = QPushButton('关闭管理窗口（后台保持不变）')
        close.clicked.connect(self.close)
        layout.addWidget(close)
        self.controller.snapshot_changed.connect(self.refresh)
        self.controller.connection_changed.connect(self.connection_changed)
        self.controller.error.connect(self.connection_changed)
        self.refresh()

    def connection_changed(self, message):
        self.feedback.setText(message)
        self.refresh()

    def refresh(self, *_):
        controller = self.controller
        status = getattr(controller.backend, 'runner_status', {})
        runtime = status.get('runtime') or {}
        local = str(Path(__file__).resolve().parents[1])
        source = runtime.get('source_root')
        match = ('一致' if Path(source).resolve() == Path(local).resolve() else '不同，请安全退出旧后台后重新连接') if source else '旧版未提供身份，不能确认与GUI一致'
        text = '\n'.join([
            f'项目：{controller.backend.project or "未选择"}',
            f'状态：{"已退出" if controller.runner_stopped else "未知" if controller.unknown else status.get("state", "等待连接")}',
            f'实例：{status.get("instance_id", "—")}',
            f'PID：{runtime.get("pid", "旧版未提供")}',
            f'后台源码：{source or "旧版未提供"}',
            f'后台Python：{runtime.get("python", "旧版未提供")}',
            f'GUI源码：{local}', f'代码位置对照：{match}',
            f'会话安全：{status.get("session_safety", "未知")}',
            f'项目状态：{status.get("project_task_status", "旧版未提供")}',
            f'运行：{status.get("run_id") or "—"}',
            f'日志：{status.get("log_directory") or "—"}',
            f'异常：{status.get("error") or "—"}',
        ] + lifecycle_lines(status))
        if text != self.details.toPlainText():
            self.details.setPlainText(text)
        project = bool(controller.backend.client)
        idle = not controller.has_active_work
        usable = project and not controller.runner_stopped and not controller.unknown and not controller.pending
        self.connectButton.setEnabled(project and not controller.pending and (idle or controller.unknown))
        self.claimButton.setEnabled(usable)
        self.stopButton.setEnabled(usable and not controller.read_only and controller.state is RunState.RUNNING)
        self.recoverButton.setEnabled(usable and idle and not controller.read_only and controller.state is RunState.RECOVERY_REQUIRED)
        self.shutdownButton.setEnabled(usable and idle and not controller.read_only and controller.state is not RunState.RECOVERY_REQUIRED)
        self.shutdownButton.setToolTip('运行中、状态未知、需要恢复或仅查看时不能退出；先停止/恢复并确认安全。')

    def request_shutdown(self):
        if self.window._confirm_action('退出后台 Runner',
                '将正常退出当前项目Runner，不强杀CST、不删除结果。\n'
                '退出后保持离线；更新程序后可点击“连接/启动”。是否继续？'):
            self.controller.request_shutdown()
            self.refresh()
