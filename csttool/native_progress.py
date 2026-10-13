"""Observe CST's overwritten progress.log; preserve raw stage vocabulary."""
from datetime import datetime, timezone
import json
import locale
import time

from .configuration import write_json_atomic
from .cst_progress import CstProgressEvent


def parse_native_progress(text):
    fields = {}
    for line in text.splitlines():
        parts = line.split(':', 2)
        if len(parts) == 3:
            fields[parts[0]] = {'type': parts[1], 'value': parts[2]}
    if not all(key in fields for key in ('Header', 'Text', 'Progress')):
        return None  # Ignore partially overwritten files.
    try:
        percent = int(fields['Progress']['value'])
    except ValueError:
        return None
    if not 0 <= percent <= 100:
        return None
    return {'header': fields['Header']['value'], 'text': fields['Text']['value'],
            'percent': percent, 'fields': fields}


class NativeProgressTracker:
    def __init__(self, path, directory, worker, session, task, logger, callback=None):
        self.path, self.directory, self.logger = path, directory, logger
        self.identity = {'worker': worker, 'session': session, 'task_id': task.task_id,
                         'parameters': {p.name: p.value for p in task.parameters}}
        self.started = time.monotonic()
        self.next_poll = self.started
        self.baseline = self._fingerprint()
        self.last_content = None
        self.last_observation = None
        self.stages = []
        self.error_reported = False
        self.callback = callback

    def _fingerprint(self):
        try:
            stat = self.path.stat()
            return (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    def poll(self, *, force=False):
        now = time.monotonic()
        if not force and now < self.next_poll:
            return
        self.next_poll = now + 0.2
        fingerprint = self._fingerprint()
        if fingerprint is None or fingerprint == self.baseline:
            return  # Do not attribute the previous task's retained file to this one.
        try:
            raw = self.path.read_bytes()
            if fingerprint != self._fingerprint():
                return
            try:
                text = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = raw.decode(locale.getpreferredencoding(False), errors='replace')
            parsed = parse_native_progress(text)
            if parsed is None:
                return
            self.last_observation = fingerprint
            if raw == self.last_content:
                return
            if callable(self.callback):
                parameters = self.identity['parameters']
                def number(name):
                    try:
                        return float(parameters.get(name))
                    except (TypeError, ValueError):
                        return None
                try:
                    self.callback(CstProgressEvent(
                        self.identity['worker'], self.identity['task_id'], number('fmin'),
                        number('fmax'), parsed['header'], None, parsed['percent'],
                        parsed['text'], time.time(), self.identity['session'], 'progress.log'))
                except Exception:
                    self.logger.debug('原生进度回调失败，不影响求解', exc_info=True)
            record = {**self.identity, 'utc': datetime.now(timezone.utc).isoformat(),
                      'elapsed_seconds': now - self.started, 'source': str(self.path),
                      'source_mtime_ns': fingerprint[0], 'raw': text, **parsed}
            self.directory.mkdir(parents=True, exist_ok=True)
            with (self.directory / 'events.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            self.last_content = raw
            if parsed['header'] not in self.stages:
                self.stages.append(parsed['header'])
                write_json_atomic(self.directory / 'stages.json', {
                    **self.identity, 'observed_headers': self.stages,
                    'semantics': 'observed first-appearance order, not a complete CST stage specification'})
                self.logger.info('CST 原生日志观察到阶段 | task=%s header=%s text=%s',
                                 self.identity['task_id'], parsed['header'], parsed['text'])
        except (OSError, ValueError) as exc:
            if not self.error_reported:
                self.logger.warning('CST 原生进度记录失败，不影响求解：%s', exc)
                self.error_reported = True
