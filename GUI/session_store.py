"""Per-user GUI selection only; never execution authority or a task replay queue."""
import os
from pathlib import Path
from csttool.configuration import read_json, write_json_atomic


class GuiSessionStore:
    def __init__(self, path=None):
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.config')
        self.path = Path(path) if path is not None else base / 'CSTTools/gui-session.json'

    def last_project(self):
        if not self.path.exists():
            return None
        value = read_json(self.path)
        if not isinstance(value, dict) or value.get('schema_version') != 1 or not isinstance(value.get('project'), str):
            raise ValueError('unsupported GUI session selection')
        project = Path(value['project'])
        if not project.is_absolute() or not project.is_dir():
            raise ValueError('previous project directory no longer exists: ' + str(project))
        return project.resolve()

    def remember(self, project):
        write_json_atomic(self.path, {'schema_version': 1, 'project': str(Path(project).resolve())})
