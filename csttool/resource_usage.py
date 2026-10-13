"""Best-effort, per-task process-tree and host resource observations."""
from datetime import datetime, timezone
from functools import wraps
import json
import time
from uuid import uuid4

import psutil


def sample_resources(process):
    if process is None or process.poll() is not None:
        return None
    root = psutil.Process(process.pid)
    members = [root, *root.children(recursive=True)]
    counters = {}
    rss = private = 0
    errors = []
    for member in members:
        try:
            memory = member.memory_info()
            cpu = member.cpu_times()
            io = member.io_counters()
            counters[f'{member.pid}:{member.create_time()}'] = {
                'cpu_seconds': cpu.user + cpu.system,
                'read_bytes': io.read_bytes, 'write_bytes': io.write_bytes,
            }
            rss += memory.rss
            private += getattr(memory, 'private', memory.rss)
        except (psutil.Error, OSError) as exc:
            errors.append(type(exc).__name__)
    host = psutil.virtual_memory()
    return {'rss_bytes': rss, 'private_bytes': private, 'processes': counters,
            'logical_cpu_count': psutil.cpu_count(),
            'host_total_bytes': host.total, 'host_available_bytes': host.available,
            'host_memory_percent': host.percent, 'sample_errors': errors}


class ResourceUsageRecorder:
    def __init__(self, root, worker, session, job, sampler=sample_resources):
        self.directory = root / 'resource_usage' / uuid4().hex
        self.directory.mkdir(parents=True)
        self.identity = {'worker': worker, 'session': session, 'job': job, 'task_id': None}
        self.sampler = sampler
        self.started = time.monotonic()
        self.start_utc = datetime.now(timezone.utc).isoformat()
        self.next_sample = self.started
        self.previous = {}
        self.totals = dict(cpu_seconds=0.0, read_bytes=0, write_bytes=0)
        self.peak_rss = self.peak_private = self.count = self.errors = 0

    def sample(self, process, *, force=False):
        now = time.monotonic()
        if not force and now < self.next_sample:
            return
        self.next_sample = now + 30.0
        try:
            data = self.sampler(process)
            if data is None:
                return
            for identity, counters in data['processes'].items():
                previous = self.previous.get(identity)
                if previous is not None:
                    for key in self.totals:
                        self.totals[key] += max(0, counters[key] - previous[key])
                self.previous[identity] = counters
            self.count += 1
            self.errors += len(data['sample_errors'])
            self.peak_rss = max(self.peak_rss, data['rss_bytes'])
            self.peak_private = max(self.peak_private, data['private_bytes'])
            record = {**self.identity, 'utc': datetime.now(timezone.utc).isoformat(),
                      'elapsed_seconds': now - self.started, **data}
            with (self.directory / 'samples.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        except (psutil.Error, OSError, ValueError):
            self.errors += 1

    def finish(self, status, failure=None):
        elapsed = time.monotonic() - self.started
        summary = {**self.identity, 'status': status, 'failure': failure,
                   'start_utc': self.start_utc,
                   'elapsed_seconds': elapsed,
                   'observed_average_cpu_percent_one_core': (
                       100 * self.totals['cpu_seconds'] / elapsed
                       if self.count and elapsed > 0 else None),
                   'sample_count': self.count, 'sample_errors': self.errors,
                   'peak_rss_bytes': self.peak_rss if self.count else None,
                   'peak_private_bytes': self.peak_private if self.count else None,
                   'observed_counter_deltas': self.totals if self.count else None,
                   'counter_semantics': 'sampled lower-bound deltas; first observation is baseline'}
        (self.directory / 'summary.json').write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        return summary


def record_worker_usage(method):
    @wraps(method)
    def wrapped(self, result_name, *, params):
        with self._lock:
            recorder = None
            try:
                recorder = ResourceUsageRecorder(getattr(self, 'observation_root', self.root), self.ID, self.session_id, result_name)
            except (OSError, AttributeError):
                self.logger.warning('无法创建资源统计记录，任务继续运行', exc_info=True)
            self._resource_usage = recorder
            status, failure = 'Failure', None
            try:
                if recorder:
                    recorder.sample(getattr(self, '_process', None), force=True)
                result = method(self, result_name, params=params)
                status, failure = result['TaskStatus'], result.get('FailureReport')
                return result
            except Exception as exc:
                failure = f'{type(exc).__name__}: {exc}'
                raise
            finally:
                if recorder:
                    try:
                        recorder.sample(getattr(self, '_process', None), force=True)
                        summary = recorder.finish(status, failure)
                        self.logger.info('Worker 资源统计 | job=%s status=%s elapsed_seconds=%.1f peak_private_bytes=%s samples=%s path=%s', result_name, status, summary['elapsed_seconds'], summary['peak_private_bytes'], summary['sample_count'], recorder.directory)
                    except (OSError, psutil.Error, ValueError):
                        self.logger.warning('资源统计写入失败，保留原任务结果', exc_info=True)
                self._resource_usage = None
    return wrapped
