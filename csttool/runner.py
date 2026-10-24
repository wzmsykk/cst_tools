"""Independent, loopback-only local Runner. No Qt or GUI dependencies."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import threading
import time
from uuid import uuid4

from .configuration import read_json, write_json_atomic
from .execution_contract import StopIntent, validate_command
from .hom_scan import ScanInterrupted
from .runner_ownership import RunnerOwnership, protect_directory
from .project_recovery_state import EXPLICIT_RECOVERY_STATES, persisted_project_status

ACTIVE = {'PREPARING', 'RUNNING', 'STOPPING', 'RECOVERING'}


class Runner:
    def __init__(self, project, executor_factory=None):
        self.project = Path(project).resolve()
        self.control = self.project / 'control'
        protect_directory(self.control)
        self.ownership = RunnerOwnership(self.control / 'runner.lock').acquire()
        project_identity = self.control / 'project.json'
        if not project_identity.exists():
            write_json_atomic(project_identity, {'schema_version': 1, 'project_id': uuid4().hex})
        self.project_id = read_json(project_identity)['project_id']
        self.instance_id = uuid4().hex
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.executor_factory = executor_factory or LocalExecution
        self.executor = None
        self.worker = None
        self.stop_delivery = None
        self.shutdown_requested = threading.Event()
        self.owner_client = None
        self.owner_seen = 0.0
        self.control_revision = 0
        self.status = {'schema_version': 1, 'instance_id': self.instance_id,
                       'project_id': self.project_id,
                       'project': str(self.project), 'run_id': None, 'version': 0,
                       'state': 'IDLE', 'phase': '', 'error': None,
                       'session_safety': 'unknown', 'last_progress': None}
        previous = self.control / 'status.json'
        if previous.exists():
            old = read_json(previous)
            for key in ('run_id', 'state', 'phase', 'error', 'session_safety', 'last_progress',
                        'log_directory', 'log_history', 'coverage', 'mode_count',
                        'completed_tasks', 'total_tasks', 'artifacts', 'lifecycle', 'error_diagnostic', 'cleanup_diagnostic'):
                if key in old:
                    self.status[key] = old[key]
            if self.status.get('lifecycle'):
                self.status['lifecycle'] = dict(self.status['lifecycle'], historical=True)
            if old.get('state') in ACTIVE or old.get('state') == 'RECOVERY_REQUIRED':
                self.status['state'] = 'RECOVERY_REQUIRED'
                self.status['phase'] = 'recovery-required'
                self.status['error'] = 'Previous controller stopped; reconcile sessions before resume'
        if not self.status.get('log_directory') and not self.status.get('log_history'):
            # Pre-Runner projects have file logs but no control/status log pointers.
            legacy = sorted(path.parent for path in self.project.glob('logs/*/application.jsonl')
                            if path.resolve().is_relative_to(self.project))
            if legacy:
                self.status['log_history'] = [dict(run_id=None, directory=str(path)) for path in legacy[:-1]]
                self.status['log_directory'] = str(legacy[-1])
        for command_path in (self.control / 'commands').glob('*.json'):
            intent = read_json(command_path)
            if intent['command']['operation'] == 'start':
                run_id = intent['result']['run_id']
                if not run_id:
                    continue
                if not (self.control / 'runs' / run_id / 'outcome.json').exists():
                    self.status.update(state='RECOVERY_REQUIRED', run_id=run_id,
                                       error='Unfinished durable start intent requires reconciliation')
        checkpoint = self.project / 'save/csv/hom_scan_checkpoint.json'
        if checkpoint.exists():
            document = read_json(checkpoint)
            self.status.update(coverage=document.get('coverage'),
                               mode_count=len(document.get('report', {}).get('modes', [])))
        self._reconcile_project_state()
        self._save_status()

    def _reconcile_project_state(self):
        """Project recovery and session closure are separate facts, not aliases."""
        if self.status['state'] in ACTIVE:
            return
        try:
            status = persisted_project_status(self.project)
            reason = f'项目状态为 {status}，请先执行显式恢复，再继续扫描' if status in EXPLICIT_RECOVERY_STATES else None
        except Exception as exc:
            status = 'UNREADABLE'
            reason = f'项目配置无法核验，需恢复检查：{type(exc).__name__}: {exc}'
        self.status['project_task_status'] = status
        if reason and self.status['state'] != 'RECOVERY_REQUIRED':
            self.status.update(state='RECOVERY_REQUIRED', phase='recovery-required',
                previous_error=self.status.get('error'), error=reason, recovery_reason=reason)
            self._save_status()

    def _save_status(self):
        self.status['version'] += 1
        write_json_atomic(self.control / 'status.json', self.status)

    def update(self, **values):
        with self.lock:
            directory = self.status.get('log_directory')
            if directory and 'log_directory' in values and values['log_directory'] != directory:
                history = list(self.status.get('log_history', []))
                if not any(item['directory'] == directory for item in history):
                    history.append(dict(run_id=self.status['run_id'], directory=directory))
                self.status['log_history'] = history
            self.status.update(values)
            try:
                self._save_status()
            except OSError as exc:
                self.status.update(state='RECOVERY_REQUIRED', session_safety='unknown',
                                   error=f'control persistence failed: {exc}')
                if hasattr(self, 'stop_intent'):
                    self.stop_intent.event.set()
                raise

    def snapshot(self):
        with self.lock:
            self._reconcile_project_state()
            remaining = max(0., 10 - (time.monotonic() - self.owner_seen)) if self.owner_client else 0.
            value = dict(self.status, owner_client=self.owner_client,
                         execution_active=bool(self.executor is not None
                             or self.worker and self.worker.is_alive()
                             or self.stop_delivery and self.stop_delivery.is_alive()),
                         runtime={'pid': os.getpid(), 'python': sys.executable,
                                  'source_root': str(Path(__file__).resolve().parents[1])},
                         control_lease_valid=remaining > 0, control_lease_remaining=remaining,
                         control_revision=self.control_revision)
        return value

    def heartbeat(self, client):
        with self.lock:
            if client == self.owner_client and time.monotonic() - self.owner_seen < 10:
                self.owner_seen = time.monotonic()

    def command_record(self, request_id):
        validate_command(dict(schema_version=1, request_id=request_id, client_id='query', operation='claim'))
        with self.lock:
            path = self.control / 'commands' / (request_id + '.json')
            return read_json(path) if path.exists() else {'found': False}

    def _stop_run(self):
        self.stop_intent.request()
        self.update(state='STOPPING', phase='stopping')
        executor = self.executor
        if executor and not (self.stop_delivery and self.stop_delivery.is_alive()):
            self.stop_delivery = threading.Thread(target=self._deliver_stop, args=(executor,), daemon=True)
            self.stop_delivery.start()

    def events(self, cursor=0, limit=100):
        from .event_replay import read_events
        with self.lock:
            directories = [item['directory'] for item in self.status.get('log_history', [])]
            if self.status.get('log_directory'):
                directories.append(self.status['log_directory'])
            elif not directories:
                directories.append(str(self.control))
        paths = list(dict.fromkeys(str(Path(directory).resolve() / 'application.jsonl')
                    for directory in directories if Path(directory).resolve().is_relative_to(self.project)))
        if not paths:
            paths = [str(self.control / 'application.jsonl')]
        source = cursor.get('source') if isinstance(cursor, dict) else None
        index = paths.index(source) if source in paths else 0
        path = Path(paths[index])
        position = cursor if source == str(path) else 0
        try:
            result = read_events(path, position, limit)
            size = path.stat().st_size if path.exists() else 0
        except OSError as exc:
            state = dict(position) if isinstance(position, dict) else {'offset': 0}
            error = f'{type(exc).__name__}: {exc}'
            events = [] if state.get('read_error') == error else [{
                'level': 'WARNING', 'message': '日志暂时无法读取；任务状态不受影响',
                'context': {'raw_file': str(path), 'reason': error}}]
            state.update(source=str(path), read_error=error)
            if index < len(paths) - 1:
                state = {'source': paths[index + 1], 'offset': 0}
            return dict(schema_version=2, instance_id=self.instance_id, cursor=state, events=events)
        state = result['cursor'] if isinstance(result['cursor'], dict) else {'offset': 0}
        state.pop('read_error', None)
        state['source'] = str(path)
        result['cursor'] = state
        if index < len(paths) - 1 and state['offset'] >= size:
            if not path.exists():
                result['events'].append({'level': 'WARNING', 'message': '旧日志文件已不存在，继续读取后续运行日志',
                                        'context': {'raw_file': str(path)}})
            result['cursor'] = {'source': paths[index + 1], 'offset': 0}
        elif index < len(paths) - 1 and not result['events'] and (
                state['offset'] == (position.get('offset', 0) if isinstance(position, dict) else 0)):
            # A finalized history file may end in an interrupted partial write.
            result['events'].append({'level': 'WARNING', 'message': '旧日志尾行未写完，继续读取后续运行日志',
                'context': {'raw_file': str(path), 'byte_offset': state['offset']}})
            result['cursor'] = {'source': paths[index + 1], 'offset': 0}
        return dict(result, instance_id=self.instance_id)

    def command(self, command):
        validate_command(command)
        encoded = json.dumps(command, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        path = self.control / 'commands' / (command['request_id'] + '.json')
        with self.lock:
            self._reconcile_project_state()
            if path.exists():
                existing = read_json(path)
                if existing['digest'] != digest:
                    raise ValueError('request_id content conflict')
                if command['operation'] == 'claim':
                    if self.owner_client != command['client_id'] or time.monotonic() - self.owner_seen >= 10:
                        raise ValueError('claim receipt expired; request a new claim')
                if command['operation'] != 'claim' or existing['result']['instance_id'] == self.instance_id:
                    return existing['result']
            op = command['operation']
            client = command['client_id']
            payload = command.get('payload', {})
            if op == 'claim':
                if self.owner_client not in (None, client) and time.monotonic() - self.owner_seen < 10:
                    raise ValueError('control belongs to another client; release it first')
                self.owner_client = client
                self.owner_seen = time.monotonic()
                self.control_revision += 1
            elif self.owner_client != client or time.monotonic() - self.owner_seen >= 10:
                raise ValueError('claim control before modifying the project')
            if op == 'cancel_start':
                target = payload.get('start_request_id')
                record = self.command_record(target)
                tombstone = self.control / 'cancelled-starts' / (target + '.json')
                if record.get('found') is not False:
                    if record['command']['operation'] != 'start':
                        raise ValueError('target is not a start request')
                    target_run = record['result']['run_id']
                    if target_run and target_run == self.status['run_id'] and self.status['state'] in ACTIVE:
                        self._stop_run()
                    elif target_run and not (self.control / 'runs' / target_run / 'outcome.json').exists():
                        raise ValueError('target start requires session reconciliation')
                else:
                    target_run = None
                result = dict(request_id=command['request_id'], accepted=True, run_id=target_run,
                              instance_id=self.instance_id, cancelled=target_run is None)
                write_json_atomic(tombstone, result)
                write_json_atomic(path, dict(digest=digest, command=command, result=result))
                return result
            if op == 'start' and (self.control / 'cancelled-starts' / (command['request_id'] + '.json')).exists():
                result = dict(request_id=command['request_id'], accepted=False, cancelled=True,
                              run_id=None, instance_id=self.instance_id)
                write_json_atomic(path, dict(digest=digest, command=command, result=result))
                return result
            state = self.status['state']
            if op in {'start', 'recover', 'shutdown'} and (state in ACTIVE or self.worker and self.worker.is_alive()
                    or self.stop_delivery and self.stop_delivery.is_alive()):
                raise ValueError('run still active')
            if op == 'start' and state == 'RECOVERY_REQUIRED':
                raise ValueError('recover previous sessions first')
            if op == 'stop' and (command.get('run_id') != self.status['run_id'] or state not in ACTIVE):
                raise ValueError('stale run_id or no active run')
            if op == 'shutdown' and state == 'RECOVERY_REQUIRED':
                raise ValueError('session safety unresolved')
            if op == 'start':
                validate_run_payload(payload)
                if not payload.get('resume', False) and any(path.exists() for path in (
                        self.project / 'save/csv/hom_scan_checkpoint.json',
                        self.project / 'save/csv/scan_manifest.json',
                        self.project / 'save/standard_batch_checkpoint.json')):
                    raise ValueError('checkpoint exists; resume or use a new project')
            run_id = uuid4().hex if op == 'start' else self.status['run_id']
            result = {'request_id': command['request_id'], 'accepted': True, 'run_id': run_id,
                      'instance_id': self.instance_id}
            # Persist intent before any execution. A crash here is not replayed blindly.
            write_json_atomic(path, {'digest': digest, 'command': command, 'result': result})
            if op == 'release':
                self.owner_client = None
            elif op in ('start', 'recover'):
                self.stop_intent = StopIntent(self.control / 'runs' / str(run_id or 'recovery') / 'stop.json')
                self.update(run_id=run_id, state='PREPARING' if op == 'start' else 'RECOVERING',
                            phase='initializing' if op == 'start' else 'recovering', error=None,
                            recovery_reason=None,
                            lifecycle=None, error_diagnostic=None, cleanup_diagnostic=None,
                            session_safety='unknown', log_directory=None, last_progress=None,
                            completed_tasks=0, total_tasks=len(payload.get('tasks', [])))
                self.worker = threading.Thread(target=self._execute, args=(op, payload), daemon=False)
                self.worker.start()
            elif op == 'stop':
                self._stop_run()
            elif op == 'shutdown':
                self.shutdown_requested.set()
            return result

    def _deliver_stop(self, executor):
        try:
            executor.request_stop()
        except Exception as exc:
            from .lifecycle_diagnostics import error_diagnostic
            self.update(state='RECOVERY_REQUIRED', error=f'stop failed: {exc}', session_safety='unknown',
                        error_diagnostic=error_diagnostic(exc, 'stop-delivery'))

    def _execute(self, operation, payload):
        executor = None
        try:
            options = {'payload': payload if operation == 'start' else None} if self.executor_factory is LocalExecution else {}
            executor = self.executor_factory(self.project, self.stop_intent, self.status['run_id'], self.update, **options)
            with self.lock:
                self.executor = executor
            if operation == 'recover':
                executor.recover()
                target = 'IDLE'
            else:
                executor.run(payload)
                target = 'INTERRUPTED' if self.stop_intent.is_set() else 'COMPLETED'
            if self.stop_delivery:
                self.stop_delivery.join(5)
                if self.stop_delivery.is_alive():
                    raise RuntimeError('stop delivery not confirmed')
            if self._needs_recovery(executor):
                target = 'RECOVERY_REQUIRED'
            with self.lock:
                if self.status['state'] == 'RECOVERY_REQUIRED':
                    target = 'RECOVERY_REQUIRED'
                self.update(state=target, phase=target.lower(),
                            session_safety=self._session_safety(executor, target == 'RECOVERY_REQUIRED'))
        except Exception as exc:
            interrupted = isinstance(exc, ScanInterrupted)
            recovery = self._needs_recovery(executor)
            from .lifecycle_diagnostics import error_diagnostic
            self.update(state='RECOVERY_REQUIRED' if recovery else ('INTERRUPTED' if interrupted else 'FAILED'),
                        phase='recovery-required' if recovery else ('interrupted' if interrupted else 'failed'),
                        error=None if interrupted else f'{type(exc).__name__}: {exc}',
                        session_safety=self._session_safety(executor, recovery),
                        error_diagnostic=None if interrupted else error_diagnostic(exc, self.status.get('phase')))
        finally:
            try:
                if executor:
                    executor.close()
            except Exception as exc:
                from .lifecycle_diagnostics import error_diagnostic
                self.update(state='RECOVERY_REQUIRED', error=f'cleanup failed: {exc}', session_safety='unknown',
                            cleanup_diagnostic=error_diagnostic(exc, 'cleanup'))
            finally:
                probe = getattr(executor, 'lifecycle_facts', None)
                if callable(probe):
                    try:
                        facts = probe()
                        values = dict(lifecycle=facts, session_safety=facts['session_safety'])
                        if facts.get('recovery_required'):
                            values.update(state='RECOVERY_REQUIRED', phase='recovery-required')
                        self.update(**values)
                    except Exception as exc:
                        from .lifecycle_diagnostics import error_diagnostic
                        self.update(state='RECOVERY_REQUIRED', phase='recovery-required',
                            session_safety='unknown', lifecycle=dict(
                            schema_version=1, session_safety='unknown',
                            diagnostic=error_diagnostic(exc, 'lifecycle-probe')))
                with self.lock:
                    self.executor = None
                    if self.status['run_id'] and self.status['state'] not in ACTIVE:
                        write_json_atomic(self.control / 'runs' / self.status['run_id'] / 'outcome.json', self.status)

    def close(self):
        if self.worker and self.worker.is_alive():
            raise RuntimeError('cannot close active Runner')
        self.ownership.close()

    @staticmethod
    def _session_safety(executor, recovery):
        try:
            probe = getattr(executor, 'session_safety', None)
            return probe() if callable(probe) else ('unknown' if recovery else 'confirmed-closed')
        except Exception:
            return 'unknown'

    @staticmethod
    def _needs_recovery(executor):
        try:
            return executor is None or executor.recovery_required()
        except Exception:
            return True  # Unreadable ownership/diagnostics is not safe closure.


def validate_run_payload(payload):
    if payload.get('kind', 'hom') not in {'hom', 'standard'}:
        raise ValueError('unsupported execution kind')
    if payload.get('kind') == 'standard':
        tasks = payload.get('tasks')
        if not isinstance(tasks, list) or not tasks or len(tasks) > 10000:
            raise ValueError('standard batch requires a bounded task list')
        jobs = set()
        for task in tasks:
            if not isinstance(task, dict) or not isinstance(task.get('parameters'), dict):
                raise ValueError('invalid standard task')
            job = task.get('job')
            if not isinstance(job, str) or not job or job in jobs:
                raise ValueError('standard job names must be unique')
            jobs.add(job)
    if not isinstance(payload.get('resume', False), bool):
        raise ValueError('resume must be boolean')
    count = payload.get('worker_count', 1)
    if type(count) is not int or not 1 <= count <= 64:
        raise ValueError('invalid worker_count')
    for key in ('algorithm',):
        if not isinstance(payload.get(key, {}), dict):
            raise ValueError('invalid ' + key)
    from .scan_settings import validate_hom_settings
    validate_hom_settings(payload.get('algorithm', {}))
    if not isinstance(payload.get('postprocess', []), list):
        raise ValueError('invalid postprocess')


class LocalExecution:
    """Concrete execution boundary. Only the Runner creates the backend."""
    def __init__(self, project, stop_intent, run_id, update, *, payload=None):
        from .application_backend import CstApplicationBackend
        from .globalconfmanager import GlobalConfigManager
        from .logging_config import ApplicationLogSession
        from .run_overview import RunOverview
        from .run_overview import RunOverviewHandler
        self.project = Path(project)
        self.update = update
        self.stop = stop_intent
        settings = (payload or {}).get('algorithm', {})
        purpose = ('会话恢复' if payload is None else ('标准批次' if payload.get('kind') == 'standard'
                   else f"HOM-{settings.get('fmin', '?')}-{settings.get('endfreq', '?')}MHz"))
        self.overview = RunOverview(project, run_id or uuid4().hex, purpose,
                                   resume=bool((payload or {}).get('resume')), settings=settings)
        self.log = ApplicationLogSession(self.overview.directory / 'application.log')
        self.overview_handler = RunOverviewHandler(self.overview)
        self.log.logger.addHandler(self.overview_handler)
        self.update(log_directory=str(self.overview.directory))
        self.backend = CstApplicationBackend(
            global_config_manager=GlobalConfigManager(self.project / 'control/config/current.ini', logger=self.log.logger),
            stop_intent=stop_intent, application_logger=self.log.logger, execution_run_id=run_id)
        self.backend.select_project_directory(str(project))
        self.backend._run_overview = self.overview
        self.backend.alg.checkpoint_listener = lambda report, pending, coverage: self.update(
            coverage=coverage, mode_count=len(report.modes))
        self._last_lifecycle_observation = 0.
        self.backend.add_progress_listener(self._progress)

    def _progress(self, event):
        values = dict(last_progress=asdict(event))
        if time.monotonic() - self._last_lifecycle_observation >= 5:
            self._last_lifecycle_observation = time.monotonic()
            try:
                values['lifecycle'] = self.lifecycle_facts()
                values['session_safety'] = values['lifecycle']['session_safety']
            except Exception as exc:
                from .lifecycle_diagnostics import error_diagnostic
                values['session_safety'] = 'unknown'
                values['lifecycle'] = dict(schema_version=1, session_safety='unknown',
                    diagnostic=error_diagnostic(exc, 'lifecycle-probe'))
        self.update(**values)

    def run(self, payload):
        self.stop.check()
        if payload.get('kind') == 'standard':
            from .standard_batch import StandardBatchAlgorithm
            self.backend.alg = StandardBatchAlgorithm(payload['tasks'])
            self.backend.alg.status_listener = self.update
        self.overview.update(settings=payload.get('algorithm', {}), source_project=payload.get('source_project'),
                             resume=payload.get('resume', False))
        if payload.get('source_project'):
            self.backend.select_cst_file(payload['source_project'])
        installation = payload.get('installation')
        if installation:
            self.backend.select_cst_installation(installation['version'], installation['executable'])
        self.backend.update_algorithm_settings(payload.get('algorithm', {}))
        self.backend.update_postprocess_settings(payload.get('postprocess', []))
        self.backend.initialize_run(payload.get('resume', False), payload.get('worker_count', 1))
        self.stop.check()
        self.backend.prepare_run()
        # Backend owns cleanup even when stop arrived at the prepare/execute boundary.
        if not self.stop.is_set():
            self.update(state='RUNNING', phase='running')
        result = self.backend.execute_run()
        from .execution_contract import ArtifactRef
        from .result_reconciliation import file_hash
        import socket
        checkpoint = self.project / ('save/standard_batch_checkpoint.json' if payload.get('kind') == 'standard'
                                     else 'save/csv/hom_scan_checkpoint.json')
        if checkpoint.exists():
            self.update(artifacts=[ArtifactRef(self.backend.run_id + ':checkpoint', socket.gethostname(),
                str(checkpoint), file_hash(checkpoint)).to_mapping()])
        if getattr(result, 'failed', None):
            raise RuntimeError('HOM finished with unconfirmed intervals; resume to fill gaps')

    def request_stop(self):
        self.backend.request_stop()

    def recover(self):
        if self._preprocessor_recovery_required():
            raise RuntimeError('任务归属的预处理CST进程尚未确认退出，不能清除项目恢复状态')
        self.backend.recover_project_sessions()

    def recovery_required(self):
        if self.backend.is_recovery_required():
            return True
        return self._preprocessor_recovery_required()

    def session_safety(self):
        return self.lifecycle_facts()['session_safety']

    def lifecycle_facts(self):
        from .lifecycle_diagnostics import project_lifecycle
        facts = project_lifecycle(self.project)
        facts['preprocessor_recovery_required'] = self._preprocessor_recovery_required()
        if facts['preprocessor_recovery_required']:
            facts['session_safety'] = 'unknown'
            facts['recovery_required'] = True
        return facts

    def _preprocessor_recovery_required(self):
        # Preprocessing owns CST too, but is not a Managed session.
        import psutil
        for path in self.project.glob('temp/cst-preprocess-*/session-status.json'):
            report = read_json(path)
            if report.get('exit_confirmed'):
                continue
            for owned in report.get('owned', []):
                try:
                    process = psutil.Process(owned['pid'])
                    if abs(process.create_time() - owned['create_time']) < .01 and process.is_running():
                        return True
                except psutil.NoSuchProcess:
                    continue
                except (psutil.AccessDenied, OSError, ValueError, KeyError):
                    return True
        return False

    def close(self):
        try:
            self.overview.update(status=self.backend.state.name)
            self.backend.close_logging()
        finally:
            self.log.logger.removeHandler(self.overview_handler)
            self.overview_handler.close()
            self.log.close()


def serve(project, executor_factory=None):
    runner = Runner(project, executor_factory)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args):
            pass  # Never put authorization headers in HTTP logs.

        def handle_request(self):
            self.connection.settimeout(3)
            try:
                if self.headers.get('Origin') or not hmac.compare_digest(
                        self.headers.get('Authorization', ''), 'Bearer ' + runner.token):
                    self.send_error(403)
                    return
                runner.heartbeat(self.headers.get('X-Client-ID'))
                if self.path == '/status' and self.command == 'GET':
                    result = runner.snapshot()
                elif self.path.startswith('/events?') and self.command == 'GET':
                    from urllib.parse import parse_qs, urlsplit
                    query = parse_qs(urlsplit(self.path).query)
                    result = runner.events(json.loads(query.get('cursor', ['0'])[0]))
                elif self.path.startswith('/commands/') and self.command == 'GET':
                    result = runner.command_record(self.path.removeprefix('/commands/'))
                elif self.path == '/commands' and self.command == 'POST':
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 262144:
                        raise ValueError('request too large or empty')
                    data = self.rfile.read(length)
                    if len(data) != length:
                        raise ValueError('incomplete request')
                    result = runner.command(json.loads(data))
                else:
                    self.send_error(404)
                    return
                body = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
                self.send_response(200)
            except (ValueError, OSError, RuntimeError) as exc:
                body = json.dumps({'error': str(exc)}).encode()
                self.send_response(409)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = handle_request
        do_POST = handle_request

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.timeout = .25
    write_json_atomic(runner.control / 'runner.json', {
        'schema_version': 1, 'instance_id': runner.instance_id, 'pid': os.getpid(),
        'port': server.server_port, 'token': runner.token, 'project': str(runner.project)})
    try:
        while not runner.shutdown_requested.is_set():
            server.handle_request()
    finally:
        server.server_close()
        runner.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--fake', action='store_true', help='synthetic execution only; never launches CST')
    args = parser.parse_args()
    if args.fake:
        from .runner_fake import FakeExecution
        serve(args.project, FakeExecution)
    else:
        serve(args.project)


if __name__ == '__main__':
    main()
