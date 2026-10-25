"""Task-focused HOM display; checkpoint observation never submits work."""
import json
from pathlib import Path

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableView, QHeaderView, QProgressBar


class HomDisplayReader:
    """Used on the existing serial client thread, cached by project/stat identity."""
    def __init__(self):
        self.key = None
        self.value = None

    def read(self, project):
        path = Path(project).resolve() / 'save/csv/hom_scan_checkpoint.json'
        try:
            stat = path.stat()
            key = (str(path), stat.st_mtime_ns, stat.st_size)
            if self.key == key:
                return self.value
            if stat.st_size > 16 * 1024**2:
                raise ValueError('检查点超过16MiB显示读取上限')
            with path.open('rb') as stream:
                document = json.loads(stream.read(16 * 1024**2 + 1))
            modes = document['report']['modes']
            if not isinstance(modes, list) or not all(isinstance(m, dict)
                    and isinstance(m.get('values', {}), dict) for m in modes):
                raise ValueError('模式列表格式无效')
            if not isinstance(document.get('policy', {}), dict) or not isinstance(document.get('coverage', {}), dict):
                raise ValueError('扫描策略或覆盖格式无效')
            value = {'available': True, 'policy': document.get('policy', {}),
                     'coverage': document.get('coverage', {}), 'modes': modes[-5000:],
                     'total_modes': len(modes), 'pending': len(document.get('pending', [])),
                     'failed': len(document['report'].get('failed', [])),
                     'metrics_truncated': len({k for m in modes[-5000:] for k in m.get('values', {})}) > 32,
                     'signature': key, 'source': str(path)}
            self.key, self.value = key, value
            return value
        except FileNotFoundError:
            return {'available': False, 'reason': '尚无已确认模式检查点', 'source': str(path)}
        except (OSError, ValueError, KeyError, TypeError) as error:
            return {'available': False, 'reason': '已确认结果暂不可读，请查看详细运行信息',
                    'diagnostic': str(error), 'source': str(path)}


class HomModeTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.modes = []
        self.metrics = []
        self.offset = 0

    def set_modes(self, modes, total):
        self.beginResetModel()
        self.modes = modes
        self.offset = max(0, total - len(modes))
        self.metrics = sorted({str(key) for mode in modes for key in mode.get('values', {})})[:32]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.modes)

    def columnCount(self, parent=QModelIndex()):
        return 2 + len(self.metrics)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return ['序号', '频率 / MHz', *self.metrics][section]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.modes):
            return None
        mode = self.modes[index.row()]
        if role == Qt.DisplayRole:
            value = (index.row() + self.offset + 1 if index.column() == 0 else
                     mode.get('frequency') if index.column() == 1 else
                     mode.get('values', {}).get(self.metrics[index.column() - 2]))
            if isinstance(value, (int, float)):
                return f'{value:.10g}'
            return '—' if value is None else str(value)[:120]


class HomDashboard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.actions = QHBoxLayout()
        title = QLabel('HOM 扫频与已确认结果')
        self.actions.addWidget(title, 1)
        layout.addLayout(self.actions)
        self.target = QLabel('扫描目标：等待任务')
        self.coverage = QLabel('已确认覆盖：—　｜　已计算上界：—')
        self.coverageBar = QProgressBar(self)
        self.coverageBar.setRange(0, 1000)
        self.coverageBar.setValue(0)
        self.coverageBar.setFormat('等待已确认覆盖范围')
        self.coverageBar.setAccessibleName('HOM已确认频率覆盖比例')
        self.current = QLabel('当前区间：—')
        self.count = QLabel('已确认模式：0')
        self.notice = QLabel('结果来自持久检查点；运行细节请切换“详细运行信息”。')
        for label in (self.target, self.coverage, self.current, self.count, self.notice):
            label.setWordWrap(True)
            label.setTextFormat(Qt.PlainText)
            layout.addWidget(label)
            if label is self.coverage:
                layout.addWidget(self.coverageBar)
        self.table = QTableView(self)
        self.table.setAccessibleName('HOM已确认模式及后处理结果')
        self.model = HomModeTableModel(self.table)
        self.table.setModel(self.model)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        layout.addWidget(self.table, 1)
        self._project = None
        self._signature = None

    @staticmethod
    def frequency(value):
        return f'{value:g} MHz' if isinstance(value, (int, float)) else '—'

    def show_configuration(self, settings):
        try:
            start = float(settings['fmin'])
            stop = float(settings.get('endfreq', settings.get('fmax')))
        except (KeyError, ValueError, TypeError):
            return
        self.target.setText(f'配置目标：{start:g} → {stop:g} MHz（实际范围以运行检查点为准）')

    def update_snapshot(self, status):
        project = status.get('project')
        if project != self._project:
            self._project, self._signature = project, None
            self.model.set_modes([], 0)
            self.target.setText('扫描目标：等待检查点')
            self.current.setText('当前区间：—')
        self.coverageBar.setValue(0)
        self.coverageBar.setFormat('等待已确认覆盖范围')
        display = status.get('hom_display') or {}
        coverage = status.get('coverage') or display.get('coverage') or {}
        self.coverage.setText('已确认覆盖至 ' + self.frequency(coverage.get('confirmed_frontier'))
                             + '　｜　已计算上界 ' + self.frequency(coverage.get('calculated_upper')))
        count = status.get('mode_count', display.get('total_modes', 0))
        self.count.setText(f'已确认模式：{count}')
        if display.get('available'):
            policy = display.get('policy') or {}
            self.target.setText('扫描目标：' + self.frequency(policy.get('start')) + ' → '
                                + self.frequency(policy.get('stop')))
            start, stop, frontier = policy.get('start'), policy.get('stop'), coverage.get('confirmed_frontier')
            if all(isinstance(x, (int, float)) for x in (start, stop, frontier)) and stop > start:
                import math
                fraction = (frontier - start) / (stop - start)
                if math.isfinite(fraction):
                    self.coverageBar.setValue(round(1000 * min(1, max(0, fraction))))
                    self.coverageBar.setFormat('已确认频率覆盖 %p%')
            signature = display.get('signature')
            if signature is None or signature != self._signature:
                self.model.set_modes(display.get('modes', []), display.get('total_modes', 0))
                self._signature = signature
            suffix = f"待处理区间：{display.get('pending', 0)}　未解决区间：{display.get('failed', 0)}"
            if display.get('total_modes', 0) > 5000:
                suffix += '；仅显示最近5000项'
            if display.get('metrics_truncated'):
                suffix += '；仅显示前32项指标，完整结果见输出文件'
            self.notice.setText(suffix)
        else:
            text = display.get('reason', '等待已确认结果；完整运行信息位于详细页。')
            if self.model.rowCount():
                text += '；表中保留上次读取的历史结果'
            self.notice.setText(text)
        progress = status.get('last_progress') or {}
        lo, hi = progress.get('interval_lo'), progress.get('interval_hi')
        if lo is not None and hi is not None:
            label = '当前计算区间' if status.get('state') in {'RUNNING', 'PREPARING'} else '最近计算区间'
            self.current.setText(f'{label}：{self.frequency(lo)} → {self.frequency(hi)}')

    def update_progress(self, event, stage):
        if event.interval_lo is not None and event.interval_hi is not None:
            self.current.setText(f'当前计算区间：{event.interval_lo:g}–{event.interval_hi:g} MHz · {stage}')
        else:
            self.current.setText('当前计算：' + stage)
