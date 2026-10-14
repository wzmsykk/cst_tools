"""Offscreen GUI layout receipt, never propagate Qt test settings to CST."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFontDatabase
from GUI.algorithm_settings_dialog import AlgorithmSettingsDialog

app=QApplication([])
QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc'))
dialog=AlgorithmSettingsDialog()
dialog.setDefaultValues({'fmin':780,'fmax':850,'endfreq':1000,'mesh_cells_per_wavelength':8})
dialog.vacuumDomainCheckBox.setChecked(True)
dialog.vacuumDomainConfigEdit.setText('D:/project/vacuum-domain.json')
dialog.resize(680,720)
dialog.show();app.processEvents()
root=ROOT/'artifacts/gui-vacuum-domain';root.mkdir(exist_ok=True)
assert dialog.grab().save(str(root/'settings.png'))
print(root/'settings.png')
