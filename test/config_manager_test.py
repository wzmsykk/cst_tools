import configparser
import logging

from csttool.globalconfmanager import GlobalConfigManager, GlobalConfmanager
from csttool.projectconfmanager import (
    ProjectConfigManager,
    ProjectConfmanager,
    ProjectStatusError,
)


class _GlobalConfig:
    def __init__(self, root):
        self.conf = configparser.ConfigParser()
        self.conf["BASE"] = {"datadir": str(root / "data")}
        self.conf["CST"] = {"cstexepath": "", "cstver": ""}


def test_modern_config_manager_names_keep_legacy_aliases():
    assert GlobalConfmanager is GlobalConfigManager
    assert ProjectConfmanager is ProjectConfigManager
    assert str(ProjectStatusError("invalid state")) == "invalid state"


def test_global_config_defaults_live_beside_selected_config(tmp_path):
    current = tmp_path / "settings" / "current.ini"

    manager = GlobalConfigManager(
        current, logger=logging.getLogger("global-config-test")
    )

    assert manager.curr_global_cfg_path == current
    assert (current.parent / "default.ini").is_file()
    assert current.is_file()
    assert manager.conf.get("BASE", "datadir") == "./data"


def test_project_config_and_postprocess_files_use_roundtrip_io(tmp_path):
    manager = ProjectConfigManager(
        GlobalConfigManager=_GlobalConfig(tmp_path),
        logger=logging.getLogger("project-config-test"),
    )
    manager.assignProjectDir(tmp_path)
    manager.conf = manager.createNewEmptyProjectConfFile(tmp_path)
    values = [{"resultName": "frequency", "method": "Frequency", "params": {}}]

    assert manager.savePPSSettings(values) is True
    assert manager.readPPSList() == values
    assert not list(tmp_path.glob("tmp*"))

    (tmp_path / manager.ppsfilename).write_text("not-json", encoding="utf-8")
    assert manager.readPPSList() == []
