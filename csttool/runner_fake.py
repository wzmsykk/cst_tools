"""Explicit synthetic Runner acceptance executor; not a CST result provider."""
import time
from pathlib import Path
from .configuration import read_json, write_json_atomic
from .hom_scan import AdaptiveHomScanner, ScanCheckpointStore, ScanPolicy, ModeResult


class FakeExecution:
    def __init__(self, project, stop_intent, run_id, update):
        self.project = Path(project)
        self.stop = stop_intent
        self.update = update

    def run(self, payload):
        if payload.get('kind') == 'standard':
            from .standard_batch import StandardBatchAlgorithm
            from .cstmanager import CSTManager
            from .configuration import GlobalSettings, ProjectSettings
            from types import SimpleNamespace
            parent = self
            class Worker:
                def run_task(self, name, *, params):
                    time.sleep(.05)
                    with (parent.project / 'control/fake-calls.jsonl').open('a') as stream:
                        stream.write(name + '\n')
                    radius = float(params.get('R', 100))
                    return {'TaskStatus': 'Success', 'RunName': name, 'PostProcessResult': [
                        {'resultName': 'frequency', 'value': 114742.527 / radius}]}
                def stop(self):
                    pass
                def request_stop(self):
                    parent.stop.request()
            manager = CSTManager(SimpleNamespace(settings=GlobalSettings().with_cst('2022', str(self.project / 'synthetic.exe'))),
                SimpleNamespace(currProjectDir=self.project, settings=ProjectSettings(name='synthetic', cst_filename=Path('synthetic.cst')),
                                get_postprocess_settings=lambda: []), [],
                worker_factory=lambda *a: Worker(), maxTask=payload.get('worker_count', 1))
            try:
                algorithm = StandardBatchAlgorithm(payload['tasks'])
                algorithm.set_resume(payload.get('resume', False))
                algorithm.set_job_manager(manager)
                algorithm.status_listener = self.update
                algorithm.start()
            finally:
                manager.stop()
            return
        settings = payload.get('algorithm', {})
        delay = min(1., max(.01, float(settings.get('fake_delay', .1))))
        folder = self.project / 'save/csv'
        store = ScanCheckpointStore(folder / 'hom_scan_checkpoint.json')
        policy = ScanPolicy(500, 510, 600, window_width=10)
        report, pending = store.load(policy, {'synthetic': True}) if payload.get('resume') else (None, None)
        if store.path.exists() and not payload.get('resume'):
            raise ValueError('synthetic checkpoint exists; resume explicitly')
        self.update(state='RUNNING', phase='running')
        def solve(request):
            time.sleep(delay)
            with (self.project / 'control/fake-calls.jsonl').open('a') as stream:
                stream.write(f'{request.solve_lo},{request.solve_hi}\n')
            return [ModeResult(1, request.solve_lo + 5, {'R/Q': 1.})]
        def checkpoint(report, pending):
            store.save(policy, {'synthetic': True}, report, pending)
            self.update(coverage=read_json(store.path)['coverage'], mode_count=len(report.modes))
        AdaptiveHomScanner(policy).run(solve, report=report, pending=pending,
            checkpoint=checkpoint,
            should_stop=self.stop.is_set)

    def request_stop(self):
        self.stop.request()

    def recover(self):
        write_json_atomic(self.project / 'control/fake-recovered.json', {'synthetic': True})

    def recovery_required(self):
        return False

    def close(self):
        pass
