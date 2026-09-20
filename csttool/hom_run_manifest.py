"""Immutable launch identity for a real HOM scan."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
from pathlib import Path


class ManifestMismatchError(ValueError):
    pass


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class HomRunManifest:
    schema_version: int
    source_project: str
    prepared_project: str
    project_sha256: str
    frequency_start: float
    frequency_stop: float
    initial_window: float
    requested_modes: int
    worker_count: int
    background: bool
    cst_version: str = ""
    cst_executable: str = ""

    @classmethod
    def create(cls, manager, policy) -> "HomRunManifest":
        prepared = Path(manager.cstProjPath).resolve()
        project_config = getattr(manager, "pconfm", None)
        source = getattr(project_config, "inputCSTFilePath", None) or prepared
        global_config = getattr(manager, "gconf", None)
        cst_section = global_config["CST"] if global_config is not None else {}
        return cls(
            schema_version=2,
            source_project=str(Path(source).resolve()),
            prepared_project=str(prepared),
            project_sha256=file_sha256(prepared),
            frequency_start=policy.start,
            frequency_stop=policy.stop,
            initial_window=policy.initial_stop - policy.start,
            requested_modes=policy.requested_modes,
            worker_count=int(getattr(manager, "maxParallelTasks", 1)),
            background=True,
            cst_version=str(cst_section.get("cstver", "")),
            cst_executable=str(cst_section.get("cstexepath", "")),
        )

    def write_once(self, path: str | Path) -> Path:
        path = Path(path)
        document = asdict(self)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != document:
                raise ManifestMismatchError(
                    "existing HOM scan manifest does not match this run"
                )
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, path)
        return path

    @classmethod
    def ensure(cls, path: str | Path, manager, policy) -> "HomRunManifest":
        path = Path(path)
        current = cls.create(manager, policy)
        if path.exists():
            existing = cls(**json.loads(path.read_text(encoding="utf-8")))
            if getattr(getattr(manager, "pconfm", None), "inputCSTFilePath", None) is None:
                current = replace(current, source_project=existing.source_project)
            if existing != current:
                raise ManifestMismatchError(
                    "existing HOM scan manifest does not match this run"
                )
            return existing
        current.write_once(path)
        return current
