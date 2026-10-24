"""Single-controller durable run index; observational events are not solver evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock

from .configuration import write_json_atomic
import hashlib
import os
from weakref import WeakValueDictionary


class _RunState:
    def __init__(self):
        self.lock = RLock()
        self.adopted = None


_STATES = WeakValueDictionary()
_STATES_LOCK = RLock()


def logical_job_id(name, parameters, definition):
    payload = json.dumps({'name': name, 'parameters': dict(parameters), 'definition': definition},
                         sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


class RunStore:
    def __init__(self, project, directory, *, run_id=None):
        self.project = Path(project).resolve()
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        with _STATES_LOCK:
            key = os.path.normcase(str(self.directory.resolve()))
            self._state = _STATES.get(key)
            if self._state is None:
                self._state = _RunState()
                _STATES[key] = self._state
        self.lock = self._state.lock
        manifest = self.directory / 'run.json'
        if not manifest.exists():
            write_json_atomic(manifest, {'schema_version': 1, 'run_id': run_id or self.directory.name,
                                        'project': str(self.project), 'created_utc': self._utc()})

    @staticmethod
    def _utc():
        return datetime.now(timezone.utc).isoformat()

    def reference(self, path):
        path = Path(path).resolve()
        try:
            return {'path': str(path.relative_to(self.project)), 'relative_to': 'project'}
        except ValueError:
            return {'path': str(path), 'relative_to': None}

    def event(self, task_id, event, **fields):
        if event == 'algorithm_adopted':
            return self.ensure_adopted(task_id, **fields)
        if Path(task_id).name != task_id or task_id in ('.', '..'):
            raise ValueError('invalid task identity')
        with self.lock:
            record = {'task_id': task_id, 'event': event, 'utc': self._utc(), **fields}
            path = self.directory / 'tasks' / task_id / 'attempt.json'
            previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            allowed = {
                None: {'submitted', 'reconciled'},
                'submitted': {'received', 'ack_pending'},
                'received': {'acknowledged', 'ack_pending'},
                'acknowledged': {'algorithm_adopted', 'ack_pending'},
                'reconciled': {'algorithm_adopted'},
                'ack_pending': {'reconciled'},
                'algorithm_adopted': set(),
            }
            if event not in allowed.get(previous.get('event'), set()):
                raise ValueError(f"invalid attempt transition: {previous.get('event')} -> {event}")
            self._adoption_events()
            write_json_atomic(path, {**previous, **record})
            try:
                with (self.directory / 'events.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            except BaseException:
                self._state.adopted = None
                raise

    def _adoption_events(self):
        if self._state.adopted is not None:
            return self._state.adopted
        found = {}
        path = self.directory / 'events.jsonl'
        if path.exists():
            with path.open('r+b') as stream:
                while True:
                    offset = stream.tell()
                    line = stream.readline()
                    if not line: break
                    try:
                        record = json.loads(line)
                        if not isinstance(record, dict): raise ValueError('event is not an object')
                    except (UnicodeError, ValueError):
                        if line.endswith(b'\n') or stream.read(1):
                            raise ValueError('corrupt RunStore event journal; preserve evidence')
                        saved = path.with_name('events.truncated-' + hashlib.sha256(line).hexdigest()[:16] + '.bin')
                        if saved.exists() and saved.read_bytes() != line:
                            raise ValueError('truncated journal evidence conflict')
                        if not saved.exists():
                            with saved.open('xb') as evidence:
                                evidence.write(line); evidence.flush(); os.fsync(evidence.fileno())
                        stream.seek(offset); stream.truncate(); stream.flush(); os.fsync(stream.fileno())
                        break
                    if record.get('event') == 'algorithm_adopted':
                        task = record['task_id']
                        if task in found: raise ValueError('duplicate adoption event; preserve evidence')
                        found[task] = record
                    if not line.endswith(b'\n'):
                        stream.seek(0, 2); stream.write(b'\n'); stream.flush(); os.fsync(stream.fileno())
                        break
        self._state.adopted = found
        return found

    def ensure_adopted(self, task_id, *, checkpoint=None, **fields):
        """Single project owner only: journal first, then index, idempotently."""
        if Path(task_id).name != task_id or task_id in ('.', '..'):
            raise ValueError('invalid task identity')
        with self.lock:
            path = self.directory / 'tasks' / task_id / 'attempt.json'
            previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            allowed = {'acknowledged', 'reconciled', 'algorithm_adopted'}
            if checkpoint is not None:
                allowed |= {None, 'submitted', 'received', 'ack_pending'}
            if previous.get('event') not in allowed:
                raise ValueError('adoption requires acknowledged result or verified checkpoint')
            if previous.get('task_id', task_id) != task_id:
                raise ValueError('RunStore task identity mismatch')
            events = self._adoption_events()
            if task_id not in events:
                record = dict(task_id=task_id, event='algorithm_adopted', utc=self._utc(), **fields)
                if checkpoint is not None: record['checkpoint'] = checkpoint
                try:
                    with (self.directory / 'events.jsonl').open('ab') as stream:
                        stream.write((json.dumps(record, ensure_ascii=False) + '\n').encode('utf-8'))
                        stream.flush(); os.fsync(stream.fileno())
                except BaseException:
                    self._state.adopted = None
                    raise
                events[task_id] = record
            if previous.get('event') != 'algorithm_adopted':
                write_json_atomic(path, {**previous, **events[task_id]})

    def artifacts(self, task_id, **paths):
        with self.lock:
            destination = self.directory / 'tasks' / task_id / 'artifacts.json'
            previous = json.loads(destination.read_text(encoding='utf-8')) if destination.exists() else {}
            write_json_atomic(destination, {**previous, **{
                name: {**self.reference(path), 'exists_at_registration': Path(path).exists()}
                for name, path in paths.items() if path is not None}})
