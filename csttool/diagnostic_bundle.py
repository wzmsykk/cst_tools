"""Bounded, read-only diagnostic snapshots; no Runner token or model payloads."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile


LIGHT_SUFFIXES = {'.log', '.jsonl', '.json', '.tsv', '.vb', '.bas', '.run'}
PROTOCOL_NAMES = {'current.task', 'current.completion', 'current.ack', 'stop.request',
                  'stop.ack', 'close.receipt', 'worker.state', 'worker.pid',
                  'stage.txt', 'completion.txt', 'parameters.txt', 'output.txt'}


class ExportCancelled(RuntimeError):
    pass


def export_failure_bundle(project, *, file_limit=4 * 1024**2,
                          total_limit=64 * 1024**2, max_files=1000,
                          cancel_check=None, progress=None):
    """Export current run and linked worker evidence, even with Runner offline.

    Large files contain a tail snapshot, not a valid complete JSON document.
    All omissions/errors are recorded. Source metadata is never changed.
    """
    def check():
        if cancel_check and cancel_check():
            raise ExportCancelled('诊断导出已取消')
    check()
    project = Path(project).resolve(strict=True)
    if not project.is_dir():
        raise ValueError('project must be an existing directory')
    if min(file_limit, total_limit, max_files) <= 0:
        raise ValueError('bundle limits must be positive')
    output = project / 'diagnostics'
    if not output.resolve().is_relative_to(project):
        raise ValueError('diagnostics directory escapes project')
    output.mkdir(exist_ok=True)
    candidates = {}
    warnings = []

    def add(path):
        check()
        path = Path(path)
        if not path.resolve().is_relative_to(project):
            warnings.append('outside-project: ' + str(path))
            return
        if len(candidates) >= max_files:
            if 'file-count-limit' not in warnings:
                warnings.append('file-count-limit')
            return
        candidates.setdefault(path.relative_to(project).as_posix(), path)
        if progress and (len(candidates) == 1 or len(candidates) % 25 == 0):
            progress(dict(phase='discover', current=len(candidates), total=None,
                          file=path.relative_to(project).as_posix()))

    def tree(root):
        if not root.is_dir() or not root.resolve().is_relative_to(project):
            return
        def inaccessible(error):
            warnings.append('discovery unreadable: ' + str(error))
        for visited, (directory, dirs, names) in enumerate(os.walk(root, followlinks=False, onerror=inaccessible)):
            check()
            if visited >= max_files:
                warnings.append('directory-discovery-limit: ' + str(root))
                break
            dirs[:] = sorted(d for d in dirs if
                (Path(directory) / d).resolve().is_relative_to(project)
                and not (Path(directory) / d).is_symlink())
            for name in sorted(names):
                p = Path(directory) / name
                if p.suffix.lower() in LIGHT_SUFFIXES or name in PROTOCOL_NAMES or name.endswith('.accepted'):
                    add(p)
            if len(candidates) >= max_files:
                warnings.append('discovery-stopped-at-file-limit')
                break

    status_path = project / 'control/status.json'
    status = {}
    try:
        if status_path.resolve().is_relative_to(project):
            with status_path.open('rb') as stream:
                status = json.loads(stream.read(1024**2))
            if not isinstance(status, dict):
                status = {}
    except (OSError, ValueError) as error:
        warnings.append('status unavailable: ' + str(error))
    # Explicit allowlist: endpoint.json/runner.json contain bearer credentials.
    for name in ('status.json', 'project.json'):
        add(project / 'control' / name)
    startup = None
    for name in ('bootstrap.json', 'bootstrap.log'):
        path = project / 'control' / name
        if path.is_file():
            add(path)
    bootstrap = project / 'control/bootstrap.json'
    try:
        if bootstrap.is_file():
            if not bootstrap.resolve().is_relative_to(project):
                raise ValueError('bootstrap evidence escapes project')
            with bootstrap.open('rb') as stream:
                value = json.loads(stream.read(1024**2))
            if (not isinstance(value, dict) or not isinstance(value.get('project'), str)
                    or Path(value['project']).resolve() != project):
                raise ValueError('invalid bootstrap project identity')
            startup = dict(source='control/bootstrap.json', **{key:value.get(key) for key in (
                'attempt_id', 'startup_state', 'phase', 'started_at', 'elapsed_seconds',
                'launcher_pid', 'launcher_exit_code', 'last_probe_error')})
    except (OSError, ValueError) as error:
        startup = dict(source='control/bootstrap.json', startup_state='unreadable')
        warnings.append('bootstrap unavailable: ' + str(error))
    for name in ('project.ini', 'project.conf', 'params.json', 'pps.json'):
        if (project / name).is_file():
            add(project / name)
    for name in ('save/csv/hom_scan_checkpoint.json', 'save/csv/scan_manifest.json',
                 'save/csv/hom_scan_results.csv', 'save/standard_batch_checkpoint.json'):
        if (project / name).is_file():
            add(project / name)

    runs = []
    directory = status.get('log_directory')
    if isinstance(directory, str):
        run = Path(directory)
        if not run.is_absolute():
            run = project / run
        if run.resolve().is_relative_to(project / 'logs') and run.is_dir():
            runs.append(run)
        else:
            warnings.append('current log directory unavailable or outside logs')
    if not runs and (project / 'logs').is_dir():
        available = sorted((p for p in (project / 'logs').iterdir()
                            if p.is_dir() and p.resolve().is_relative_to(project / 'logs')),
                           key=lambda p: p.name, reverse=True)
        runs = available[:1]
        warnings.append('run selected by directory ordering; status did not identify an accessible run')
    history = status.get('log_history')
    if isinstance(history, list):
        for entry in history[-1:]:
            if not isinstance(entry, dict) or not isinstance(entry.get('directory'), str):
                continue
            prior = Path(entry['directory'])
            if not prior.is_absolute():
                prior = project / prior
            if prior.resolve().is_relative_to(project / 'logs') and prior.is_dir() and prior not in runs:
                runs.append(prior)
    sessions = set()
    # Reserve core run evidence before historic worker enumeration consumes
    # the discovery budget. Final ZIP priority cannot recover undiscovered files.
    for run in runs:
        for name in ('application.log', 'application.jsonl', 'run.json', 'summary.json'):
            if (run / name).is_file():
                add(run / name)
    run_metadata = {}
    if runs:
        metadata = runs[0] / 'run.json'
        try:
            if metadata.resolve().is_relative_to(project):
                with metadata.open('rb') as stream:
                    value = json.loads(stream.read(1024**2))
                if isinstance(value, dict):
                    run_metadata = value
        except (OSError, ValueError):
            pass
    for run in runs:
        for worker in (run / 'workers').glob('*/*'):
            if worker.is_dir() and worker.resolve().is_relative_to(project):
                sessions.add(worker.name)
    temp = project / 'temp'
    try:
        import configparser
        config = configparser.ConfigParser(interpolation=None)
        config_path = project / 'project.ini'
        if config_path.resolve().is_relative_to(project):
            config.read(config_path, encoding='utf-8-sig')
        configured = Path(config.get('paths', 'temp_dir', fallback='temp'))
        proposed = configured if configured.is_absolute() else project / configured
        if proposed.resolve().is_relative_to(project):
            temp = proposed
        else:
            warnings.append('configured temp outside project; excluded')
    except (OSError, ValueError, configparser.Error) as error:
        warnings.append('temp configuration unreadable: ' + str(error))
    worker_dirs = list(temp.glob('worker_*/*'))
    if not sessions:
        worker_dirs = sorted((p for p in worker_dirs if p.is_dir()),
                             key=lambda p: p.stat().st_mtime_ns, reverse=True)[:3]
        warnings.append('worker sessions selected by newest directory timestamps')
    for worker in worker_dirs:
        if sessions and worker.name not in sessions:
            continue
        for name in ('worker.state', 'worker.pid', 'close-protocol.json', 'close-verification.json',
                     'recovery-l1.json', 'recovery.json',
                     'task-context.json', 'worker-input.cst.last-good-parameters.tsv',
                     'worker-input.cst.recovery-saved', 'runtime_managed_worker_v1.bas',
                     'diagnostics.json', 'process-identity.json', 'cst.log', 'lifecycle.log'):
            add(worker / name)
        tree(worker / 'protocol')
        tree(worker / 'failures')
        for name in ('output.txt', 'progress.log'):
            add(worker / 'worker-input/Result' / name)
        add(worker / 'worker-input/Model/3D/Model.run')
        tree(worker / 'received')
        tree(worker / 'resource_usage')
    for run in runs:
        # Prioritize application/lifecycle/error evidence over resource samples.
        for p in run.glob('*'):
            if p.is_file() and p.suffix.lower() in LIGHT_SUFFIXES:
                add(p)
        for observation in (run / 'workers').glob('*/*'):
            for p in observation.glob('*'):
                if p.is_file() and p.suffix.lower() in LIGHT_SUFFIXES:
                    add(p)
            tree(observation / 'failures')
        tree(run)
    # Preparation can fail before a worker exists, so keep its newest probes.
    preprobes = sorted((p for p in temp.glob('cst-preprocess-*') if p.is_dir()),
                       key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for probe in preprobes[:3]:
        tree(probe)
    if not runs:
        warnings.append('no run log directory found')
    stamp = datetime.now().astimezone().strftime('%Y%m%d-%H%M%S-%f')
    destination = output / ((project.name or 'project')[:48] + '-failure-' + stamp + '.zip')
    manifest = {'schema_version': 1, 'created': datetime.now().astimezone().isoformat(),
                'project': str(project), 'run_id': status.get('run_id') or run_metadata.get('run_id'),
                'run_identity_source': ('control/status.json' if status.get('run_id') else
                                        str(runs[0] / 'run.json') if run_metadata.get('run_id') else None),
                'state': status.get('state'), 'phase': status.get('phase'),
                'startup': startup,
                'error': status.get('error'), 'runs': [str(p) for p in runs],
                'limits': {'per_file': file_limit, 'total': total_limit, 'files': max_files},
                'snapshot_consistency': 'best-effort; active files can change',
                'warnings': warnings, 'files': []}
    fd, temporary = tempfile.mkstemp(prefix='.export-', suffix='.tmp', dir=output)
    os.close(fd)
    used = 0
    published = False
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            def priority(item):
                relative, path = item
                if relative.startswith('control/') or (relative.startswith('logs/') and
                        path.name in {'application.log', 'application.jsonl', 'run.json', 'summary.json'}):
                    return -1
                if path.name in {'output.txt', 'progress.log', 'lifecycle.log', 'cst.log'}:
                    return 0
                if '/resource_usage/' in relative:
                    return 3
                return 1 if ('/failures/' in relative or '/protocol/' in relative
                             or relative.startswith('save/') or path.name == 'recovery-l1.json') else 2

            for index, (relative, path) in enumerate(sorted(candidates.items(), key=priority), 1):
                check()
                if progress:
                    progress(dict(phase='capture', current=index, total=len(candidates), file=relative))
                record = {'source': str(path), 'archive': 'files/' + relative}
                manifest['files'].append(record)
                try:
                    if not path.resolve().is_relative_to(project) or not path.is_file():
                        raise OSError('missing, not a regular file, or outside project')
                    before = path.stat()
                    amount = min(file_limit, total_limit - used)
                    if amount <= 0:
                        record['status'] = 'omitted-budget'
                        continue
                    with path.open('rb') as stream:
                        offset = max(0, before.st_size - amount)
                        stream.seek(offset)
                        data = stream.read(amount)
                    check()
                    after = path.stat()
                    record.update(status='included', original_bytes=before.st_size,
                                  captured_bytes=len(data), offset=offset,
                                  truncated=offset > 0,
                                  changed_during_read=(before.st_size, before.st_mtime_ns) !=
                                                      (after.st_size, after.st_mtime_ns),
                                  sha256=hashlib.sha256(data).hexdigest())
                    archive.writestr(record['archive'], data)
                    used += len(data)
                except OSError as error:
                    record.update(status='unavailable', error=str(error))
            manifest['captured_bytes'] = used
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr('README.txt',
                'CST failure diagnostics\nSee manifest.json for project/run/task source paths, hashes, '
                'missing files and truncation. Files may be live snapshots. Truncated JSON/JSONL '
                'is a raw tail, not necessarily parseable. Models and 3D fields are excluded.\n'
                'This package can contain local paths, parameter expressions and log contents.\n')
        # Exclusive publication never overwrites an earlier diagnostic package.
        check()
        with open(temporary, 'rb') as source, destination.open('xb') as target:
            published = True
            while True:
                check()
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)
    except BaseException:
        if published and destination.exists():
            destination.unlink()
        raise
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {'path': str(destination), 'bytes': destination.stat().st_size,
            'run_id': manifest['run_id'], 'files': len(manifest['files']),
            'warnings': len(warnings)}
