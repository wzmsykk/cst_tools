import logging

from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QLineEdit, QPushButton, QFileDialog, QHBoxLayout, QScrollArea, QWidget,
)
from GUI.ui_algo_pop import Ui_AlgoPopDialog
from GUI.config_models import AlgorithmSettings
from GUI.theme import apply_theme, style_dialog_buttons
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QDoubleValidator, QIntValidator


class AlgorithmSettingsDialog(QDialog, Ui_AlgoPopDialog):
    _signal_done = pyqtSignal()

    def __init__(self, logger: logging.Logger | None = None, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        apply_theme(self)
        style_dialog_buttons(self.buttonBox)
        self.setWindowTitle("扫描与算法设置")
        self.fminLineEdit.setPlaceholderText("扫描目标下限")
        self.fmaxLineEdit.setPlaceholderText("首个求解窗口上限")
        self.maxFreqThresholdLineEdit.setPlaceholderText("扫描目标上限")
        for label, editor, description in (
            (self.fminlabel, self.fminLineEdit, "扫描目标下限（fmin）：整体扫描的起始频率。"),
            (self.fmaxlabel, self.fmaxLineEdit, "首个求解窗口上限（fmax）：与扫描目标下限共同定义首次求解区间，不是整体扫描终点。"),
            (self.dstFreqLabel, self.maxFreqThresholdLineEdit, "扫描目标上限（endfreq）：整体扫描的终止频率；失败恢复探测窗口可能临时超出此值。"),
        ):
            label.setBuddy(editor)
            label.setWordWrap(True)
            editor.setAccessibleName(label.text())
            editor.setToolTip(description)
            label.setToolTip(description)
        self.meshCellsLineEdit.setPlaceholderText("例如 20")
        self.logger = logger
        self.data = dict()
        self._committed_data = {}
        validator = QDoubleValidator(self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        for editor in (
            self.fmaxLineEdit,
            self.fminLineEdit,
            self.maxFreqThresholdLineEdit,
        ):
            editor.setValidator(validator)
        self.meshCellsLineEdit.setValidator(QIntValidator(1, 999999, self))
        self.preserveMeshCheckBox = QCheckBox("预处理不修改 mesh（保留工程网格设置）", self)
        self.preserveMeshCheckBox.setToolTip("不写入cell或mesh设置；仍执行HOM参数绑定和重建，不保证保留已有网格数据。")
        self.preserveMeshCheckBox.toggled.connect(self._set_preserve_mesh)
        self.meshConvergenceCheckBox = QCheckBox("运行前执行 Mesh 收敛分析", self)
        self.meshConvergenceStartSpinBox = QSpinBox(self)
        self.meshConvergenceStopSpinBox = QSpinBox(self)
        self.meshConvergenceStepSpinBox = QSpinBox(self)
        for editor in (
            self.meshConvergenceStartSpinBox,
            self.meshConvergenceStopSpinBox,
            self.meshConvergenceStepSpinBox,
        ):
            editor.setRange(1, 999999)
        self.meshConvergenceToleranceSpinBox = QDoubleSpinBox(self)
        self.meshConvergenceToleranceSpinBox.setRange(0.001, 99.999)
        self.meshConvergenceToleranceSpinBox.setDecimals(3)
        self.meshConvergenceToleranceSpinBox.setSuffix(" %")
        self._convergence_editors = (
            self.meshConvergenceStartSpinBox,
            self.meshConvergenceStopSpinBox,
            self.meshConvergenceStepSpinBox,
            self.meshConvergenceToleranceSpinBox,
        )
        self.meshConvergenceCheckBox.toggled.connect(
            self._set_convergence_controls_enabled
        )
        self.vacuumDomainCheckBox = QCheckBox('可选：工程前提预检与真空域掩码登记',self)
        self.vacuumDomainConfigEdit = QLineEdit(self)
        self.vacuumDomainConfigEdit.setAccessibleName('真空域设置JSON路径')
        self.vacuumDomainBrowseButton = QPushButton('选择JSON…',self)
        self.vacuumDomainBrowseButton.clicked.connect(self._select_domain_config)
        self.vacuumDomainCheckBox.toggled.connect(self._set_domain_controls_enabled)
        self._set_domain_controls_enabled(False)
        self._install_responsive_layout()
        self.buttonBox.accepted.disconnect()
        self.buttonBox.rejected.disconnect()
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _install_responsive_layout(self):
        self.setMinimumSize(620, 680)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)
        outer_layout = layout
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)
        fields = QGridLayout()
        fields.setHorizontalSpacing(12)
        fields.setVerticalSpacing(14)
        rows = (
            (self.fminlabel, self.fminLineEdit, self.label),
            (self.fmaxlabel, self.fmaxLineEdit, self.label_2),
            (self.dstFreqLabel, self.maxFreqThresholdLineEdit, self.label_3),
            (self.meshCellsLabel, self.meshCellsLineEdit, None),
        )
        for row, (label, editor, unit) in enumerate(rows):
            fields.addWidget(label, row, 0)
            fields.addWidget(editor, row, 1)
            if unit is not None:
                fields.addWidget(unit, row, 2)
        fields.setColumnStretch(1, 1)
        layout.addLayout(fields)
        frequency_hint = QLabel("先计算目标下限至首个求解窗口上限，再逐窗扫描至目标上限。", self)
        frequency_hint.setWordWrap(True)
        layout.addWidget(frequency_hint)
        layout.addWidget(self.preserveMeshCheckBox)
        mesh_hint = QLabel("勾选后保留网格密度、类型及自适应设置；仍会重建工程。", self)
        mesh_hint.setWordWrap(True)
        layout.addWidget(mesh_hint)
        layout.addWidget(self.meshConvergenceCheckBox)
        convergence_fields = QGridLayout()
        convergence_rows = (
            ("起始单元数", self.meshConvergenceStartSpinBox),
            ("最大单元数", self.meshConvergenceStopSpinBox),
            ("递增步长", self.meshConvergenceStepSpinBox),
            ("结果变化容差", self.meshConvergenceToleranceSpinBox),
        )
        for row, (text, editor) in enumerate(convergence_rows):
            convergence_fields.addWidget(QLabel(text, self), row, 0)
            convergence_fields.addWidget(editor, row, 1)
        layout.addLayout(convergence_fields)
        layout.addWidget(self.vacuumDomainCheckBox)
        domain_row = QHBoxLayout()
        domain_label = QLabel('域设置文件',self)
        domain_label.setBuddy(self.vacuumDomainConfigEdit)
        domain_row.addWidget(domain_label)
        domain_row.addWidget(self.vacuumDomainConfigEdit,1)
        domain_row.addWidget(self.vacuumDomainBrowseButton)
        layout.addLayout(domain_row)
        hint = QLabel('默认关闭，仅支持单Worker、PEC背景封闭真空腔。运行前预检；正常退出后登记。'
                      '增加E场导出耗时，不自动匹配或合并HOM。',self)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        outer_layout.addWidget(self.buttonBox)

    def _select_domain_config(self):
        path,_ = QFileDialog.getOpenFileName(self,'选择真空域设置',self.vacuumDomainConfigEdit.text(),'JSON (*.json)')
        if path:
            self.vacuumDomainConfigEdit.setText(path)

    def _set_preserve_mesh(self, preserve):
        self.meshCellsLineEdit.setEnabled(not preserve)
        self.meshConvergenceCheckBox.setEnabled(not preserve)
        if preserve:
            self.meshConvergenceCheckBox.setChecked(False)
            self._set_convergence_controls_enabled(False)

    def _set_domain_controls_enabled(self,enabled):
        self.vacuumDomainConfigEdit.setEnabled(enabled)
        self.vacuumDomainBrowseButton.setEnabled(enabled)

    def setDefaultValues(self, param_dict):
        self.data = AlgorithmSettings.from_mapping(param_dict).to_backend_payload()
        self._committed_data = dict(self.data)
        self._load_fields(self.data)

    def _load_fields(self, values):
        self.data = dict(values)
        self.fmaxLineEdit.setText(str(self.data.get("fmax", 700)))
        self.fminLineEdit.setText(str(self.data.get("fmin", 500)))
        self.maxFreqThresholdLineEdit.setText(str(self.data.get("endfreq", 2500)))
        self.meshCellsLineEdit.setText(
            str(self.data.get("mesh_cells_per_wavelength", 20))
        )
        self.meshConvergenceCheckBox.setChecked(
            bool(self.data.get("mesh_convergence_enabled", False))
        )
        self.meshConvergenceStartSpinBox.setValue(
            int(self.data.get("mesh_convergence_start", 10))
        )
        self.meshConvergenceStopSpinBox.setValue(
            int(self.data.get("mesh_convergence_stop", 30))
        )
        self.meshConvergenceStepSpinBox.setValue(
            int(self.data.get("mesh_convergence_step", 5))
        )
        self.meshConvergenceToleranceSpinBox.setValue(
            float(self.data.get("mesh_convergence_tolerance", 0.01)) * 100
        )
        self._set_convergence_controls_enabled(
            self.meshConvergenceCheckBox.isChecked()
        )
        self.preserveMeshCheckBox.setChecked(not self.data.get('preprocess_modify_mesh', True))
        self._set_preserve_mesh(self.preserveMeshCheckBox.isChecked())
        self.vacuumDomainCheckBox.setChecked(bool(self.data.get('vacuum_domain_enabled',False)))
        self.vacuumDomainConfigEdit.setText(self.data.get('vacuum_domain_config',''))
        self._set_domain_controls_enabled(self.vacuumDomainCheckBox.isChecked())

    def _set_convergence_controls_enabled(self, enabled):
        for editor in self._convergence_editors:
            editor.setEnabled(bool(enabled))

    def setValues(self):
        settings = AlgorithmSettings.from_mapping(
            {
                "fmax": self.fmaxLineEdit.text(),
                "fmin": self.fminLineEdit.text(),
                "endfreq": self.maxFreqThresholdLineEdit.text(),
                "mesh_cells_per_wavelength": self.meshCellsLineEdit.text(),
                "preprocess_modify_mesh": not self.preserveMeshCheckBox.isChecked(),
                "mesh_convergence_enabled": self.meshConvergenceCheckBox.isChecked(),
                "mesh_convergence_start": self.meshConvergenceStartSpinBox.value(),
                "mesh_convergence_stop": self.meshConvergenceStopSpinBox.value(),
                "mesh_convergence_step": self.meshConvergenceStepSpinBox.value(),
                "mesh_convergence_tolerance": (
                    self.meshConvergenceToleranceSpinBox.value() / 100
                ),
                'vacuum_domain_enabled':self.vacuumDomainCheckBox.isChecked(),
                'vacuum_domain_config':self.vacuumDomainConfigEdit.text(),
            }
        )
        if settings.vacuum_domain_enabled:
            from csttool.configuration import read_json
            from csttool.vacuum_domain_registry import validate_managed_domain_options
            validate_managed_domain_options(read_json(settings.vacuum_domain_config))
        self.data = settings.to_backend_payload()

    def accept(self):
        try:
            self.setValues()
        except (TypeError, ValueError, OSError, KeyError) as exc:
            QMessageBox.warning(self, "算法设置无效", str(exc))
            return
        self._committed_data = dict(self.data)
        self._signal_done.emit()
        super().accept()

    def reject(self):
        if self._committed_data:
            self._load_fields(self._committed_data)
        super().reject()

    def getValues(self):
        return dict(self.data)
