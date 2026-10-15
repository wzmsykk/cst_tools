"""Offscreen real-GUI process used only against an already-running fake Runner."""
import argparse
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from GUI.main_window import MainWindow
from GUI.runner_backend import RunnerBackend
from GUI.run_controller import RunState


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--ready', required=True)
    args = parser.parse_args()
    app = QApplication([])
    backend = RunnerBackend()
    backend.supports_cst_backend_selection = False
    backend.select_project_directory(args.project)
    window = MainWindow(engine=backend)
    window.show()
    timer = QTimer()
    timer.timeout.connect(lambda: Path(args.ready).write_text('connected')
                          if window.controller.state is RunState.RUNNING else None)
    timer.start(100)
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
