"""Post-processing configuration dialogs and Qt list model."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import QAbstractListModel, QModelIndex, Qt, pyqtSignal
from PyQt5.QtGui import QDoubleValidator, QIntValidator
from PyQt5.QtWidgets import QDialog, QFileDialog, QListView, QMessageBox

from GUI.config_models import (
    PostProcessSetting,
    decode_postprocess_document,
    encode_postprocess_document,
)
from GUI.ui_post import Ui_PostProcessSettingDialog
from GUI.ui_post_edit import Ui_AddComplexPostDialog
from GUI.theme import apply_theme, set_visual_role, style_dialog_buttons


class myPostProcessDataModel(QAbstractListModel):
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
        self.beginResetModel()
        self.pps = settings
        self.endResetModel()


class myAddPPSDialog(QDialog, Ui_AddComplexPostDialog):
    _signal_data_updated = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
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
        self.reset()
        self.buttonBox.accepted.disconnect()
        self.buttonBox.accepted.connect(self.accept)

    def reset(self):
        self.setComplexMode(False)
        self.setTargetPPS(None)
        self.data.clear()
        self.xoffsetEdit.setText("0")
        self.yoffsetEdit.setText("0")
        self.ModeIndexEdit.setText("1")
        self.resultNameEdit.setText("default")

    def setComplexMode(self, isComplex):
        self.complexMode = bool(isComplex)
        self.AdvSettingframe.setEnabled(self.complexMode)

    def setTargetPPS(self, ppsname=None):
        self.targetPPS = None if ppsname is None else str(ppsname)
        self.PostprocessNameLabel.setText(self.targetPPS or "None")
        return self.targetPPS

    def _build_setting(self):
        params = {"iModeNumber": int(self.ModeIndexEdit.text())}
        if self.complexMode:
            params["xoffset"] = float(self.xoffsetEdit.text())
            params["yoffset"] = float(self.yoffsetEdit.text())
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
        self.data = setting.to_legacy_dict()
        self._signal_data_updated.emit()
        super().accept()


class myPPSDialog(QDialog, Ui_PostProcessSettingDialog):
    _signal_done = pyqtSignal()

    def __init__(self, Logger=None) -> None:
        super().__init__()
        self.setupUi(self)
        apply_theme(self)
        style_dialog_buttons(self.buttonBox)
        self.setWindowTitle("后处理结果设置")
        self.addDialog = myAddPPSDialog()
        self.logger = Logger
        self.listModel = myPostProcessDataModel()
        self.listView.setModel(self.listModel)
        self.listView.setEditTriggers(QListView.NoEditTriggers)
        self.listView.setAlternatingRowColors(False)
        self.listView.setToolTip("本次计算将生成的后处理结果")
        set_visual_role(self.DeleteButton, "danger")
        set_visual_role(self.SaveJsonButton, "quiet")
        set_visual_role(self.LoadJsonButton, "quiet")
        self.setSignalNSlots()

    def setSignalNSlots(self):
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
            self.AddSIButton: ("Shunt_Inpedence", True),
            self.AddFreqButton: ("Frequency", False),
        }
        for button, (method, complex_mode) in actions.items():
            button.clicked.connect(
                lambda _checked=False, m=method, c=complex_mode: self.showAddDialog(m, c)
            )
        self.DeleteButton.clicked.connect(self.deleteItem)
        self.SaveJsonButton.clicked.connect(self.savePPSJson)
        self.LoadJsonButton.clicked.connect(self.loadPPSJson)
        self.addDialog._signal_data_updated.connect(self.addItem)
        self.buttonBox.accepted.connect(self.saveAndHide)

    def saveAndHide(self):
        self.hide()
        self._signal_done.emit()

    def showAddDialog(self, ppsType, isComplex):
        self.addDialog.reset()
        self.addDialog.setComplexMode(isComplex)
        self.addDialog.setTargetPPS(ppsType)
        self.addDialog.show()

    def addItem(self):
        try:
            self.listModel.append(self.addDialog.data)
        except (TypeError, ValueError) as exc:
            self._report_error("添加后处理配置失败", exc)

    def deleteItem(self):
        self.listModel.removeRow(self.listView.currentIndex().row())

    def clearAll(self):
        self.listModel.clear()

    def setPPSList(self, ppslist):
        self.listModel.replace(ppslist)

    def getPPSList(self):
        return [item.to_legacy_dict() for item in self.listModel.pps]

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
