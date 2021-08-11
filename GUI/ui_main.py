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
        MainWindow.resize(987, 709)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.selectProjectDirButton = QtWidgets.QPushButton(self.centralwidget)
        self.selectProjectDirButton.setGeometry(QtCore.QRect(470, 70, 151, 51))
        self.selectProjectDirButton.setObjectName("selectProjectDirButton")
        self.dirNameLineEdit = QtWidgets.QLineEdit(self.centralwidget)
        self.dirNameLineEdit.setGeometry(QtCore.QRect(30, 70, 411, 51))
        self.dirNameLineEdit.setObjectName("dirNameLineEdit")
        self.RunOnlyButton = QtWidgets.QPushButton(self.centralwidget)
        self.RunOnlyButton.setGeometry(QtCore.QRect(80, 260, 171, 61))
        self.RunOnlyButton.setObjectName("RunOnlyButton")
        self.GenerateOnlyButton = QtWidgets.QPushButton(self.centralwidget)
        self.GenerateOnlyButton.setGeometry(QtCore.QRect(80, 340, 171, 61))
        self.GenerateOnlyButton.setObjectName("GenerateOnlyButton")
        self.GenerateAndRunButton = QtWidgets.QPushButton(self.centralwidget)
        self.GenerateAndRunButton.setGeometry(QtCore.QRect(80, 420, 171, 51))
        self.GenerateAndRunButton.setObjectName("GenerateAndRunButton")
        self.horizontalLayoutWidget = QtWidgets.QWidget(self.centralwidget)
        self.horizontalLayoutWidget.setGeometry(QtCore.QRect(670, 40, 271, 471))
        self.horizontalLayoutWidget.setObjectName("horizontalLayoutWidget")
        self.LogBoxLayout = QtWidgets.QHBoxLayout(self.horizontalLayoutWidget)
        self.LogBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.LogBoxLayout.setObjectName("LogBoxLayout")
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
        self.selectProjectDirButton.setText(_translate("MainWindow", "选择文件夹"))
        self.RunOnlyButton.setText(_translate("MainWindow", "仅运行"))
        self.GenerateOnlyButton.setText(_translate("MainWindow", "从cst生成项目"))
        self.GenerateAndRunButton.setText(_translate("MainWindow", "生成并运行"))

