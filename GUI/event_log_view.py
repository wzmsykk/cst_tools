"""Virtualized event table and bounded details, alongside the raw log mirror."""
from collections import deque
from datetime import datetime
import json
import logging
from pathlib import Path

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QHeaderView, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSplitter, QTableView, QTabWidget, QVBoxLayout, QWidget,
    QAbstractItemView,
)
from GUI.log_view import QPlainTextEditLogger

PHASE_LABELS = {'preprocess':'预处理', 'prepare':'准备', 'solve':'求解',
                'shutdown':'退出', 'postprocess':'后处理', 'readout':'读取结果',
                'ack':'确认', 'lifecycle':'生命周期'}
STATUS_LABELS = {'applied':'已读取', 'requested':'待执行', 'started':'开始',
                 'returned':'已返回', 'returned-not-verified':'返回·未核验',
                 'returned-success':'返回成功', 'failed':'失败', 'closed':'已关闭',
                 'success':'成功', 'SUCCESS':'成功', 'unchanged':'保持不变'}


def snapshot_record(record):
    """Copy strings, not traceback frames; no parsing of human-language semantics."""
    message = record.getMessage()
    standard = logging.makeLogRecord({}).__dict__
    context = {key: str(value)[:512] for key, value in list(record.__dict__.items())
               if key not in standard and key not in {'message', 'asctime', 'exc_text'}}
    context = dict(list(context.items())[:32])
    error = logging.Formatter().formatException(record.exc_info) if record.exc_info else (record.exc_text or '')
    clipped = len(message) > 8192 or len(error) > 8192
    phase = context.get('phase', context.get('stage', '未分类'))
    task = context.get('task_id', context.get('task', context.get('job', '—')))
    event = {
        'time': datetime.fromtimestamp(record.created).strftime('%H:%M:%S'),
        'level': record.levelname, 'levelno': record.levelno,
        'phase': phase, 'task': task, 'summary': message.split('\n', 1)[0][:240],
        'message': message[:8192], 'error': error[:8192], 'context': context,
        'status': context.get('status', '错误' if record.levelno >= logging.ERROR else
                              '警告' if record.levelno >= logging.WARNING else '记录'),
        'source': f'{record.pathname}:{record.lineno} ({record.funcName})',
        'clipped': clipped, 'updates': 1,
    }
    # Only explicit progress events with complete task identity can overwrite.
    run = context.get('run_id')
    session = context.get('session_id', context.get('session'))
    task_id = context.get('task_id', context.get('task'))
    event['progress_key'] = ((run, session, task_id, phase, context.get('event'))
                             if record.levelno < logging.WARNING and run and session and task_id
                             and context.get('event') in {'CST_PROGRESS', 'WORKER_PROGRESS', 'CST_WAIT_PROGRESS'} else None)
    event['search'] = (' '.join([message[:8192], phase, task, *context.values()])).casefold()
    if context.get('action') and context.get('target'):
        action = {'parameter-set':'参数修改', 'parameter-add':'参数新增',
                  'parameter-keep':'参数保留', 'parameter-readback':'参数读回'}.get(context['action'], context['action'])
        event['summary'] = (f"{action} {context['target']}："
                            f"{context.get('before', '')} → {context.get('after', '')}")[:240]
    return event


class EventTableModel(QAbstractTableModel):
    HEADERS = ('时间', '级别', '阶段 / 任务', '摘要', '状态')
    LIMIT = 5000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self._progress = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == Qt.DisplayRole:
            level = {'INFO':'信息','DEBUG':'调试','WARNING':'警告','ERROR':'错误','CRITICAL':'严重'}.get(row['level'],row['level'])
            phase = PHASE_LABELS.get(row['phase'], row['phase'])
            return (row['time'], level, f"{phase} / {row['task']}",
                    row['summary'], STATUS_LABELS.get(row['status'], row['status']))[index.column()]
        if role == Qt.ToolTipRole:
            return row['summary']
        if role == Qt.UserRole:
            return row

    def append_events(self, batch):
        additions = []
        pending_keys = {}
        for row in batch:
            key = row['progress_key']
            if key and key in self._progress:
                pos = self._progress[key]
                row['updates'] = self.rows[pos]['updates'] + 1
                self.rows[pos] = row
                self.dataChanged.emit(self.index(pos, 0), self.index(pos, 4))
            elif key and key in pending_keys:
                pos = pending_keys[key]
                row['updates'] = additions[pos]['updates'] + 1
                additions[pos] = row
            else:
                if key:
                    pending_keys[key] = len(additions)
                additions.append(row)
        if additions:
            start = len(self.rows)
            self.beginInsertRows(QModelIndex(), start, start + len(additions) - 1)
            self.rows.extend(additions)
            self.endInsertRows()
        excess = len(self.rows) - self.LIMIT
        if excess > 0:
            self.beginRemoveRows(QModelIndex(), 0, excess - 1)
            del self.rows[:excess]
            self.endRemoveRows()
        self._progress = {row['progress_key']: i for i, row in enumerate(self.rows) if row['progress_key']}


class EventFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.minimum = logging.INFO
        self.query = self.phase = self.task = ''

    def filterAcceptsRow(self, row, parent):
        event = self.sourceModel().rows[row]
        return (event['levelno'] >= self.minimum and self.query in event['search']
                and self.phase in (event['phase'] + ' ' + PHASE_LABELS.get(event['phase'], '')).casefold()
                and self.task in event['task'].casefold())


class StructuredLogHandler(QPlainTextEditLogger):
    def __init__(self, parent):
        super().__init__(parent)
        self._events = deque()
        self._event_dropped = 0
        self._logger = None
        self.panel = QWidget(parent)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        self.level_filter = QComboBox(self.panel)
        for label, value in [('信息及以上', 20), ('警告及以上', 30), ('仅错误', 40), ('全部（含DEBUG）', 0)]:
            self.level_filter.addItem(label, value)
        self.level_filter.setAccessibleName('日志最低级别')
        self.search = QLineEdit(self.panel)
        self.search.setPlaceholderText('搜索事件或上下文')
        self.search.setAccessibleName('日志关键词搜索')
        self.phase = QLineEdit(self.panel)
        self.phase.setPlaceholderText('阶段')
        self.phase.setAccessibleName('日志阶段筛选')
        self.task = QLineEdit(self.panel)
        self.task.setPlaceholderText('任务ID')
        self.task.setAccessibleName('日志任务筛选')
        for widget in (self.level_filter, self.search, self.phase, self.task):
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.tabs = QTabWidget(self.panel)
        layout.addWidget(self.tabs)
        events_page = QWidget()
        events_layout = QVBoxLayout(events_page)
        events_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Vertical)
        events_layout.addWidget(splitter)
        self.table = QTableView()
        self.model = EventTableModel(self.table)
        self.proxy = EventFilter(self.table)
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setAccessibleName('结构化运行事件')
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for col, width in ((0, 80), (1, 85), (2, 160), (4, 85)):
            self.table.setColumnWidth(col, width)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setUndoRedoEnabled(False)
        self.details.setAccessibleName('选中事件详情')
        self.details.setPlaceholderText('选择事件查看完整消息、堆栈、任务上下文和源码位置')
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        splitter.setSizes([320, 150])
        self.tabs.addTab(events_page, '运行事件')
        self.tabs.addTab(self.widget, '原始日志（最近5000行）')
        footer = QHBoxLayout()
        self.notice = QLabel('事件缓存最多5000条；文件日志保留完整内容')
        self.notice.setWordWrap(True)
        footer.addWidget(self.notice, 1)
        self.autoScrollButton = QPushButton('自动滚动：开')
        self.autoScrollButton.setCheckable(True)
        self.autoScrollButton.setChecked(True)
        self.autoScrollButton.setAccessibleName('日志自动滚动')
        self.autoScrollButton.setToolTip('默认开启；关闭后继续接收日志但不跟随。开启时回到最新；向上阅读或选中事件时暂时暂停跟随。')
        self.autoScrollButton.toggled.connect(self.set_auto_scroll)
        footer.addWidget(self.autoScrollButton)
        self.latest = QPushButton('回到最新')
        self.latest.clicked.connect(self.go_latest)
        footer.addWidget(self.latest)
        copy = QPushButton('复制详情')
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.details.toPlainText()))
        footer.addWidget(copy)
        self.log_button = QPushButton('打开.log')
        self.json_button = QPushButton('打开JSONL')
        self.log_button.clicked.connect(lambda: self.open_file('.log'))
        self.json_button.clicked.connect(lambda: self.open_file('.jsonl'))
        self.log_button.setEnabled(False)
        self.json_button.setEnabled(False)
        footer.addWidget(self.log_button)
        footer.addWidget(self.json_button)
        self.export_button = QPushButton('导出失败日志')
        self.export_button.setAccessibleName('一键导出失败诊断日志包')
        self.export_button.setToolTip('导出当前项目的日志、CST原生输出、失败报告和回执到diagnostics；不包含模型和三维场')
        layout.addLayout(footer)
        export_actions = QHBoxLayout()
        export_actions.addStretch()
        export_actions.addWidget(self.export_button)
        layout.addLayout(export_actions)
        self.table.selectionModel().currentRowChanged.connect(self.show_details)
        self._filter_timer = QTimer(self.panel)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(150)
        self._filter_timer.timeout.connect(self.apply_filters)
        for field in (self.search, self.phase, self.task):
            field.textChanged.connect(lambda: self._filter_timer.start())
        self.level_filter.currentIndexChanged.connect(self.apply_filters)

    def set_auto_scroll(self, enabled):
        super().set_auto_scroll(enabled)
        self.autoScrollButton.setText('自动滚动：开' if self.auto_scroll else '自动滚动：关')
        if self.autoScrollButton.isChecked() != self.auto_scroll:
            self.autoScrollButton.setChecked(self.auto_scroll)
        if self.auto_scroll:
            self.go_latest()

    def go_latest(self):
        self.table.clearSelection()
        self.table.setCurrentIndex(QModelIndex())
        self.table.scrollToBottom()
        self.widget.verticalScrollBar().setValue(self.widget.verticalScrollBar().maximum())

    def bind_logger(self, logger):
        self._logger = getattr(logger, 'logger', logger)
        self.log_button.setEnabled(bool(self.file_path('.log')))
        self.json_button.setEnabled(bool(self.file_path('.jsonl')))

    def file_path(self, suffix):
        explicit = getattr(self, '_source_files', {})
        if suffix in explicit:
            return explicit[suffix]
        logger = self._logger
        while logger is not None:
            for handler in logger.handlers:
                filename = getattr(handler, 'baseFilename', None)
                if filename and Path(filename).suffix.lower() == suffix:
                    return filename
            logger = logger.parent if logger.propagate else None

    def bind_source_files(self, directory):
        self._source_files = {suffix: str(Path(directory) / ('application' + suffix))
                              for suffix in ('.log', '.jsonl')}
        self.log_button.setEnabled(True)
        self.json_button.setEnabled(True)

    def open_file(self, suffix):
        path = self.file_path(suffix)
        if path and Path(path).is_file():
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
                self.notice.setText(f'无法打开日志文件：{path}')
        else:
            self.notice.setText('日志文件尚未创建或没有配置文件输出')

    def emit(self, record):
        try:
            event = snapshot_record(record)
            with self._guard:
                if self._disposed:
                    return
                if len(self._events) >= self.MAX_PENDING:
                    self._events.popleft()
                    self._event_dropped += 1
                self._events.append(event)
            super().emit(record)
        except Exception:
            self.handleError(record)

    def flush_pending(self):
        if self._disposed:
            return
        if self.table.verticalScrollBar().isSliderDown():
            self._timer.start()
            return
        super().flush_pending()
        with self._guard:
            if self._disposed:
                return
            batch = [self._events.popleft() for _ in range(min(self.BATCH_SIZE, len(self._events)))]
            dropped, self._event_dropped = self._event_dropped, 0
        if batch:
            scroll = self.table.verticalScrollBar()
            follow = self.auto_scroll and scroll.value() >= scroll.maximum() - 1 and not self.table.currentIndex().isValid()
            previous_position = scroll.value()
            self.model.append_events(batch)
            if follow:
                self.table.scrollToBottom()
            elif not self.auto_scroll:
                scroll.setValue(previous_position)
        if dropped:
            self.notice.setText(f'界面积压省略{dropped}条事件；完整内容见文件日志')

    def apply_filters(self):
        if self._disposed:
            return
        self.proxy.minimum = self.level_filter.currentData()
        self.proxy.query = self.search.text().strip().casefold()
        self.proxy.phase = self.phase.text().strip().casefold()
        self.proxy.task = self.task.text().strip().casefold()
        self.proxy.invalidateFilter()
        self.details.clear()

    def show_details(self, current, previous=QModelIndex()):
        if self._disposed:
            return
        if not current.isValid():
            self.details.clear()
            return
        event = self.proxy.data(current, Qt.UserRole)
        text = (f"{event['time']} | {event['level']} | {event['phase']} / {event['task']}\n"
                f"源码：{event['source']}\n进度更新次数：{event['updates']}\n\n{event['message']}\n\n"
                f"上下文：\n{json.dumps(event['context'], ensure_ascii=False, indent=2)}\n\n{event['error']}")
        if event['clipped']:
            text += '\n[详情缓存截断，完整内容见文件日志]'
        self.details.setPlainText(text)

    def close(self):
        if hasattr(self, '_events'):
            with self._guard:
                self._events.clear()
        try:
            from PyQt5.QtCore import QThread
            if hasattr(self, '_filter_timer') and QThread.currentThread() == self._filter_timer.thread():
                self._filter_timer.stop()
        except RuntimeError:
            pass
        super().close()
