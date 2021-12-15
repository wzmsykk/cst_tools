from PyQt5.QtWidgets import QDialog, QMainWindow, QListView
from GUI.ui_post import Ui_PostProcessSettingDialog
from GUI.ui_post_edit import Ui_AddComplexPostDialog
from PyQt5.QtCore import QAbstractListModel
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QFileDialog
import json


class myPostProcessDataModel(QAbstractListModel):
    def __init__(self, pps=None) -> None:
        super(myPostProcessDataModel, self).__init__()
        self.pps = pps or []

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            # See below for the data structure.
            text, altdata = self.pps[index.row()]
            # Return the todo text only.
            return text

    def clear(self):
        self.pps.clear()

    def rowCount(self, index) -> int:
        return len(self.pps)

    def getData(self, row):
        return self.pps[row]

    def append(self, data):
        self.pps.append(data)

    def removeRow(self, row: int) -> bool:
        try:
            self.pps.pop(row)
        except IndexError:
            return False
        return True

    def insertRow(self, row: int, data) -> bool:
        try:
            self.pps.insert(row, data)
        except IndexError:
            return False
        return True


class myAddPPSDialog(QDialog, Ui_AddComplexPostDialog):

    _signal_data_updated = pyqtSignal()

    def __init__(self) -> None:
        super(myAddPPSDialog, self).__init__()
        self.setupUi(self)
        self.complexMode = False
        self.targetPPS = None
        self.data = {}
        self.reset()
        self.accepted.connect(self.saveData)

    def reset(self):
        self.setComplexMode(False)
        self.setTargetPPS(None)
        self.data.clear()
        self.xoffsetEdit.setText("0")
        self.yoffsetEdit.setText("0")
        self.ModeIndexEdit.setText("1")
        self.resultNameEdit.setText("default")

    def setComplexMode(self, isComplex):
        self.complexMode = isComplex
        if isComplex:
            self.AdvSettingframe.setEnabled(True)
        else:
            self.AdvSettingframe.setEnabled(False)

    def setTargetPPS(self, ppsname=None):
        if ppsname == None:
            self.targetPPS = None
            self.PostprocessNameLabel.setText("None")
            return self.targetPPS
        else:
            self.targetPPS = str(ppsname)
            self.PostprocessNameLabel.setText(str(ppsname))
            return self.targetPPS

    def saveData(self):
        self.data.clear()
        ndat = {}
        paramdict = {}
        ndat["resultName"] = self.resultNameEdit.text()
        ndat["method"] = self.PostprocessNameLabel.text()
        paramdict["iModeNumber"] = int(self.ModeIndexEdit.text())
        if self.complexMode:
            paramdict["xoffset"] = float(self.xoffsetEdit.text())
            paramdict["yoffset"] = float(self.yoffsetEdit.text())
        ndat["params"] = paramdict
        self.data.update(ndat)
        self._signal_data_updated.emit()

    def loadData(self):
        pass


class myPPSDialog(QDialog, Ui_PostProcessSettingDialog):
    _signal_done = pyqtSignal()

    def __init__(self, Logger=None) -> None:
        super(myPPSDialog, self).__init__()
        self.setupUi(self)
        self.addDialog = myAddPPSDialog()
        self.logger = Logger
        self.datalist = []
        self.listModel = myPostProcessDataModel()
        for item in self.datalist:

            self.listModel.append((item, None))
        self.listModel.layoutChanged.emit()
        self.listView.setModel(self.listModel)
        self.listView.setEditTriggers(QListView.NoEditTriggers)
        self.setSignalNSlots()

    def setSignalNSlots(self):
        self.listView.clicked.connect(self.listItemClicked)
        self.DeleteButton.clicked.connect(self.deleteItem)
        self.AddROQButton.clicked.connect(self.addROQ)
        self.AddQButton.clicked.connect(self.addQ)
        self.AddQExtButton.clicked.connect(self.addQ_Ext)
        self.AddLossButton.clicked.connect(self.addTL)
        self.AddLossButton_Enclosure.clicked.connect(self.addLE)
        self.AddLossButton_Volume.clicked.connect(self.addLV)
        self.AddLossButton_Surface.clicked.connect(self.addLS)
        self.AddQButton_Enclosure.clicked.connect(self.addQE)
        self.AddQButton_Volume.clicked.connect(self.addQV)
        self.AddQButton_Surface.clicked.connect(self.addQS)
        self.AddSIButton.clicked.connect(self.addSI)
        self.AddFreqButton.clicked.connect(self.addFQ)
        self.SaveJsonButton.clicked.connect(self.savePPSJson)
        self.LoadJsonButton.clicked.connect(self.loadPPSJson)
        self.addDialog._signal_data_updated.connect(self.addItem)
        self.buttonBox.accepted.connect(self.saveAndHide)

    def saveAndHide(self):
        self.hide()
        self._signal_done.emit()

    def addROQ(self):
        self.showAddDialog("R_over_Q", True)

    def addSI(self):
        self.showAddDialog("Shunt_Inpedence", True)

    def addQ(self):
        self.showAddDialog("Q_Factor", False)

    def addQ_Ext(self):
        self.showAddDialog("Q_Ext", False)

    def addTL(self):
        self.showAddDialog("Total_Loss", False)

    def addLE(self):
        self.showAddDialog("Loss_Enclosure", False)

    def addLV(self):
        self.showAddDialog("Loss_Volume", False)

    def addLS(self):
        self.showAddDialog("Loss_Surface", False)

    def addQE(self):
        self.showAddDialog("Q_Enclosure", False)

    def addQV(self):
        self.showAddDialog("Q_Volume", False)

    def addQS(self):
        self.showAddDialog("Q_Surface", False)

    def addTE(self):
        self.showAddDialog("Total_Energy", False)

    def addFQ(self):
        self.showAddDialog("Frequency", False)

    def showAddDialog(self, ppsType, isComplex):
        self.addDialog.reset()
        self.addDialog.setComplexMode(isComplex)
        self.addDialog.setTargetPPS(ppsType)
        self.addDialog.show()

    def editItem(self):
        index = self.listView.currentIndex()
        print(self.listModel.getData(index.row()))

    def __addItem(self, idata):
        if idata:
            resname = idata["resultName"]
            data = (resname, idata.copy())
        else:
            data = None

        index = self.listView.currentIndex()
        # self.listModel.insertRow(index.row(),data)
        self.listModel.append(data)
        self.listModel.layoutChanged.emit()

    def addItem(self):
        idata = self.addDialog.data
        self.__addItem(idata)

    def deleteItem(self):
        index = self.listView.currentIndex()
        self.listModel.removeRow(index.row())
        self.listModel.layoutChanged.emit()

    def clearAll(self):
        self.listModel.clear()
        self.listModel.layoutChanged.emit()

    def listItemClicked(self, qModelIndex):
        print("Index %d clicked" % qModelIndex.row())
        print(self.listModel.getData(qModelIndex.row()))

    def setPPSList(self, ppslist):
        for item in ppslist:
            self.__addItem(item)

    def getPPSList(self):
        ppsdata = []
        for text, data in self.listModel.pps:
            ppsdata.append(data)
        return ppsdata

    def savePPSJson(self):
        filt = "所有文件(*.*);;JSON(*.json);;TXT(*.txt)"
        jsonsavePath, Ok = QFileDialog.getSaveFileName(
            self, "选取保存位置", filter=filt, initialFilter="JSON(*.json)"
        )
        lst = []

        for name, item in self.listModel.pps:
            lst.append(item)
        try:
            fp = open(jsonsavePath, "w")
            json.dump(lst, fp)
            fp.close()
            return True
        except:
            return False

    def loadPPSJson(self):
        filt = "所有文件(*.*);;JSON(*.json);;TXT(*.txt)"
        jsonsavePath, Ok = QFileDialog.getOpenFileName(
            self, "选取JSON位置", filter=filt, initialFilter="JSON(*.json)"
        )
        try:
            fp = open(jsonsavePath, "r")
            lst = json.load(fp)
            for item in lst:
                self.__addItem(item)
            self.logger.error("读取JSON成功")
            return True
        except:
            self.logger.error("读取JSON失败")
            return False
