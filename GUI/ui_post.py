# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_post.ui'
#
# Created by: PyQt5 UI code generator 5.9.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_PostProcessSettingDialog(object):
    def setupUi(self, PostProcessSettingDialog):
        PostProcessSettingDialog.setObjectName("PostProcessSettingDialog")
        PostProcessSettingDialog.resize(645, 490)
        self.buttonBox = QtWidgets.QDialogButtonBox(PostProcessSettingDialog)
        self.buttonBox.setGeometry(QtCore.QRect(180, 410, 401, 61))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.listView = QtWidgets.QListView(PostProcessSettingDialog)
        self.listView.setGeometry(QtCore.QRect(30, 20, 281, 381))
        self.listView.setObjectName("listView")
        self.DeleteButton = QtWidgets.QPushButton(PostProcessSettingDialog)
        self.DeleteButton.setGeometry(QtCore.QRect(380, 280, 231, 41))
        self.DeleteButton.setObjectName("DeleteButton")
        self.AddLossButton = QtWidgets.QPushButton(PostProcessSettingDialog)
        self.AddLossButton.setGeometry(QtCore.QRect(380, 100, 231, 41))
        self.AddLossButton.setObjectName("AddLossButton")
        self.AddROQButton = QtWidgets.QPushButton(PostProcessSettingDialog)
        self.AddROQButton.setGeometry(QtCore.QRect(380, 20, 231, 41))
        self.AddROQButton.setObjectName("AddROQButton")
        self.SaveJsonButton = QtWidgets.QPushButton(PostProcessSettingDialog)
        self.SaveJsonButton.setGeometry(QtCore.QRect(380, 320, 231, 41))
        self.SaveJsonButton.setObjectName("SaveJsonButton")
        self.LoadJsonButton = QtWidgets.QPushButton(PostProcessSettingDialog)
        self.LoadJsonButton.setGeometry(QtCore.QRect(380, 360, 231, 41))
        self.LoadJsonButton.setObjectName("LoadJsonButton")
        self.AddFreqButton = QtWidgets.QPushButton(PostProcessSettingDialog)
        self.AddFreqButton.setGeometry(QtCore.QRect(380, 140, 231, 41))
        self.AddFreqButton.setObjectName("AddFreqButton")
        self.AddQButton = QtWidgets.QPushButton(PostProcessSettingDialog)
        self.AddQButton.setGeometry(QtCore.QRect(380, 180, 231, 41))
        self.AddQButton.setObjectName("AddQButton")
        self.AddSIButton = QtWidgets.QPushButton(PostProcessSettingDialog)
        self.AddSIButton.setGeometry(QtCore.QRect(380, 60, 231, 41))
        self.AddSIButton.setObjectName("AddSIButton")
        self.AddQExtButton = QtWidgets.QPushButton(PostProcessSettingDialog)
        self.AddQExtButton.setGeometry(QtCore.QRect(380, 220, 231, 41))
        self.AddQExtButton.setObjectName("AddQExtButton")

        self.retranslateUi(PostProcessSettingDialog)
        self.buttonBox.accepted.connect(PostProcessSettingDialog.accept)
        self.buttonBox.rejected.connect(PostProcessSettingDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(PostProcessSettingDialog)

    def retranslateUi(self, PostProcessSettingDialog):
        _translate = QtCore.QCoreApplication.translate
        PostProcessSettingDialog.setWindowTitle(_translate("PostProcessSettingDialog", "后处理设置"))
        self.DeleteButton.setText(_translate("PostProcessSettingDialog", "删除选中项"))
        self.AddLossButton.setText(_translate("PostProcessSettingDialog", "添加Total Loss"))
        self.AddROQButton.setText(_translate("PostProcessSettingDialog", "添加R/Q"))
        self.SaveJsonButton.setText(_translate("PostProcessSettingDialog", "保存后处理设定到文件"))
        self.LoadJsonButton.setText(_translate("PostProcessSettingDialog", "从文件读取后处理设定"))
        self.AddFreqButton.setText(_translate("PostProcessSettingDialog", "添加Freq输出"))
        self.AddQButton.setText(_translate("PostProcessSettingDialog", "添加Q"))
        self.AddSIButton.setText(_translate("PostProcessSettingDialog", "添加Shunt Inpedence"))
        self.AddQExtButton.setText(_translate("PostProcessSettingDialog", "添加Q_ext"))

