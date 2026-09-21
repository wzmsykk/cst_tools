"""Typed, versioned configuration models and INI persistence.

The dataclasses are the application-facing configuration API. ``ConfigParser``
is restricted to this serialization boundary and compatibility views.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import tempfile


CONFIG_SCHEMA_VERSION = 3
PROJECT_TASK_STATUSES = frozenset(
    {
        "UNKNOWN",
        "READY",
        "RUNNING",
        "DONE",
        "STOP_REQUESTED",
        "INTERRUPTED",
        "FAILED",
        "RECOVERY_REQUIRED",
    }
)


class ConfigurationError(ValueError):
    """A persisted configuration is missing or semantically invalid."""


def _required(parser: configparser.ConfigParser, section: str, key: str) -> str:
    if not parser.has_option(section, key):
        raise ConfigurationError(f"missing configuration value [{section}] {key}")
    return parser.get(section, key)


def _first(
    parser: configparser.ConfigParser,
    candidates: tuple[tuple[str, str], ...],
    *,
    fallback: str | None = None,
) -> str:
    for section, key in candidates:
        if parser.has_option(section, key):
            return parser.get(section, key)
    if fallback is not None:
        return fallback
    section, key = candidates[0]
    raise ConfigurationError(f"missing configuration value [{section}] {key}")


def _optional_path(value: str) -> Path | None:
    value = value.strip()
    return Path(value) if value else None


def _schema_version(parser: configparser.ConfigParser) -> int:
    return int(
        _first(
            parser,
            (("config", "schema_version"), ("CONFIG", "schema_version")),
            fallback="1",
        )
    )


@dataclass(frozen=True, slots=True)
class DirectorySettings:
    data: Path = Path("./data")
    temp: Path = Path("./temp")
    log: Path = Path("./log")
    result: Path = Path("./result")


@dataclass(frozen=True, slots=True)
class CstBackendSettings:
    version: str = ""
    executable: Path | None = None


@dataclass(frozen=True, slots=True)
class SuperfishSettings:
    version: str = ""
    directory: Path | None = None


@dataclass(frozen=True, slots=True)
class GlobalSettings:
    directories: DirectorySettings = DirectorySettings()
    cst: CstBackendSettings = CstBackendSettings()
    current_project_directory: Path | None = None
    superfish: SuperfishSettings = SuperfishSettings()
    schema_version: int = CONFIG_SCHEMA_VERSION

    @classmethod
    def from_parser(
        cls,
        parser: configparser.ConfigParser,
        *,
        defaults: "GlobalSettings | None" = None,
    ) -> "GlobalSettings":
        defaults = defaults or cls()
        schema = _schema_version(parser)
        if schema > CONFIG_SCHEMA_VERSION:
            raise ConfigurationError(
                f"unsupported global configuration schema: {schema}"
            )
        return cls(
            directories=DirectorySettings(
                Path(
                    _first(
                        parser,
                        (("paths", "data_dir"), ("BASE", "datadir")),
                        fallback=str(defaults.directories.data),
                    )
                ),
                Path(
                    _first(
                        parser,
                        (("paths", "temp_dir"), ("BASE", "tempdir")),
                        fallback=str(defaults.directories.temp),
                    )
                ),
                Path(
                    _first(
                        parser,
                        (("paths", "log_dir"), ("BASE", "logdir")),
                        fallback=str(defaults.directories.log),
                    )
                ),
                Path(
                    _first(
                        parser,
                        (("paths", "result_dir"), ("BASE", "resultdir")),
                        fallback=str(defaults.directories.result),
                    )
                ),
            ),
            cst=CstBackendSettings(
                _first(
                    parser,
                    (("cst", "version"), ("CST", "cstver")),
                    fallback=defaults.cst.version,
                ),
                _optional_path(
                    _first(
                        parser,
                        (("cst", "executable"), ("CST", "cstexepath")),
                        fallback=str(defaults.cst.executable or ""),
                    )
                ),
            ),
            current_project_directory=_optional_path(
                _first(
                    parser,
                    (("project", "current_directory"), ("PROJECT", "currprojdir")),
                    fallback=str(defaults.current_project_directory or ""),
                )
            ),
            superfish=SuperfishSettings(
                _first(
                    parser,
                    (("superfish", "version"),),
                    fallback=defaults.superfish.version,
                ),
                _optional_path(
                    _first(
                        parser,
                        (("superfish", "directory"), ("superfish", "dirpath")),
                        fallback=str(defaults.superfish.directory or ""),
                    )
                ),
            ),
        )

    def to_parser(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser()
        parser["config"] = {
            "schema_version": str(self.schema_version),
            "document_type": "global",
        }
        parser["paths"] = {
            "data_dir": str(self.directories.data),
            "temp_dir": str(self.directories.temp),
            "log_dir": str(self.directories.log),
            "result_dir": str(self.directories.result),
        }
        parser["cst"] = {
            "version": self.cst.version,
            "executable": str(self.cst.executable or ""),
        }
        parser["project"] = {
            "current_directory": str(self.current_project_directory or "")
        }
        parser["superfish"] = {
            "directory": str(self.superfish.directory or ""),
            "version": self.superfish.version,
        }
        return parser

    def with_cst(self, version: str, executable: str | Path) -> "GlobalSettings":
        return replace(
            self,
            cst=CstBackendSettings(str(version), Path(executable).resolve()),
        )


@dataclass(frozen=True, slots=True)
class ProjectDirectorySettings:
    result: Path = Path("result")
    temp: Path = Path("temp")


@dataclass(frozen=True, slots=True)
class ProjectSettings:
    name: str
    description: str = ""
    directories: ProjectDirectorySettings = ProjectDirectorySettings()
    cst_filename: Path | None = None
    project_digest: str = ""
    digest_algorithm: str = "sha256"
    use_mpi: bool = False
    mpi_node_list: str = ""
    use_remote_calculation: bool = False
    dc_main_control_address: str = ""
    parameter_file: Path = Path("params.json")
    postprocess_file: Path = Path("pps.json")
    fixed_mesh: bool = True
    cells_per_wavelength: int = 20
    task_status: str = "READY"
    schema_version: int = CONFIG_SCHEMA_VERSION

    def __post_init__(self):
        if not self.name.strip():
            raise ConfigurationError("project name must not be empty")
        if self.cells_per_wavelength < 1:
            raise ConfigurationError("cells per wavelength must be positive")
        if self.task_status not in PROJECT_TASK_STATUSES:
            raise ConfigurationError(
                f"unsupported project task status: {self.task_status}"
            )
        if self.digest_algorithm not in {"md5", "sha256"}:
            raise ConfigurationError(
                f"unsupported project digest algorithm: {self.digest_algorithm}"
            )

    @classmethod
    def from_parser(cls, parser: configparser.ConfigParser) -> "ProjectSettings":
        schema = _schema_version(parser)
        if schema > CONFIG_SCHEMA_VERSION:
            raise ConfigurationError(
                f"unsupported project configuration schema: {schema}"
            )
        cst_filename = _first(
            parser,
            (("cst", "project_file"), ("CST", "CSTFilename")),
            fallback="",
        ).strip()
        return cls(
            name=_first(parser, (("project", "name"), ("PROJECT", "ProjectName"))),
            description=_first(
                parser,
                (("project", "description"), ("PROJECT", "ProjectDescription")),
                fallback="",
            ),
            directories=ProjectDirectorySettings(
                Path(
                    _first(
                        parser,
                        (("paths", "result_dir"), ("DIRS", "resultdir")),
                    )
                ),
                Path(
                    _first(
                        parser,
                        (("paths", "temp_dir"), ("DIRS", "tempdir")),
                    )
                ),
            ),
            cst_filename=Path(cst_filename) if cst_filename else None,
            project_digest=_first(
                parser,
                (("cst", "project_digest"), ("CST", "CSTFileMD5")),
                fallback="",
            ),
            digest_algorithm=_first(
                parser,
                (("cst", "digest_algorithm"),),
                fallback=("sha256" if parser.has_section("cst") else "md5"),
            ),
            use_mpi=_first(
                parser, (("execution", "use_mpi"), ("CST", "UseMpi")), fallback="False"
            ).casefold()
            == "true",
            mpi_node_list=_first(
                parser,
                (("execution", "mpi_node_list"), ("CST", "MpiNodeList")),
                fallback="",
            ),
            use_remote_calculation=_first(
                parser,
                (("execution", "use_remote"), ("CST", "UseRemoteCalculaton")),
                fallback="False",
            ).casefold()
            == "true",
            dc_main_control_address=_first(
                parser,
                (("execution", "controller_address"), ("CST", "DCMainControlAddress")),
                fallback="",
            ),
            parameter_file=Path(
                _first(
                    parser,
                    (("artifacts", "parameters"), ("PARAMETERS", "paramfile")),
                )
            ),
            postprocess_file=Path(
                _first(
                    parser,
                    (("artifacts", "postprocess"), ("PARAMETERS", "ppsfile")),
                )
            ),
            fixed_mesh=_first(
                parser, (("mesh", "fixed"), ("MESH", "Fixed")), fallback="True"
            ).casefold()
            == "true",
            cells_per_wavelength=int(
                _first(
                    parser,
                    (("mesh", "cells_per_wavelength"), ("MESH", "CellsPerWavelength")),
                    fallback="20",
                )
            ),
            task_status=_first(parser, (("task", "status"), ("TASK", "status"))),
        )

    def to_parser(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser()
        parser["config"] = {
            "schema_version": str(self.schema_version),
            "document_type": "project",
        }
        parser["project"] = {
            "name": self.name,
            "description": self.description,
        }
        parser["paths"] = {
            "result_dir": str(self.directories.result),
            "temp_dir": str(self.directories.temp),
        }
        parser["cst"] = {
            "project_file": str(self.cst_filename or ""),
            "project_digest": self.project_digest,
            "digest_algorithm": self.digest_algorithm,
        }
        parser["execution"] = {
            "use_mpi": str(self.use_mpi),
            "mpi_node_list": self.mpi_node_list,
            "use_remote": str(self.use_remote_calculation),
            "controller_address": self.dc_main_control_address,
        }
        parser["artifacts"] = {
            "parameters": str(self.parameter_file),
            "postprocess": str(self.postprocess_file),
        }
        parser["mesh"] = {
            "fixed": str(self.fixed_mesh),
            "cells_per_wavelength": str(self.cells_per_wavelength),
        }
        parser["task"] = {"status": self.task_status}
        return parser


def read_ini(
    path: str | Path, *, defaults: str | Path | None = None
) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    paths = [Path(defaults)] if defaults is not None else []
    paths.append(Path(path))
    loaded = parser.read(paths, encoding="utf-8")
    if not loaded:
        raise FileNotFoundError(path)
    return parser


def write_ini_atomic(path: str | Path, parser: configparser.ConfigParser) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=destination.parent, delete=False
        ) as stream:
            parser.write(stream)
            temporary = Path(stream.name)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination


def read_json(path: str | Path):
    with Path(path).open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json_atomic(path: str | Path, value) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=destination.parent, delete=False
        ) as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            temporary = Path(stream.name)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination
