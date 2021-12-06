# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_main.ui'
#
# Created by: PyQt5 UI code generator 5.9.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(987, 713)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.selectProjectDirButton = QtWidgets.QPushButton(self.centralwidget)
        self.selectProjectDirButton.setGeometry(QtCore.QRect(470, 70, 151, 51))
        self.selectProjectDirButton.setObjectName("selectProjectDirButton")
        self.dirNameLineEdit = QtWidgets.QLineEdit(self.centralwidget)
        self.dirNameLineEdit.setGeometry(QtCore.QRect(30, 70, 411, 51))
        self.dirNameLineEdit.setObjectName("dirNameLineEdit")
        self.StartButton = QtWidgets.QPushButton(self.centralwidget)
        self.StartButton.setGeometry(QtCore.QRect(460, 380, 171, 61))
        self.StartButton.setObjectName("StartButton")
        self.horizontalLayoutWidget = QtWidgets.QWidget(self.centralwidget)
        self.horizontalLayoutWidget.setGeometry(QtCore.QRect(670, 40, 271, 471))
        self.horizontalLayoutWidget.setObjectName("horizontalLayoutWidget")
        self.LogBoxLayout = QtWidgets.QHBoxLayout(self.horizontalLayoutWidget)
        self.LogBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.LogBoxLayout.setObjectName("LogBoxLayout")
        self.AlgSettingButton = QtWidgets.QPushButton(self.centralwidget)
        self.AlgSettingButton.setGeometry(QtCore.QRect(470, 210, 151, 61))
        self.AlgSettingButton.setObjectName("AlgSettingButton")
        self.cstFilePathLineEdit = QtWidgets.QLineEdit(self.centralwidget)
        self.cstFilePathLineEdit.setGeometry(QtCore.QRect(30, 140, 411, 51))
        self.cstFilePathLineEdit.setObjectName("cstFilePathLineEdit")
        self.selectCSTPathButton = QtWidgets.QPushButton(self.centralwidget)
        self.selectCSTPathButton.setGeometry(QtCore.QRect(470, 140, 151, 51))
        self.selectCSTPathButton.setObjectName("selectCSTPathButton")
        self.checkBox_CTN = QtWidgets.QCheckBox(self.centralwidget)
        self.checkBox_CTN.setEnabled(False)
        self.checkBox_CTN.setGeometry(QtCore.QRect(70, 250, 121, 31))
        self.checkBox_CTN.setObjectName("checkBox_CTN")
        self.checkBox_SAFE = QtWidgets.QCheckBox(self.centralwidget)
        self.checkBox_SAFE.setEnabled(False)
        self.checkBox_SAFE.setGeometry(QtCore.QRect(70, 290, 101, 21))
        self.checkBox_SAFE.setObjectName("checkBox_SAFE")
        self.postProcessButton = QtWidgets.QPushButton(self.centralwidget)
        self.postProcessButton.setGeometry(QtCore.QRect(470, 280, 151, 61))
        self.postProcessButton.setObjectName("postProcessButton")
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 987, 22))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "MainWindow"))
        self.selectProjectDirButton.setText(_translate("MainWindow", "选择项目文件夹"))
        self.StartButton.setText(_translate("MainWindow", "开始"))
        self.AlgSettingButton.setText(_translate("MainWindow", "计算设置"))
        self.selectCSTPathButton.setText(_translate("MainWindow", "选择cst文件"))
        self.checkBox_CTN.setText(_translate("MainWindow", "继续运行"))
        self.checkBox_SAFE.setText(_translate("MainWindow", "安全模式"))
        self.postProcessButton.setText(_translate("MainWindow", "后处理设置"))

