import configparser
import logging
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from csttool.globalconfmanager import GlobalConfigManager
from csttool.configuration import (
    CONFIG_SCHEMA_VERSION,
    ConfigurationError,
    GlobalSettings,
    ProjectSettings,
    read_ini,
    write_ini_atomic,
)
from csttool.projectconfmanager import (
    ProjectConfigManager,
    ProjectStatusError,
)


class _GlobalConfig:
    def __init__(self, root):
        self.conf = configparser.ConfigParser()
        self.conf["BASE"] = {"datadir": str(root / "data")}
        self.conf["CST"] = {"cstexepath": "", "cstver": ""}
        self.settings = GlobalSettings.from_parser(self.conf)


def test_config_manager_exposes_modern_names():
    assert GlobalConfigManager.__name__ == "GlobalConfigManager"
    assert ProjectConfigManager.__name__ == "ProjectConfigManager"
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
    manager.select_project_directory(tmp_path)
    manager.settings = manager.createNewEmptyProjectConfFile(tmp_path)
    values = [{"resultName": "frequency", "method": "Frequency", "params": {}}]

    assert manager.savePPSSettings(values) is True
    assert manager.readPPSList() == values
    assert not list(tmp_path.glob("tmp*"))

    (tmp_path / manager.ppsfilename).write_text("not-json", encoding="utf-8")
    assert manager.readPPSList() == []


@pytest.mark.parametrize('modify_mesh', [True, False])
def test_new_project_pipeline_keeps_typed_settings(tmp_path, monkeypatch, modify_mesh):
    destination = tmp_path / 'project'
    destination.mkdir()
    source = tmp_path / 'source.cst'
    source.write_bytes(b'model')
    manager = ProjectConfigManager(GlobalConfigManager=_GlobalConfig(tmp_path))
    manager.select_project_directory(destination)
    manager.select_input_project(source)
    observed = []

    def preprocess(settings, projectDir, savejsonpath, **kwargs):
        assert isinstance(settings, ProjectSettings)
        observed.append(settings)
        assert kwargs.get('modify_mesh', True) == modify_mesh
        (projectDir / savejsonpath).write_text('[]', encoding='utf-8')
        return projectDir / settings.cst_filename

    monkeypatch.setattr(manager, '_preprocess_cst_project', preprocess)
    assert manager.prepare_project(mesh_cells_per_wavelength=25, modify_mesh=modify_mesh)
    assert manager.settings.fixed_mesh == modify_mesh
    assert manager.settings.cells_per_wavelength == 25
    assert manager.settings.cst_filename == Path('source.cst')
    assert len(observed) == 1
    assert ProjectSettings.from_parser(read_ini(destination / 'project.ini')) == manager.settings


@pytest.mark.parametrize('repair', [False, True])
def test_missing_project_file_is_validation_failure(tmp_path, repair):
    manager = ProjectConfigManager(GlobalConfigManager=_GlobalConfig(tmp_path))
    manager.select_project_directory(tmp_path)
    manager.createNewEmptyProjectConfFile(tmp_path)
    check = (manager._ProjectConfigManager__checkAndRepairProject if repair
             else manager._ProjectConfigManager__checkProjectStatus)
    with pytest.raises(ProjectStatusError, match="CST 模型文件"):
        check()


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


@pytest.mark.parametrize("status", ["READY", "DONE", "INTERRUPTED"])
@pytest.mark.parametrize("filename", [None, Path("missing.cst"), Path("directory.cst")])
def test_existing_project_requires_model_file(tmp_path, status, filename):
    manager = ProjectConfigManager(_GlobalConfig(tmp_path))
    manager.select_project_directory(tmp_path)
    (tmp_path / "directory.cst").mkdir()
    write_ini_atomic(tmp_path / "project.ini", ProjectSettings(
        name="invalid", task_status=status, cst_filename=filename
    ).to_parser())
    before = (tmp_path / "project.ini").read_bytes()
    manager.ready = True

    with pytest.raises(ProjectStatusError, match="CST 模型文件"):
        manager.prepare_project(startFromExisted=True)

    assert not manager.is_ready()
    assert (tmp_path / "project.ini").read_bytes() == before


def test_preprocess_failure_can_retry_with_current_installation(tmp_path, monkeypatch):
    global_config = _GlobalConfig(tmp_path)
    global_config.settings = GlobalSettings()
    manager = ProjectConfigManager(global_config)
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "source.cst"
    source.write_bytes(b"original model")
    source.chmod(source.stat().st_mode & ~stat.S_IWRITE)
    manager.select_project_directory(project)
    manager.select_input_project(source)
    selected = Path("selected-cst.exe")
    global_config.settings = replace(global_config.settings, cst=replace(
        global_config.settings.cst, executable=selected
    ))
    attempts = []

    class Preprocessor:
        def __init__(self, executable, *args, **kwargs):
            assert executable == selected

        def preprocess(self, source_project, candidate, jsonpath, td, **kwargs):
            assert not (project / "project.ini").exists()
            assert source.stat().st_mode & stat.S_IWRITE
            assert source_project.stat().st_mode & stat.S_IWRITE
            attempts.append(kwargs["mesh_cells_per_wavelength"])
            if len(attempts) == 1:
                raise RuntimeError("preprocessing failed")
            candidate.write_bytes(b"prepared model")
            jsonpath.write_text("[]", encoding="utf-8")
            return SimpleNamespace(project_path=candidate, parameters=[])

    monkeypatch.setattr("csttool.projectconfmanager.CstProjectPreprocessor", Preprocessor)
    with pytest.raises(RuntimeError, match="preprocessing failed"):
        manager.prepare_project(mesh_cells_per_wavelength=10)
    assert not manager.is_ready()
    assert not (project / "project.ini").exists()

    assert manager.prepare_project(mesh_cells_per_wavelength=10)
    saved = ProjectSettings.from_parser(read_ini(project / "project.ini"))
    assert saved.cst_filename == Path("processed.cst")
    assert saved.cells_per_wavelength == 10
    assert saved.project_digest == manager.file_digest(project / "processed.cst")
    assert source.read_bytes() == b"original model"
    assert attempts == [10, 10]
    assert manager.prepare_project(startFromExisted=True, mesh_cells_per_wavelength=10)
