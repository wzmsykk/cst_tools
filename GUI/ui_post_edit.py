# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_post_edit.ui'
#
# Created by: PyQt5 UI code generator 5.9.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_AddComplexPostDialog(object):
    def setupUi(self, AddComplexPostDialog):
        AddComplexPostDialog.setObjectName("AddComplexPostDialog")
        AddComplexPostDialog.setEnabled(True)
        AddComplexPostDialog.resize(395, 281)
        self.buttonBox = QtWidgets.QDialogButtonBox(AddComplexPostDialog)
        self.buttonBox.setGeometry(QtCore.QRect(30, 240, 341, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.PostprocessNameLabel = QtWidgets.QLabel(AddComplexPostDialog)
        self.PostprocessNameLabel.setGeometry(QtCore.QRect(30, 20, 131, 16))
        self.PostprocessNameLabel.setObjectName("PostprocessNameLabel")
        self.resultNameEdit = QtWidgets.QLineEdit(AddComplexPostDialog)
        self.resultNameEdit.setGeometry(QtCore.QRect(100, 50, 141, 20))
        self.resultNameEdit.setObjectName("resultNameEdit")
        self.ModeIndexEdit = QtWidgets.QLineEdit(AddComplexPostDialog)
        self.ModeIndexEdit.setGeometry(QtCore.QRect(310, 180, 41, 21))
        self.ModeIndexEdit.setObjectName("ModeIndexEdit")
        self.label_4 = QtWidgets.QLabel(AddComplexPostDialog)
        self.label_4.setGeometry(QtCore.QRect(240, 180, 61, 16))
        self.label_4.setObjectName("label_4")
        self.AdvSettingframe = QtWidgets.QFrame(AddComplexPostDialog)
        self.AdvSettingframe.setEnabled(True)
        self.AdvSettingframe.setGeometry(QtCore.QRect(20, 80, 301, 61))
        self.AdvSettingframe.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.AdvSettingframe.setFrameShadow(QtWidgets.QFrame.Raised)
        self.AdvSettingframe.setObjectName("AdvSettingframe")
        self.label = QtWidgets.QLabel(self.AdvSettingframe)
        self.label.setGeometry(QtCore.QRect(10, 0, 54, 12))
        self.label.setObjectName("label")
        self.xoffsetEdit = QtWidgets.QLineEdit(self.AdvSettingframe)
        self.xoffsetEdit.setGeometry(QtCore.QRect(80, 0, 141, 20))
        self.xoffsetEdit.setObjectName("xoffsetEdit")
        self.label_5 = QtWidgets.QLabel(self.AdvSettingframe)
        self.label_5.setGeometry(QtCore.QRect(230, 0, 54, 12))
        self.label_5.setObjectName("label_5")
        self.label_2 = QtWidgets.QLabel(self.AdvSettingframe)
        self.label_2.setGeometry(QtCore.QRect(10, 30, 54, 12))
        self.label_2.setObjectName("label_2")
        self.yoffsetEdit = QtWidgets.QLineEdit(self.AdvSettingframe)
        self.yoffsetEdit.setGeometry(QtCore.QRect(80, 30, 141, 21))
        self.yoffsetEdit.setObjectName("yoffsetEdit")
        self.label_6 = QtWidgets.QLabel(self.AdvSettingframe)
        self.label_6.setGeometry(QtCore.QRect(230, 30, 54, 12))
        self.label_6.setObjectName("label_6")
        self.label_3 = QtWidgets.QLabel(AddComplexPostDialog)
        self.label_3.setGeometry(QtCore.QRect(30, 50, 71, 16))
        self.label_3.setObjectName("label_3")

        self.retranslateUi(AddComplexPostDialog)
        self.buttonBox.accepted.connect(AddComplexPostDialog.accept)
        self.buttonBox.rejected.connect(AddComplexPostDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(AddComplexPostDialog)

    def retranslateUi(self, AddComplexPostDialog):
        _translate = QtCore.QCoreApplication.translate
        AddComplexPostDialog.setWindowTitle(_translate("AddComplexPostDialog", "New"))
        self.PostprocessNameLabel.setText(_translate("AddComplexPostDialog", "DefaultName"))
        self.resultNameEdit.setText(_translate("AddComplexPostDialog", "default"))
        self.ModeIndexEdit.setText(_translate("AddComplexPostDialog", "1"))
        self.label_4.setText(_translate("AddComplexPostDialog", "Mode Index"))
        self.label.setText(_translate("AddComplexPostDialog", "x offset"))
        self.xoffsetEdit.setText(_translate("AddComplexPostDialog", "0"))
        self.label_5.setText(_translate("AddComplexPostDialog", "mm"))
        self.label_2.setText(_translate("AddComplexPostDialog", "y offset"))
        self.yoffsetEdit.setText(_translate("AddComplexPostDialog", "0"))
        self.label_6.setText(_translate("AddComplexPostDialog", "mm"))
        self.label_3.setText(_translate("AddComplexPostDialog", "resultname"))

