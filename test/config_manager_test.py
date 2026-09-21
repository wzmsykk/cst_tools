import configparser
import logging
from pathlib import Path

import pytest

from csttool.globalconfmanager import GlobalConfigManager, GlobalConfmanager
from csttool.configuration import (
    CONFIG_SCHEMA_VERSION,
    ConfigurationError,
    GlobalSettings,
    ProjectSettings,
    read_ini,
)
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


def test_typed_configuration_roundtrips_and_migrates_legacy_ini():
    legacy_global = configparser.ConfigParser()
    legacy_global.read_dict(
        {
            "BASE": {
                "datadir": "data",
                "tempdir": "temp",
                "logdir": "log",
                "resultdir": "result",
            },
            "CST": {"cstver": "2022", "cstexepath": "cst.exe"},
            "PROJECT": {"currprojdir": ""},
            "superfish": {"dirpath": "", "version": ""},
        }
    )
    global_settings = GlobalSettings.from_parser(legacy_global)
    assert global_settings.schema_version == CONFIG_SCHEMA_VERSION
    assert global_settings.to_parser().getint("config", "schema_version") == 3

    project = ProjectSettings(name="typed", cells_per_wavelength=24)
    project_parser = project.to_parser()
    assert ProjectSettings.from_parser(project_parser) == project
    assert project_parser.sections() == [
        "config",
        "project",
        "paths",
        "cst",
        "execution",
        "artifacts",
        "mesh",
        "task",
    ]
    assert not project_parser.has_option("execution", "UseRemoteCalculaton")


def test_typed_configuration_rejects_future_schema_and_invalid_state():
    parser = GlobalSettings().to_parser()
    parser.set("config", "schema_version", "999")
    with pytest.raises(ConfigurationError, match="unsupported global"):
        GlobalSettings.from_parser(parser)

    with pytest.raises(ConfigurationError, match="task status"):
        ProjectSettings(name="invalid", task_status="BROKEN")


def test_global_config_defaults_live_beside_selected_config(tmp_path):
    current = tmp_path / "settings" / "current.ini"

    manager = GlobalConfigManager(
        current, logger=logging.getLogger("global-config-test")
    )

    assert manager.curr_global_cfg_path == current
    assert (current.parent / "default.ini").is_file()
    assert current.is_file()
    assert manager.settings.directories.data == Path("data")
    assert manager.conf.has_section("paths")
    assert not manager.conf.has_section("BASE")


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


def test_annotated_configuration_templates_match_typed_schema():
    root = Path(__file__).parents[1]

    global_settings = GlobalSettings.from_parser(
        read_ini(root / "config" / "default.ini")
    )
    project_settings = ProjectSettings.from_parser(
        read_ini(root / "config" / "project.example.ini")
    )

    assert global_settings.schema_version == CONFIG_SCHEMA_VERSION
    assert project_settings.schema_version == CONFIG_SCHEMA_VERSION
    assert project_settings.cells_per_wavelength == 20
    assert project_settings.digest_algorithm == "sha256"
