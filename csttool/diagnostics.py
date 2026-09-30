"""Persist reproducible worker inputs and implementation fingerprints."""

from dataclasses import fields
import hashlib
import json
from pathlib import Path

from .runtime_protocol import atomic_publish
from .logging_config import _code_version


def write_run_manifest(path, config, artifacts, *, context=None):
    source_root = Path(__file__).resolve().parent
    repository = source_root.parent
    implementations = list(source_root.glob("*.py"))
    implementations.extend((repository / "data").rglob("*.vb"))
    sources = {
        source.relative_to(repository).as_posix(): hashlib.sha256(source.read_bytes()).hexdigest()
        for source in sorted(implementations)
    }
    # Do not deepcopy a bound callback: its owner can contain locks or processes.
    settings = {field.name: getattr(config, field.name) for field in fields(config)
                if field.name != "progress_callback"}
    document = {
        "schema_version": 1, "code": _code_version(), "source_sha256": sources,
        "config": settings, "artifacts": artifacts, "context": context or {},
    }
    path = Path(path)
    atomic_publish(path, json.dumps(document, ensure_ascii=False, indent=2, default=str))
    return path
