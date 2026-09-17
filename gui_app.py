"""CST Tools desktop application entry point."""

import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from GUI.main_window import MainWindow


SMOKE_TEST_FLAG = "--smoke-test"


def main(argv=None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    smoke_test = SMOKE_TEST_FLAG in arguments
    arguments = [item for item in arguments if item != SMOKE_TEST_FLAG]
    app = QApplication(arguments)
    window = MainWindow()
    window.show()
    if smoke_test:
        QTimer.singleShot(0, window.close)
        QTimer.singleShot(50, app.quit)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
