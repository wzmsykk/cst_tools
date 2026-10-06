"""Post-processing configuration dialogs and Qt list model."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt5.QtCore import QAbstractListModel, QModelIndex, Qt, pyqtSignal
from PyQt5.QtGui import QDoubleValidator, QIntValidator
from PyQt5.QtWidgets import (
    QDialog,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from GUI.config_models import (
    PostProcessSetting,
    decode_postprocess_document,
    encode_postprocess_document,
)
from GUI.ui_post import Ui_PostProcessSettingDialog
from GUI.ui_post_edit import Ui_AddComplexPostDialog
from GUI.theme import apply_theme, set_visual_role, style_dialog_buttons


class PostProcessListModel(QAbstractListModel):
    def __init__(self, pps=None) -> None:
        super().__init__()
        self.pps: list[PostProcessSetting] = []
        if pps:
            self.replace(pps)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.pps):
            return None
        if role == Qt.DisplayRole:
            return self.pps[index.row()].display_text
        if role == Qt.UserRole:
            return self.pps[index.row()]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.pps)

    def getData(self, row):
        return self.pps[row]

    def append(self, data):
        setting = (
            data
            if isinstance(data, PostProcessSetting)
            else PostProcessSetting.from_mapping(data)
        )
        if any(item.result_name == setting.result_name for item in self.pps):
            raise ValueError(f"后处理结果名称重复: {setting.result_name}")
        row = len(self.pps)
        self.beginInsertRows(QModelIndex(), row, row)
        self.pps.append(setting)
        self.endInsertRows()

    def removeRows(self, row, count, parent=QModelIndex()) -> bool:
        if parent.isValid() or count < 1 or row < 0 or row + count > len(self.pps):
            return False
        self.beginRemoveRows(parent, row, row + count - 1)
        del self.pps[row : row + count]
        self.endRemoveRows()
        return True

    def removeRow(self, row, parent=QModelIndex()) -> bool:
        return self.removeRows(row, 1, parent)

    def clear(self):
        self.beginResetModel()
        self.pps.clear()
        self.endResetModel()

    def replace(self, values):
        settings = [
            item
            if isinstance(item, PostProcessSetting)
            else PostProcessSetting.from_mapping(item)
            for item in values
        ]
        self._ensure_unique(settings)
        self.beginResetModel()
        self.pps = settings
        self.endResetModel()

    def replaceRow(self, row, data) -> bool:
        if not 0 <= row < len(self.pps):
            return False
        setting = (
            data
            if isinstance(data, PostProcessSetting)
            else PostProcessSetting.from_mapping(data)
        )
        if any(
            index != row and item.result_name == setting.result_name
            for index, item in enumerate(self.pps)
        ):
            raise ValueError(f"后处理结果名称重复: {setting.result_name}")
        self.pps[row] = setting
        model_index = self.index(row, 0)
        self.dataChanged.emit(
            model_index, model_index, [Qt.DisplayRole, Qt.UserRole]
        )
        return True

    def set_integration_axis(self, axis):
        axis = str(axis).strip().lower()
        if axis not in {"x", "y", "z"}:
            raise ValueError("积分轴必须是 X、Y 或 Z")
        updates = []
        for row, setting in enumerate(self.pps):
            base = setting.method.removesuffix("_All")
            if base in {"R_over_Q", "Shunt_Impedance"}:
                payload = setting.to_backend_payload()
                payload["params"]["axis"] = axis
                updates.append((row, PostProcessSetting.from_mapping(payload)))
        for row, setting in updates:
            self.replaceRow(row, setting)
        return len(updates)

    @staticmethod
    def _ensure_unique(settings):
        names = [item.result_name for item in settings]
        if len(names) != len(set(names)):
            raise ValueError("后处理结果名称不能重复")


class AddPostProcessDialog(QDialog, Ui_AddComplexPostDialog):
    _signal_data_updated = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        apply_theme(self)
        style_dialog_buttons(self.buttonBox)
        self.setWindowTitle("新增后处理结果")
        self.resultNameEdit.setPlaceholderText("用于结果文件与汇总表的唯一名称")
        set_visual_role(self.buttonBox.button(self.buttonBox.Ok), "primary")
        self.complexMode = False
        self.targetPPS = None
        self.data = {}
        self.ModeIndexEdit.setValidator(QIntValidator(1, 999999, self))
        self.xoffsetEdit.setValidator(QDoubleValidator(self))
        self.yoffsetEdit.setValidator(QDoubleValidator(self))
        self.zoffsetEdit.setValidator(QDoubleValidator(self))
        for index, axis in enumerate(("x", "y", "z")):
            self.axisComboBox.setItemData(index, axis)
        self.axisComboBox.setCurrentIndex(2)
        self.axisComboBox.currentIndexChanged.connect(self._sync_axis_offset)
        self.reset()
        self._install_responsive_layout()
        self.buttonBox.accepted.disconnect()
        self.buttonBox.accepted.connect(self.accept)

    def _install_responsive_layout(self):
        self.setMinimumSize(520, 440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)
        layout.addWidget(self.PostprocessNameLabel)
        result_row = QHBoxLayout()
        result_row.addWidget(self.label_3)
        result_row.addWidget(self.resultNameEdit, 1)
        layout.addLayout(result_row)
        advanced = QGridLayout(self.AdvSettingframe)
        advanced.setContentsMargins(14, 12, 14, 12)
        advanced.addWidget(self.axisLabel, 0, 0)
        advanced.addWidget(self.axisComboBox, 0, 1, 1, 2)
        advanced.addWidget(self.label, 1, 0)
        advanced.addWidget(self.xoffsetEdit, 1, 1)
        advanced.addWidget(self.label_5, 1, 2)
        advanced.addWidget(self.label_2, 2, 0)
        advanced.addWidget(self.yoffsetEdit, 2, 1)
        advanced.addWidget(self.label_6, 2, 2)
        advanced.addWidget(self.zoffsetLabel, 3, 0)
        advanced.addWidget(self.zoffsetEdit, 3, 1)
        advanced.addWidget(self.zoffsetUnitLabel, 3, 2)
        advanced.setColumnStretch(1, 1)
        layout.addWidget(self.AdvSettingframe)
        mode_row = QHBoxLayout()
        mode_row.addStretch(1)
        mode_row.addWidget(self.label_4)
        mode_row.addWidget(self.ModeIndexEdit)
        layout.addLayout(mode_row)
        layout.addStretch(1)
        layout.addWidget(self.buttonBox)

    def reset(self):
        self.setComplexMode(False)
        self.setTargetPPS(None)
        self.data.clear()
        self.xoffsetEdit.setText("0")
        self.yoffsetEdit.setText("0")
        self.zoffsetEdit.setText("0")
        self.axisComboBox.setCurrentIndex(2)
        self.ModeIndexEdit.setText("1")
        self.resultNameEdit.setText("default")

    def setComplexMode(self, isComplex):
        self.complexMode = bool(isComplex)
        self.AdvSettingframe.setEnabled(self.complexMode)
        self._sync_axis_offset()

    def _sync_axis_offset(self):
        for name, editor in {
            "x": self.xoffsetEdit,
            "y": self.yoffsetEdit,
            "z": self.zoffsetEdit,
        }.items():
            editor.setEnabled(self.complexMode)

    def setTargetPPS(self, ppsname=None):
        self.targetPPS = None if ppsname is None else str(ppsname)
        self.PostprocessNameLabel.setText(self.targetPPS or "None")
        return self.targetPPS

    def load_setting(self, setting: PostProcessSetting):
        self.reset()
        self.setTargetPPS(setting.method)
        base = setting.method[:-4] if setting.method.endswith("_All") else setting.method
        self.setComplexMode(base in {"R_over_Q", "Shunt_Impedance"})
        self.resultNameEdit.setText(setting.result_name)
        self.ModeIndexEdit.setText(str(setting.params.get("iModeNumber", 1)))
        self.xoffsetEdit.setText(str(setting.params.get("xoffset", 0)))
        self.yoffsetEdit.setText(str(setting.params.get("yoffset", 0)))
        self.zoffsetEdit.setText(str(setting.params.get("zoffset", 0)))
        axis = str(setting.params.get("axis", "z")).lower()
        self.axisComboBox.setCurrentIndex({"x": 0, "y": 1, "z": 2}[axis])
        self._sync_axis_offset()

    def _build_setting(self):
        params = {"iModeNumber": int(self.ModeIndexEdit.text())}
        if self.complexMode:
            params["axis"] = self.axisComboBox.currentData()
            params["xoffset"] = float(self.xoffsetEdit.text())
            params["yoffset"] = float(self.yoffsetEdit.text())
            params["zoffset"] = float(self.zoffsetEdit.text())
        return PostProcessSetting.from_mapping(
            {
                "resultName": self.resultNameEdit.text(),
                "method": self.targetPPS,
                "params": params,
            }
        )
    def accept(self):
        try:
            setting = self._build_setting()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "后处理设置无效", str(exc))
            return
        self.data = setting.to_backend_payload()
        self._signal_data_updated.emit()
        super().accept()


class PostProcessSettingsDialog(QDialog, Ui_PostProcessSettingDialog):
    _signal_done = pyqtSignal()

    def __init__(self, logger: logging.Logger | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        apply_theme(self)
        style_dialog_buttons(self.buttonBox)
        self.setWindowTitle("后处理结果设置")
        self.addDialog = AddPostProcessDialog(parent=self)
        self.logger = logger
        self.listModel = PostProcessListModel()
        self._committed_settings = []
        self._editing_row = None
        self.listView.setModel(self.listModel)
        self.listView.setEditTriggers(QListView.NoEditTriggers)
        self.listView.setAlternatingRowColors(False)
        self.listView.setToolTip("本次计算将生成的后处理结果")
        set_visual_role(self.DeleteButton, "danger")
        set_visual_role(self.SaveJsonButton, "quiet")
        set_visual_role(self.LoadJsonButton, "quiet")
        self._install_responsive_layout()
        self.buttonBox.accepted.disconnect()
        self.buttonBox.rejected.disconnect()
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.setSignalNSlots()

    def _install_responsive_layout(self):
        self.resize(980, 620)
        self.setMinimumSize(780, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        content = QHBoxLayout()
        content.setSpacing(18)
        list_column = QVBoxLayout()
        list_column.addWidget(QLabel("已配置结果", self))
        list_column.addWidget(self.listView, 1)
        list_column.addWidget(self.DeleteButton)
        axis_row = QHBoxLayout()
        axis_row.addWidget(QLabel("统一积分轴", self))
        self.batchAxisComboBox = QComboBox(self)
        self.batchAxisComboBox.setObjectName("batchAxisComboBox")
        for axis in ("x", "y", "z"):
            self.batchAxisComboBox.addItem(f"{axis.upper()} 轴", axis)
        self.batchAxisComboBox.setCurrentIndex(2)
        axis_row.addWidget(self.batchAxisComboBox)
        self.ApplyAxisButton = QPushButton("统一修改", self)
        self.ApplyAxisButton.setAutoDefault(False)
        self.ApplyAxisButton.setObjectName("ApplyAxisButton")
        self.ApplyAxisButton.setToolTip("修改全部 R/Q 和分流阻抗的积分轴，保留所有偏移值")
        axis_row.addWidget(self.ApplyAxisButton)
        list_column.addLayout(axis_row)
        self.batchAxisStatusLabel = QLabel("适用于全部 R/Q 和分流阻抗结果", self)
        self.batchAxisStatusLabel.setWordWrap(True)
        list_column.addWidget(self.batchAxisStatusLabel)
        content.addLayout(list_column, 1)
        actions = QVBoxLayout()
        actions.addWidget(QLabel("添加结果", self))
        grid = QGridLayout()
        buttons = (
            self.AddROQButton,
            self.AddSIButton,
            self.AddLossButton,
            self.AddFreqButton,
            self.AddQButton,
            self.AddQExtButton,
            self.AddLossButton_Enclosure,
            self.AddLossButton_Volume,
            self.AddLossButton_Surface,
            self.AddQButton_Enclosure,
            self.AddQButton_Volume,
            self.AddQButton_Surface,
        )
        for index, button in enumerate(buttons):
            grid.addWidget(button, index // 2, index % 2)
        actions.addLayout(grid)
        actions.addStretch(1)
        files = QHBoxLayout()
        files.addWidget(self.LoadJsonButton)
        files.addWidget(self.SaveJsonButton)
        actions.addLayout(files)
        content.addLayout(actions, 2)
        layout.addLayout(content, 1)
        layout.addWidget(self.buttonBox)

    def setSignalNSlots(self):
        self.listView.doubleClicked.connect(self.editItem)
        actions = {
            self.AddROQButton: ("R_over_Q", True),
            self.AddQButton: ("Q_Factor", False),
            self.AddQExtButton: ("Q_Ext", False),
            self.AddLossButton: ("Total_Loss", False),
            self.AddLossButton_Enclosure: ("Loss_Enclosure", False),
            self.AddLossButton_Volume: ("Loss_Volume", False),
            self.AddLossButton_Surface: ("Loss_Surface", False),
            self.AddQButton_Enclosure: ("Q_Enclosure", False),
            self.AddQButton_Volume: ("Q_Volume", False),
            self.AddQButton_Surface: ("Q_Surface", False),
            self.AddSIButton: ("Shunt_Impedance", True),
            self.AddFreqButton: ("Frequency", False),
        }
        for button, (method, complex_mode) in actions.items():
            button.clicked.connect(
                lambda _checked=False, m=method, c=complex_mode: self.showAddDialog(m, c)
            )
        self.DeleteButton.clicked.connect(self.deleteItem)
        self.ApplyAxisButton.clicked.connect(self.applyIntegrationAxis)
        self.SaveJsonButton.clicked.connect(self.savePPSJson)
        self.LoadJsonButton.clicked.connect(self.loadPPSJson)
        self.addDialog._signal_data_updated.connect(self.addItem)
    def accept(self):
        self._committed_settings = list(self.listModel.pps)
        self._signal_done.emit()
        super().accept()

    def reject(self):
        self.listModel.replace(self._committed_settings)
        super().reject()

    def showAddDialog(self, ppsType, isComplex):
        self._editing_row = None
        self.addDialog.reset()
        self.addDialog.setComplexMode(isComplex)
        self.addDialog.setTargetPPS(ppsType)
        self.addDialog.show()

    def editItem(self, index=None):
        index = index or self.listView.currentIndex()
        if not index.isValid():
            return
        self._editing_row = index.row()
        self.addDialog.load_setting(self.listModel.getData(index.row()))
        self.addDialog.show()

    def addItem(self):
        try:
            if self._editing_row is None:
                self.listModel.append(self.addDialog.data)
            else:
                self.listModel.replaceRow(self._editing_row, self.addDialog.data)
                self._editing_row = None
        except (TypeError, ValueError) as exc:
            self._report_error("添加后处理配置失败", exc)

    def deleteItem(self):
        self.listModel.removeRow(self.listView.currentIndex().row())

    def applyIntegrationAxis(self):
        axis = self.batchAxisComboBox.currentData()
        count = self.listModel.set_integration_axis(axis)
        self.batchAxisStatusLabel.setText(
            f"已将 {count} 项结果统一为 {axis.upper()} 轴，偏移值保持不变"
            if count else "没有可修改的 R/Q 或分流阻抗结果"
        )

    def clearAll(self):
        self.listModel.clear()

    def setPPSList(self, ppslist):
        self.listModel.replace(ppslist)
        self._committed_settings = list(self.listModel.pps)

    def getPPSList(self):
        return [item.to_backend_payload() for item in self.listModel.pps]

    def _report_error(self, title, error):
        if self.logger is not None:
            self.logger.error("%s: %s", title, error)
        QMessageBox.warning(self, title, str(error))

    def savePPSJson(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "选取保存位置",
            filter="JSON(*.json);;所有文件(*.*)",
            initialFilter="JSON(*.json)",
        )
        if not path:
            return False
        try:
            document = encode_postprocess_document(self.listModel.pps)
            Path(path).write_text(
                json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return True
        except (OSError, TypeError, ValueError) as exc:
            self._report_error("保存后处理配置失败", exc)
            return False

    def loadPPSJson(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选取JSON位置",
            filter="JSON(*.json);;所有文件(*.*)",
            initialFilter="JSON(*.json)",
        )
        if not path:
            return False
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
            settings = decode_postprocess_document(document)
            self.listModel.replace(settings)
            if self.logger is not None:
                self.logger.info("读取后处理配置成功")
            return True
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self._report_error("读取后处理配置失败", exc)
            return False
