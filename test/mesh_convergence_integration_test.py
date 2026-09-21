import configparser
import logging
from pathlib import Path

import pytest

from csttool.application_backend import CstApplicationBackend
from csttool.projectconfmanager import ProjectConfmanager


pytestmark = pytest.mark.integration


class _GlobalConfig:
    def __init__(self, root, executable):
        self.conf = configparser.ConfigParser()
        self.conf["BASE"] = {"datadir": str(root / "data")}
        self.conf["CST"] = {
            "cstexepath": str(executable),
            "cstver": "2022",
        }


def test_real_pillbox_mesh_convergence_produces_report(
    cst_executable, tmp_path
):
    root = Path(__file__).parents[1]
    global_config = _GlobalConfig(root, cst_executable)
    project_config = ProjectConfmanager(
        GlobalConfigManager=global_config,
        logger=logging.getLogger("mesh-convergence-integration"),
    )
    backend = CstApplicationBackend(
        global_config_manager=global_config,
        project_config_manager=project_config,
        application_logger=logging.getLogger("mesh-convergence-integration"),
    )
    backend.select_project_directory(str(tmp_path))
    backend.select_cst_file(str(root / "model" / "Pillbox_2015.cst"))
    backend.update_postprocess_settings(
        [
            {
                "resultName": "frequency",
                "method": "Frequency",
                "params": {"iModeNumber": 1},
            }
        ]
    )

    recommended = backend._run_mesh_convergence(
        {
            "fmin": 400,
            "fmax": 550,
            "mesh_convergence_start": 18,
            "mesh_convergence_stop": 22,
            "mesh_convergence_step": 2,
            "mesh_convergence_tolerance": 0.5,
        }
    )

    assert recommended == 22
    assert (tmp_path / "mesh_convergence" / "mesh_convergence.json").is_file()
    assert (tmp_path / "mesh_convergence" / "mesh_convergence.csv").is_file()
