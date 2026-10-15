"""GUI draft state only; production execution always belongs to the Runner."""
import json
import logging
from pathlib import Path
from uuid import uuid4
from csttool.cst_installations import discover_cst_installations, validate_cst_installation
from csttool.scan_settings import default_hom_settings, validate_hom_settings
from csttool.runner_client import RunnerClient
from install_compat import resource_path


class RunnerBackend:
    supports_cst_backend_selection = True
    uses_runner = True

    def __init__(self):
        self.logger = logging.getLogger('cst.gui.' + uuid4().hex)
        self.logger.setLevel(logging.DEBUG)
        self.project = None
        self.source = None
        self.installation = None
        self.algorithm = default_hom_settings()
        self.postprocess = json.loads(Path(resource_path('data/defaultPPS.json')).read_text(encoding='utf-8'))
        self.client = None

    def select_project_directory(self, path):
        self.project = str(Path(path).resolve())
        self.client = RunnerClient(self.project)

    def select_cst_file(self, path):
        self.source = str(Path(path).resolve())

    def get_cst_installations(self):
        return discover_cst_installations()

    def get_selected_cst_installation(self):
        return self.installation

    def select_cst_installation(self, version, executable):
        self.installation = validate_cst_installation(version, executable)
        return self.installation

    def get_algorithm_settings(self):
        return dict(self.algorithm)

    def update_algorithm_settings(self, values):
        self.algorithm = validate_hom_settings({**self.algorithm, **values})

    def get_postprocess_settings(self):
        return list(self.postprocess)

    def update_postprocess_settings(self, values):
        self.postprocess = list(values)

    def run_payload(self, resume, worker_count):
        return json.loads(json.dumps({'resume': resume, 'worker_count': worker_count, 'source_project': self.source,
                'algorithm': self.algorithm, 'postprocess': self.postprocess,
                'installation': ({'version': self.installation.version,
                                  'executable': str(self.installation.executable)} if self.installation else None)}))
