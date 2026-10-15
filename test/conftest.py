import os
from pathlib import Path

import pytest


@pytest.fixture(scope='session', autouse=True)
def keep_qt_application_alive_for_gui_modules():
    """A module fixture must not destroy QApplication while other Qt objects live."""
    import sys
    if 'PyQt5.QtWidgets' in sys.modules:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        yield app
    else:
        yield None


def pytest_addoption(parser):
    group = parser.getgroup("cst")
    group.addoption(
        "--run-cst",
        action="store_true",
        default=False,
        help="allow tests that start a local CST process",
    )
    group.addoption(
        "--cst-exe",
        default=os.environ.get("CST_TEST_EXE"),
        help="path to CST DESIGN ENVIRONMENT.exe (or set CST_TEST_EXE)",
    )


@pytest.fixture
def cst_executable(request):
    if not request.config.getoption("--run-cst"):
        pytest.skip("requires explicit --run-cst")
    configured = request.config.getoption("--cst-exe")
    if not configured:
        pytest.skip("requires --cst-exe or CST_TEST_EXE")
    executable = Path(configured)
    if not executable.is_file():
        pytest.fail(f"configured CST executable does not exist: {executable}")
    return executable
