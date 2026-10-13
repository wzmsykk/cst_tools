import json
from types import SimpleNamespace

import pytest

from csttool.resource_usage import ResourceUsageRecorder, record_worker_usage


def sample(cpu, memory=100):
    return {'rss_bytes': memory, 'private_bytes': memory,
            'sample_errors': [], 'processes': {'1:100': {
                'cpu_seconds': cpu, 'read_bytes': cpu * 10, 'write_bytes': cpu * 20}}}


def test_resource_summary_uses_task_deltas_not_worker_lifetime(tmp_path):
    values = iter([sample(100), sample(103, 200)])
    recorder = ResourceUsageRecorder(tmp_path, '0', 'session', 'mode', lambda _: next(values))
    recorder.identity['task_id'] = 'task'
    recorder.sample(None, force=True)
    recorder.sample(None, force=True)
    summary = recorder.finish('Success')
    assert summary['observed_counter_deltas'] == {'cpu_seconds': 3, 'read_bytes': 30, 'write_bytes': 60}
    assert summary['peak_private_bytes'] == 200
    assert summary['task_id'] == 'task'
    lines = (recorder.directory / 'samples.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])['job'] == 'mode'


def test_no_measurement_is_reported_as_unknown_not_zero(tmp_path):
    recorder = ResourceUsageRecorder(tmp_path, '0', 'session', 'mode', lambda _: None)
    recorder.sample(None, force=True)
    assert recorder.finish('Failure')['peak_private_bytes'] is None


def test_failed_sampling_does_not_interrupt_task_statistics(tmp_path):
    def denied(_):
        raise PermissionError('denied')
    recorder = ResourceUsageRecorder(tmp_path, '0', 'session', 'mode', denied)
    recorder.sample(None, force=True)
    summary = recorder.finish('Failure', 'solver failed')
    assert summary['sample_errors'] == 1
    assert summary['failure'] == 'solver failed'


def test_wrapper_finalizes_exception_without_hiding_original(tmp_path, monkeypatch):
    import logging
    from threading import RLock
    monkeypatch.setattr('csttool.resource_usage.sample_resources', lambda _: None)
    class Worker:
        root = tmp_path
        ID = '0'
        session_id = 'session'
        logger = logging.getLogger('resources-test')
        _lock = RLock()
        @record_worker_usage
        def run(self, name, *, params):
            raise RuntimeError('original failure')
    with pytest.raises(RuntimeError, match='original failure'):
        Worker().run('mode', params={})
    summary_path = next(tmp_path.glob('resource_usage/*/summary.json'))
    assert json.loads(summary_path.read_text(encoding='utf-8'))['status'] == 'Failure'
