import configparser
import logging

import pytest

from csttool.cst_installations import (
    discover_cst_installations,
    validate_cst_installation,
)
from csttool.globalconfmanager import GlobalConfmanager


def make_installation(root, version):
    executable = root / f"CST Studio Suite {version}" / "CST DESIGN ENVIRONMENT.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    return executable


def write_config(path, executable, version):
    config = configparser.ConfigParser()
    config["BASE"] = {
        "datadir": str(path.parent / "data"),
        "tempdir": str(path.parent / "temp"),
        "logdir": str(path.parent / "log"),
        "resultdir": str(path.parent / "result"),
    }
    config["CST"] = {"cstver": str(version), "cstexepath": str(executable)}
    config["PROJECT"] = {"currprojdir": ""}
    config["superfish"] = {"dirpath": "", "version": ""}
    with path.open("w", encoding="utf-8") as stream:
        config.write(stream)


def test_discovers_all_installations_newest_first(tmp_path):
    older = make_installation(tmp_path, 2022)
    newer = make_installation(tmp_path, 2026)

    found = discover_cst_installations(search_roots=[tmp_path])

    assert [(item.version, item.executable) for item in found] == [
        (2026, newer.resolve()),
        (2022, older.resolve()),
    ]


def test_validation_rejects_version_path_mismatch(tmp_path):
    executable = make_installation(tmp_path, 2025)

    with pytest.raises(ValueError, match="does not match"):
        validate_cst_installation(2024, executable)


def test_global_config_accepts_new_versions_and_persists_selection(tmp_path):
    old_executable = make_installation(tmp_path / "old", 2022)
    new_executable = make_installation(tmp_path / "new", 2026)
    config_path = tmp_path / "current.ini"
    write_config(config_path, old_executable, 2022)
    manager = GlobalConfmanager(
        configpath=config_path, logger=logging.getLogger("cst-install-test")
    )

    selected = manager.select_cst_installation(2026, new_executable)

    assert selected.version == 2026
    assert manager.checkCSTENVConfig() is True
    reloaded = configparser.ConfigParser()
    reloaded.read(config_path)
    assert reloaded["cst"]["version"] == "2026"
    assert reloaded["cst"]["executable"] == str(new_executable.resolve())
