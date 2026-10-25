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

    def __init__(self, *, session_store=None):
        self.logger = logging.getLogger('cst.gui.' + uuid4().hex)
        self.logger.setLevel(logging.DEBUG)
        self.project = None
        self.source = None
        self.installation = None
        self.algorithm = default_hom_settings()
        self.postprocess = json.loads(Path(resource_path('data/defaultPPS.json')).read_text(encoding='utf-8'))
        self.client = None
        self.session_store = session_store
        self.restored_worker_count = 1
        self.restore_message = None

    def select_project_directory(self, path):
        self.project = str(Path(path).resolve())
        self.client = RunnerClient(self.project)
        if self.session_store is not None:
            try:
                self.session_store.remember(self.project)
            except (OSError, ValueError) as exc:
                self.logger.warning('项目已选择，但上次项目记录未能保存: %s', exc)

    def restore_last_project(self):
        if self.session_store is None:
            return False
        try:
            project = self.session_store.last_project()
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.restore_message = '上次项目无法自动恢复，请手动选择：' + str(exc)
            self.logger.warning(self.restore_message)
            return False
        if project is None:
            return False
        self.select_project_directory(project)
        # Only read known project metadata. The Runner/checkpoint owns execution state.
        manifest = project / 'save/csv/scan_manifest.json'
        try:
            if manifest.is_file():
                value = json.loads(manifest.read_text(encoding='utf-8'))
                if value.get('schema_version') != 3:
                    raise ValueError('unsupported HOM manifest')
                start, width, stop = float(value['frequency_start']), float(value['initial_window']), float(value['frequency_stop'])
                from csttool.hom_scan import ScanPolicy
                ScanPolicy(start, start + width, stop)
                settings = dict(fmin=start, fmax=start + width, endfreq=stop,
                    mesh_cells_per_wavelength=value['mesh_cells_per_wavelength'],
                    preprocess_modify_mesh=value['preprocess_modify_mesh'])
                self.algorithm = validate_hom_settings({**self.algorithm, **settings})
                self.source = str(value['source_project']) if value.get('source_project') else None
                self.restored_worker_count = max(1, int(value['worker_count']))
                executable = value.get('cst_executable')
                if executable:
                    self.installation = validate_cst_installation(value['cst_version'], executable)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            self.logger.warning('项目已找回，部分运行设置无法读取；继续连接后台查看状态: %s', exc)
        try:
            postprocess = project / 'pps.json'
            if postprocess.is_file():
                value = json.loads(postprocess.read_text(encoding='utf-8'))
                if not isinstance(value, list): raise ValueError('postprocess must be a list')
                self.postprocess = value
        except (OSError, ValueError, TypeError) as exc:
            self.logger.warning('原后处理设置无法显示，请检查项目配置: %s', exc)
        self.restore_message = '已找回上次项目，正在连接后台并读取历史状态；未提交计算'
        return True

    @property
    def has_checkpoint(self):
        if not self.project:
            return False
        project = Path(self.project)
        return any((project / name).exists() for name in (
            'save/csv/hom_scan_checkpoint.json', 'save/csv/scan_manifest.json',
            'save/standard_batch_checkpoint.json'))

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
