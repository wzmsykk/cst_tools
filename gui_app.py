"""CST Tools desktop application entry point."""

import sys
import threading

from PyQt5.QtCore import QTimer, QThread
from PyQt5.QtWidgets import QApplication

from GUI.main_window import MainWindow


SMOKE_TEST_FLAG = "--smoke-test"


def main(argv=None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    smoke_test = SMOKE_TEST_FLAG in arguments
    arguments = [item for item in arguments if item != SMOKE_TEST_FLAG]
    app = QApplication(arguments)
    threading.current_thread().name = "GUI/MAIN"
    QThread.currentThread().setObjectName("GUI/MAIN")
    if smoke_test:
        window = MainWindow()  # Packaging must not restore a real user project or Runner.
    else:
        from GUI.runner_backend import RunnerBackend
        from GUI.session_store import GuiSessionStore
        window = MainWindow(engine=RunnerBackend(session_store=GuiSessionStore()))
    window.show()
    if smoke_test:
        window._close_confirmed = True
        QTimer.singleShot(0, window.close)
        QTimer.singleShot(50, app.quit)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
