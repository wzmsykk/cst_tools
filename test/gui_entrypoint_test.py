import ast
from pathlib import Path

import gui_app


def test_gui_entrypoint_has_explicit_smoke_mode_and_no_import_side_effect():
    assert gui_app.SMOKE_TEST_FLAG == "--smoke-test"
    assert callable(gui_app.main)


def test_pyinstaller_spec_uses_project_relative_paths_and_required_resources():
    spec = Path("gui_app.spec").read_text(encoding="utf-8")
    tree = ast.parse(spec)
    assert tree is not None
    assert "SPECPATH" in spec
    assert "Desktop\\cst_tools" not in spec
    assert "'data'" in spec
    assert "'default.ini'" in spec
    assert "console=False" in spec
    assert "'pytest'" in spec
    assert "'sphinx'" in spec


def test_launch_scripts_use_the_single_gui_entrypoint():
    assert "gui_app.py" in Path("win.bat").read_text(encoding="utf-8")
    assert "gui_app.spec" in Path("pack.bat").read_text(encoding="utf-8")
