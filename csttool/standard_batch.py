"""Finite standard task batches with durable adoption, using the existing Manager."""
import hashlib
import json
from pathlib import Path
from .configuration import read_json, write_json_atomic
from .cstmanager import SimulationTask
from .hom_scan import ScanInterrupted, ScanReport
from .hom_scan_algorithm import HomScanAlgorithm


class StandardBatchAlgorithm:
    def __init__(self, tasks):
        self.tasks = tasks
        self.settings = HomScanAlgorithm(None, None)
        self.resume = False
        self.manager = None
        self.status_listener = None

    def get_editable_attributes(self):
        return self.settings.get_editable_attributes()

    def set_editable_attributes(self, values):
        self.settings.set_editable_attributes(values)

    def set_resume(self, resume):
        self.resume = resume

    def set_job_manager(self, manager):
        self.manager = manager

    def set_cst_parameters(self, parameters):
        pass

    def validate_postprocess_settings(self, settings):
        from .postprocess_cst import CstPostProcessor
        CstPostProcessor().configure(settings)

    def start(self):
        signature = hashlib.sha256(json.dumps(self.tasks, sort_keys=True).encode()).hexdigest()
        path = self.manager.currProjectDir / 'save/standard_batch_checkpoint.json'
        state = {'schema_version': 1, 'task_signature': signature, 'results': [], 'pending_index': 0}
        if path.exists():
            if not self.resume:
                raise ValueError('standard checkpoint exists; resume explicitly')
            state = read_json(path)
            if state['task_signature'] != signature:
                raise ValueError('standard tasks changed; cannot resume')
            if state['results']:
                snapshot = state['results'][-1].get('ProjectSnapshot')
                if snapshot:
                    self.manager.restore_project_snapshot(snapshot)
        if self.status_listener:
            self.status_listener(completed_tasks=state['pending_index'], total_tasks=len(self.tasks))
        for index in range(state['pending_index'], len(self.tasks)):
            if self.manager.stop_requested:
                raise ScanInterrupted(ScanReport(), [])
            state['pending_index'] = index
            write_json_atomic(path, state)
            task = self.tasks[index]
            result = self.manager.execute(SimulationTask(task['parameters'], task['job'],
                retry_count=1, continue_from_snapshot=True))
            if result.get('TaskStatus') != 'Success':
                if self.manager.stop_requested:
                    raise ScanInterrupted(ScanReport(), [])
                raise RuntimeError(result.get('FailureReport', 'standard task failed'))
            state['results'].append(result)
            state['pending_index'] = index + 1
            write_json_atomic(path, state)
            if result.get('TaskID'):
                self.manager.adopt_result(result['TaskID'])
            if self.status_listener:
                self.status_listener(completed_tasks=index + 1, total_tasks=len(self.tasks))
        return state
