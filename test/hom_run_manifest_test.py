import json
from dataclasses import replace
from pathlib import Path

import pytest

from csttool.hom_run_manifest import HomRunManifest, ManifestMismatchError
from csttool.hom_scan import ScanPolicy
from csttool.configuration import CstBackendSettings, GlobalSettings


class _ProjectConfig:
    def __init__(self, source):
        self.inputCSTFilePath = source


class _Manager:
    def __init__(self, prepared, source):
        self.cstProjPath = prepared
        self.pconfm = _ProjectConfig(source)
        self.maxParallelTasks = 1
        self.global_settings = GlobalSettings(cst=CstBackendSettings(
            "2022", Path(r"D:\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe")
        ))


def test_manifest_records_exact_project_identity_and_rejects_drift(tmp_path):
    source = tmp_path / "source.cst"
    prepared = tmp_path / "prepared.cst"
    source.write_bytes(b"source")
    prepared.write_bytes(b"prepared-v1")
    manager = _Manager(prepared, source)
    policy = ScanPolicy(500, 550, 1000)
    path = tmp_path / "scan_manifest.json"

    manifest = HomRunManifest.ensure(
        path,
        manager,
        policy,
        mesh_cells_per_wavelength=24,
    )

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["source_project"] == str(source.resolve())
    assert document["frequency_start"] == 500
    assert document["frequency_stop"] == 1000
    assert document["project_sha256"] == manifest.project_sha256
    assert document["cst_version"] == "2022"
    assert document["cst_executable"].endswith("CST DESIGN ENVIRONMENT.exe")
    assert document["schema_version"] == 3
    assert document["mesh_cells_per_wavelength"] == 24

    prepared.write_bytes(b"prepared-v2")
    with pytest.raises(ManifestMismatchError, match="does not match"):
        HomRunManifest.ensure(
            path,
            manager,
            policy,
            mesh_cells_per_wavelength=24,
        )


def test_manifest_rejects_mesh_setting_drift(tmp_path):
    source = tmp_path / "source.cst"
    prepared = tmp_path / "prepared.cst"
    source.write_bytes(b"source")
    prepared.write_bytes(b"prepared")
    manager = _Manager(prepared, source)
    policy = ScanPolicy(500, 550, 1000)
    path = tmp_path / "scan_manifest.json"
    HomRunManifest.ensure(path, manager, policy, mesh_cells_per_wavelength=20)

    with pytest.raises(ManifestMismatchError, match="does not match"):
        HomRunManifest.ensure(path, manager, policy, mesh_cells_per_wavelength=24)


def test_manifest_uses_typed_settings_without_a_parser_view(tmp_path):
    prepared = tmp_path / "prepared.cst"
    prepared.write_bytes(b"prepared")
    manager = _Manager(prepared, None)
    manager.global_settings = replace(
        GlobalSettings(), cst=CstBackendSettings("2025", Path("cst2025.exe"))
    )
    path = tmp_path / "manifest.json"
    manifest = HomRunManifest.ensure(path, manager, ScanPolicy(500, 550, 1000))
    assert HomRunManifest.ensure(path, manager, ScanPolicy(500, 550, 1000)) == manifest
    assert manifest.cst_version == "2025"
    assert manifest.cst_executable == "cst2025.exe"


def test_manifest_requires_migrated_manager_settings(tmp_path):
    prepared = tmp_path / "prepared.cst"
    prepared.write_bytes(b"prepared")
    manager = _Manager(prepared, None)
    del manager.global_settings
    manager.gconf = {"CST": {"cstver": "2022"}}
    with pytest.raises(AttributeError, match="global_settings"):
        HomRunManifest.create(manager, ScanPolicy(500, 550, 1000))
