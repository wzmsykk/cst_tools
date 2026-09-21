import json

import pytest

from csttool.hom_run_manifest import HomRunManifest, ManifestMismatchError
from csttool.hom_scan import ScanPolicy


class _ProjectConfig:
    def __init__(self, source):
        self.inputCSTFilePath = source


class _Manager:
    def __init__(self, prepared, source):
        self.cstProjPath = prepared
        self.pconfm = _ProjectConfig(source)
        self.maxParallelTasks = 1
        self.gconf = {
            "CST": {
                "cstver": "2022",
                "cstexepath": r"D:\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe",
            }
        }


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
