"""Exclusive, observable postprocessing probes; never terminate CST."""
import os
from contextlib import contextmanager
from pathlib import Path
import time

import psutil

from .configuration import write_json_atomic


def cst_processes():
    records = []
    for process in psutil.process_iter(['pid', 'name', 'create_time']):
        name = (process.info['name'] or '').lower()
        if name.startswith(('cst design environment', 'modeler_', 'solver_')):
            records.append(process.info)
    return records


def task_project_processes(project):
    """Positive exact-path evidence only; inaccessible unrelated users are skipped."""
    target = os.path.normcase(os.path.abspath(project))
    for process in psutil.process_iter(['pid', 'create_time']):
        try:
            if not process.name().lower().startswith(('cst design environment', 'modeler_', 'solver_')):
                continue
            if any(os.path.normcase(os.path.abspath(arg)) == target
                   for arg in process.cmdline()[1:]):
                yield process
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            continue


@contextmanager
def exclusive_probe(root):
    """OS lock, automatically released on Python exit; reject live CST too."""
    path = Path(root) / 'artifacts' / '.acceptance.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            if path.stat().st_size == 0:
                stream.write(b'0'); stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError('another acceptance probe owns CST') from error
            unlock = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            unlock = lambda: fcntl.flock(stream, fcntl.LOCK_UN)
        try:
            existing = cst_processes()
            if existing:
                raise RuntimeError(f'CST is not idle: {existing}')
            yield
        finally:
            stream.seek(0)
            unlock()


def wait_probe(process, directory, *, stage_timeout=180, exit_timeout=60,
               completion_names=('completed.txt', 'failed.txt'), unbounded_stages=(),
               on_observation=None, preexisting_processes=(), task_project=None):
    """Bound idle probe phases, not normal solves. Keep failures for intervention."""
    directory = Path(directory)
    started = changed = time.monotonic()
    signature = None
    completed_at = None
    owned = {}
    foreign = {}
    baseline = {(record['pid'], record['create_time']): record
                for record in preexisting_processes}
    launcher_identity = None
    while True:
        try:
            root = psutil.Process(process.pid)
            identity = (root.pid, root.create_time())
            if launcher_identity is None:
                launcher_identity = identity
            if identity != launcher_identity:
                raise psutil.NoSuchProcess(process.pid)
            for child in [root, *root.children(recursive=True)]:
                owned[(child.pid, child.create_time())] = child
        except psutil.NoSuchProcess:
            pass
        if task_project is not None:
            for related in task_project_processes(task_project):
                try:
                    for member in [related, *related.children(recursive=True)]:
                        owned[(member.pid, member.create_time())] = member
                except psutil.NoSuchProcess:
                    pass
        files = [directory / name for name in ('stage.txt', 'cst.log', *completion_names)]
        current = tuple((p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None for p in files)
        if current != signature:
            signature = current
            changed = time.monotonic()
        if any(p.exists() for p in files[2:]) and completed_at is None:
            completed_at = time.monotonic()
        active = [p.pid for p in owned.values() if p.is_running()]
        # Only currently live, newly observed, unowned identities can block.
        # PID alone is insufficient: a recycled PID is not a baseline instance.
        try:
            current_cst = {(record['pid'], record['create_time']): record
                           for record in cst_processes()}
        except psutil.AccessDenied:
            current_cst = {}
        foreign = {identity: record for identity, record in current_cst.items()
                   if identity not in owned and identity not in baseline}
        exited = process.poll() is not None and not active
        diagnostic = {'launcher_pid': process.pid, 'owned': [{'pid': k[0], 'create_time': k[1]} for k in owned],
                      'active_pids': active, 'elapsed_seconds': time.monotonic()-started,
                      'exit_confirmed': exited, 'foreign_processes': list(foreign.values()),
                      'preexisting_processes': list(baseline.values()),
                      'ownership_scope': 'task-project' if task_project is not None else 'probe',
                      'task_project': str(task_project) if task_project is not None else None,
                      'stage': files[0].read_text(errors='replace').strip() if files[0].exists() else 'awaiting-macro'}
        write_json_atomic(directory / 'session-status.json', diagnostic)
        if on_observation is not None:
            on_observation(diagnostic)
        if exited:
            return diagnostic
        expired = (time.monotonic()-completed_at > exit_timeout if completed_at is not None
                   else time.monotonic()-changed > stage_timeout)
        if completed_at is None and diagnostic['stage'] in unbounded_stages:
            expired = False
        if expired:
            diagnostic['failure'] = 'exit-unconfirmed' if completed_at is not None else 'probe-phase-stalled'
            write_json_atomic(directory / 'session-status.json', diagnostic)
            raise RuntimeError(f"{diagnostic['failure']}; CST retained, inspect {directory}")
        time.sleep(0.5)
