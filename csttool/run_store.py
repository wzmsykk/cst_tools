"""Single-controller durable run index; observational events are not solver evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock

from .configuration import write_json_atomic


class RunStore:
    def __init__(self, project, directory):
        self.project = Path(project).resolve()
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        manifest = self.directory / 'run.json'
        if not manifest.exists():
            write_json_atomic(manifest, {'schema_version': 1, 'run_id': self.directory.name,
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
        if Path(task_id).name != task_id or task_id in ('.', '..'):
            raise ValueError('invalid task identity')
        with self.lock:
            record = {'task_id': task_id, 'event': event, 'utc': self._utc(), **fields}
            with (self.directory / 'events.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            path = self.directory / 'tasks' / task_id / 'attempt.json'
            previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            write_json_atomic(path, {**previous, **record})

    def artifacts(self, task_id, **paths):
        with self.lock:
            write_json_atomic(self.directory / 'tasks' / task_id / 'artifacts.json', {
                name: {**self.reference(path), 'exists_at_registration': Path(path).exists()}
                for name, path in paths.items() if path is not None})
