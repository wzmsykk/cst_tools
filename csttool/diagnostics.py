"""Persist reproducible worker inputs and implementation fingerprints."""

from dataclasses import fields
import hashlib
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .runtime_protocol import atomic_publish
from .logging_config import _code_version
from .cst_installations import infer_cst_version


def collect_windows_events():
    """Return a stable envelope, distinguishing no matches from query failure."""
    command = (
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
        "try { $events=@(Get-WinEvent -FilterHashtable @{LogName='Application';"
        "Id=1000;StartTime=(Get-Date).AddMinutes(-5)} -ErrorAction Stop | "
        "Where-Object {$_.Message -match 'CST'} | Select-Object -First 3 "
        "TimeCreated,Message); @{status='ok';events=$events} | ConvertTo-Json -Depth 4 -Compress } "
        "catch { if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') "
        "{ @{status='ok';events=@()} | ConvertTo-Json -Compress } "
        "else { @{status='unavailable';events=@();error=$_.Exception.Message;"
        "error_id=$_.FullyQualifiedErrorId} | ConvertTo-Json -Compress } }")
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, encoding='utf-8', errors='replace', timeout=5, check=False)
        if result.returncode:
            return {'status': 'unavailable', 'events': [], 'exit_code': result.returncode,
                    'stderr': result.stderr[-8192:], 'stdout': result.stdout[-8192:]}
        envelope = json.loads(result.stdout)
        if not isinstance(envelope, dict) or not isinstance(envelope.get('events'), list):
            raise ValueError('invalid Windows event envelope')
        return envelope
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {'status': 'unavailable', 'events': [], 'error': str(exc)}


def write_failure_report(root, *, phase, process=None, paths=None, context=None):
    """Best-effort bounded evidence; collecting it must not replace the failure."""
    evidence = {}
    for name, path in (paths or {}).items():
        if path is None:
            continue
        try:
            path = Path(path)
            item = {"path": str(path), "exists": path.exists()}
            if path.is_file():
                item.update(size=path.stat().st_size, modified=path.stat().st_mtime)
                with path.open('rb') as stream:
                    stream.seek(max(0, item['size'] - 8192))
                    item['tail'] = stream.read(8192).decode('utf-8', errors='replace')
            evidence[name] = item
        except OSError as exc:
            evidence[name] = {"error": str(exc)}
    code = process.poll() if process is not None else None
    document = {"schema_version": 1, "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": phase, "context": context or {}, "files": evidence,
                "process": {"pid": process.pid if process is not None else None,
                            "exit_code": code,
                            "exit_code_hex": f'0x{code & 0xffffffff:08X}' if code is not None else None}}
    error_type, error, error_traceback = sys.exc_info()
    document['error'] = ({'type': error_type.__name__, 'message': str(error),
                          'traceback': ''.join(traceback.format_exception(error_type, error, error_traceback))}
                         if error_type is not None else None)
    # Events are candidates from a short time window, not proof of causality.
    if os.name == 'nt' and code not in (None, 0):
        document['windows_events'] = collect_windows_events()
    destination = Path(root) / 'failures'
    destination.mkdir(parents=True, exist_ok=True)
    from uuid import uuid4
    path = destination / f'{uuid4().hex}.json'
    atomic_publish(path, json.dumps(document, ensure_ascii=False, indent=2, default=str))
    return path


def executable_metadata(executable):
    path = Path(executable)
    metadata = {"path": str(path), "inferred_year": infer_cst_version(path),
                "file_version": None, "product_version": None}
    if os.name == "nt" and path.is_file():
        literal = str(path.resolve()).replace("'", "''")
        command = (f"$v=(Get-Item -LiteralPath '{literal}').VersionInfo; "
                   "@{file_version=$v.FileVersion;product_version=$v.ProductVersion} | ConvertTo-Json -Compress")
        try:
            output = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                                    capture_output=True, text=True, timeout=10, check=True)
            metadata.update(json.loads(output.stdout))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            metadata["metadata_error"] = str(exc)
    return metadata


def archive_task(directory, task, result_name):
    """Archive the exact wire input before publishing it to the live slot."""
    from .runtime_protocol import encode_task
    destination = Path(directory) / "tasks" / task.task_id
    destination.mkdir(parents=True, exist_ok=False)
    payload = encode_task(task)
    atomic_publish(destination / "input.task", payload)
    atomic_publish(destination / "context.json", json.dumps({
        "schema_version": 1, "task_id": task.task_id,
        "session_id": task.session_id, "job": result_name,
    }, ensure_ascii=False, indent=2))
    return payload


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
    path.parent.mkdir(parents=True, exist_ok=True)
    source = Path(config.project_path)
    backup = path.parent / "source-input.cst"
    if source.is_file():
        if backup.exists():
            raise FileExistsError(backup)
        shutil.copy2(source, backup)
        document["source_project"] = {"backup": str(backup), "size": backup.stat().st_size}
    else:
        document["source_project"] = {"backup": None, "unavailable": str(source)}
    document["installation"] = executable_metadata(config.executable)
    atomic_publish(path, json.dumps(document, ensure_ascii=False, indent=2, default=str))
    return path
