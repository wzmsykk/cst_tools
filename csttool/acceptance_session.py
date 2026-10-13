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


def wait_probe(process, directory, *, stage_timeout=180, exit_timeout=60):
    """Bound idle probe phases, not normal solves. Keep failures for intervention."""
    directory = Path(directory)
    started = changed = time.monotonic()
    signature = None
    completed_at = None
    owned = {}
    foreign = {}
    while True:
        try:
            root = psutil.Process(process.pid)
            for child in [root, *root.children(recursive=True)]:
                owned[(child.pid, child.create_time())] = child
        except psutil.NoSuchProcess:
            pass
        files = [directory / name for name in ('stage.txt', 'cst.log', 'completed.txt', 'failed.txt')]
        current = tuple((p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None for p in files)
        if current != signature:
            signature = current
            changed = time.monotonic()
        if any(p.exists() for p in files[2:]) and completed_at is None:
            completed_at = time.monotonic()
        active = [p.pid for p in owned.values() if p.is_running()]
        # Late child between enumeration and listing: require later ancestry proof.
        for identity in owned:
            foreign.pop(identity, None)
        for record in cst_processes():
            if (record['pid'], record['create_time']) not in owned:
                foreign[(record['pid'], record['create_time'])] = record
        exited = process.poll() is not None and not active
        diagnostic = {'launcher_pid': process.pid, 'owned': [{'pid': k[0], 'create_time': k[1]} for k in owned],
                      'active_pids': active, 'elapsed_seconds': time.monotonic()-started,
                      'exit_confirmed': exited, 'foreign_processes': list(foreign.values()),
                      'stage': files[0].read_text(errors='replace').strip() if files[0].exists() else 'awaiting-macro'}
        write_json_atomic(directory / 'session-status.json', diagnostic)
        if exited:
            return diagnostic
        expired = (time.monotonic()-completed_at > exit_timeout if completed_at is not None
                   else time.monotonic()-changed > stage_timeout)
        if expired:
            diagnostic['failure'] = 'exit-unconfirmed' if completed_at else 'probe-phase-stalled'
            write_json_atomic(directory / 'session-status.json', diagnostic)
            raise RuntimeError(f"{diagnostic['failure']}; CST retained, inspect {directory}")
        time.sleep(0.5)
