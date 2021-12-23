import sys
from pathlib import Path

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        base_path=Path(base_path)
    except Exception:
        base_path = Path(".").absolute()
    return base_path / relative_path

