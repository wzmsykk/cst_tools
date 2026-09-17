"""CST Tools desktop application entry point."""

import sys

from PyQt5.QtWidgets import QApplication

from GUI.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
