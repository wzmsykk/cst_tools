import hashlib
import logging
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from csttool.configuration import CstBackendSettings, GlobalSettings, ProjectSettings
from csttool.cstmanager import CSTManager
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.pillbox_analytic import PillboxRadiusBatchOptimizer
from test.cst_integration_support import (
    cst_processes,
    new_cst_processes,
    windows_process_snapshot,
)


pytestmark = pytest.mark.integration


class _GlobalConfig:
    def __init__(self, root: Path, executable: Path):
        self.settings = GlobalSettings(cst=CstBackendSettings(executable=executable))


class _ProjectConfig:
    def __init__(self, root: Path):
        self.currProjectDir = root
        self.settings = ProjectSettings(name="pillbox-real-standard-batch", cst_filename=Path("Pillbox.cst"))

    def getCurrPPSList(self):
        return [
            {
                "resultName": "frequency",
                "method": "Frequency",
                "params": {"iModeNumber": 1},
            }
        ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _cleanup_residual_processes(baseline):
    residual = new_cst_processes(baseline)
    for pid in residual:
        subprocess.run(
            ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    return residual


def test_real_cst_standard_batch_optimizes_pillbox_radius_to_500_mhz(
    cst_executable, tmp_path
):
    source = Path(__file__).parent / "data" / "Pillbox" / "Pillbox.cst"
    source_hash = _sha256(source)
    project = tmp_path / "pillbox-standard-real"
    project.mkdir()
    shutil.copy2(source, project / "Pillbox.cst")
    baseline = cst_processes(windows_process_snapshot())
    manager = None
    stop_error = None
    residual = {}
    try:
        manager = CSTManager(
            _GlobalConfig(project, cst_executable),
            _ProjectConfig(project),
            params=[{"name": "R", "type": "double"}],
            logger=logging.getLogger("pillbox-real-standard-batch"),
            maxTask=1,
            worker_factory=ManagedCSTWorker.create,
            max_jobs_per_worker=100,
        )
        result = PillboxRadiusBatchOptimizer(
            manager,
            target_frequency_mhz=500.0,
            radius_bounds_mm=(230.5, 231.125),
            samples_per_iteration=3,
            max_iterations=2,
            frequency_tolerance_mhz=0.25,
            task_retry_count=1,
        ).optimize()
        print(
            "real CST Pillbox optimum: "
            f"R={result.best.radius_mm:.9f} mm, "
            f"f={result.best.frequency_mhz:.9f} MHz, "
            f"error={result.best.target_error_mhz:.9f} MHz, "
            f"iterations={result.iterations}, evaluations={result.evaluations}",
            flush=True,
        )

        assert result.best.target_error_mhz <= 0.5
        assert 228.0 <= result.best.radius_mm <= 233.0
        assert manager.get_confirmed_snapshot() is None
    finally:
        if manager is not None:
            try:
                manager.stop()
            except Exception as exc:
                stop_error = exc
        deadline = time.monotonic() + 15
        while new_cst_processes(baseline) and time.monotonic() < deadline:
            time.sleep(0.1)
        residual = _cleanup_residual_processes(baseline)

    assert _sha256(source) == source_hash
    assert stop_error is None, f"standard Manager did not stop cleanly: {stop_error}"
    assert not residual, f"standard batch left CST processes: {residual}"
