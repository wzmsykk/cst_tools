import configparser
import logging

import pytest

from csttool.projectconfmanager import ProjectConfigManager, ProjectStatusError
from csttool.configuration import ProjectSettings


def _manager_with_config(config):
    manager = object.__new__(ProjectConfigManager)
    manager.conf = config
    manager.logger = logging.getLogger("projectconfmanager-mesh-test")
    return manager


def test_existing_project_rejects_fixed_mesh_drift():
    config = ProjectSettings(name="mesh-test").to_parser()
    manager = _manager_with_config(config)

    manager._validate_fixed_mesh(20)
    with pytest.raises(ProjectStatusError, match="请新建项目"):
        manager._validate_fixed_mesh(24)


def test_legacy_project_without_mesh_metadata_is_left_unchanged(caplog):
    manager = _manager_with_config(configparser.ConfigParser())

    with caplog.at_level(logging.WARNING):
        manager._validate_fixed_mesh(24)

    assert "保持工程现状" in caplog.text
