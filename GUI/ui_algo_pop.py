# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_algo_pop.ui'
#
# Created by: PyQt5 UI code generator 5.9.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_AlgoPopDialog(object):
    def setupUi(self, AlgoPopDialog):
        AlgoPopDialog.setObjectName("AlgoPopDialog")
        AlgoPopDialog.resize(570, 329)
        self.buttonBox = QtWidgets.QDialogButtonBox(AlgoPopDialog)
        self.buttonBox.setGeometry(QtCore.QRect(90, 280, 341, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.continueCheckBox = QtWidgets.QCheckBox(AlgoPopDialog)
        self.continueCheckBox.setGeometry(QtCore.QRect(40, 130, 281, 31))
        self.continueCheckBox.setObjectName("continueCheckBox")
        self.continueFreqLineEdit = QtWidgets.QLineEdit(AlgoPopDialog)
        self.continueFreqLineEdit.setGeometry(QtCore.QRect(120, 160, 261, 31))
        self.continueFreqLineEdit.setObjectName("continueFreqLineEdit")
        self.fminlabel = QtWidgets.QLabel(AlgoPopDialog)
        self.fminlabel.setGeometry(QtCore.QRect(40, 40, 71, 31))
        self.fminlabel.setObjectName("fminlabel")
        self.fminLineEdit = QtWidgets.QLineEdit(AlgoPopDialog)
        self.fminLineEdit.setGeometry(QtCore.QRect(120, 40, 261, 31))
        self.fminLineEdit.setObjectName("fminLineEdit")
        self.fmaxlabel = QtWidgets.QLabel(AlgoPopDialog)
        self.fmaxlabel.setGeometry(QtCore.QRect(40, 90, 54, 12))
        self.fmaxlabel.setObjectName("fmaxlabel")
        self.fmaxLineEdit = QtWidgets.QLineEdit(AlgoPopDialog)
        self.fmaxLineEdit.setGeometry(QtCore.QRect(120, 80, 261, 31))
        self.fmaxLineEdit.setObjectName("fmaxLineEdit")
        self.label = QtWidgets.QLabel(AlgoPopDialog)
        self.label.setGeometry(QtCore.QRect(400, 50, 54, 12))
        self.label.setObjectName("label")
        self.label_2 = QtWidgets.QLabel(AlgoPopDialog)
        self.label_2.setGeometry(QtCore.QRect(400, 90, 54, 12))
        self.label_2.setObjectName("label_2")
        self.dstFreqLabel = QtWidgets.QLabel(AlgoPopDialog)
        self.dstFreqLabel.setGeometry(QtCore.QRect(40, 230, 91, 16))
        self.dstFreqLabel.setObjectName("dstFreqLabel")
        self.label_3 = QtWidgets.QLabel(AlgoPopDialog)
        self.label_3.setGeometry(QtCore.QRect(400, 230, 54, 12))
        self.label_3.setObjectName("label_3")
        self.maxFreqThresholdLineEdit = QtWidgets.QLineEdit(AlgoPopDialog)
        self.maxFreqThresholdLineEdit.setGeometry(QtCore.QRect(120, 220, 261, 31))
        self.maxFreqThresholdLineEdit.setObjectName("maxFreqThresholdLineEdit")

        self.retranslateUi(AlgoPopDialog)
        self.buttonBox.accepted.connect(AlgoPopDialog.accept)
        self.buttonBox.rejected.connect(AlgoPopDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(AlgoPopDialog)

    def retranslateUi(self, AlgoPopDialog):
        _translate = QtCore.QCoreApplication.translate
        AlgoPopDialog.setWindowTitle(_translate("AlgoPopDialog", "算法设置"))
        self.continueCheckBox.setText(_translate("AlgoPopDialog", "从某一频率继续"))
        self.fminlabel.setText(_translate("AlgoPopDialog", "fmin"))
        self.fmaxlabel.setText(_translate("AlgoPopDialog", "fmax"))
        self.label.setText(_translate("AlgoPopDialog", "Mhz"))
        self.label_2.setText(_translate("AlgoPopDialog", "Mhz"))
        self.dstFreqLabel.setText(_translate("AlgoPopDialog", "扫描频率上限"))
        self.label_3.setText(_translate("AlgoPopDialog", "Mhz"))

