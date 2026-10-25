"""Nonblocking GUI controller for the independent local Runner."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from datetime import datetime
import logging
from uuid import uuid4
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from csttool.cst_progress import CstProgressEvent
from GUI.run_controller import RunState


class RunnerController(QObject):
    state_changed = pyqtSignal(object)
    stage_changed = pyqtSignal(str)
    progress_changed = pyqtSignal(int, int)
    error = pyqtSignal(str)
    settled = pyqtSignal()
    cst_progress = pyqtSignal(object)
    connection_changed = pyqtSignal(str)
    snapshot_changed = pyqtSignal(object)

    def __init__(self, service):
        super().__init__()
        self.service = service
        self.backend = service.backend
        self.state = RunState.IDLE
        self.inputs_ready = False
        self.recovery_count = 0
        self.run_id = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='runner-client')
        self.future = None
        self.pending = False
        self.unknown = False
        self.read_only = False
        self.cursor = 0
        self.instance = None
        self.observed_run = None
        self.last_error = None
        self.queued_action = None
        self.pending_operation = None
        self.stop_after_start = False
        self.start_request_id = None
        self.context_client = self.backend.client
        self.generation = 0
        self.future_generation = 0
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.closed = False
        self.runner_stopped = False
        self.detaching = False
        self._restore_stop_request(self.context_client)

    def _restore_stop_request(self, client):
        if client:
            request_id = client.pending_stop_request()
            if request_id:
                self.start_request_id = request_id
                self.stop_after_start = True

    @property
    def has_active_work(self):
        return self.stop_after_start or self.pending or self.unknown or self.state in {RunState.RUNNING, RunState.STOPPING, RunState.RECOVERING}

    def set_inputs_ready(self, ready):
        self.inputs_ready = bool(ready)
        if not self.has_active_work and self.state not in {RunState.RECOVERY_REQUIRED, RunState.FAILED}:
            self.state = RunState.READY if ready else RunState.IDLE
            self.state_changed.emit(self.state)

    def _observe(self, client, instance=None, observed_run=None, cursor=0):
        status = client.connect(launch=instance is None)
        if (instance != status['instance_id'] or observed_run != status['run_id']) and not (
                isinstance(cursor, dict) and cursor.get('source')):
            cursor = 0
        events = client.events(cursor)
        return status, events

    def _sync_context(self):
        client = self.backend.client
        if client is self.context_client:
            return
        if self.stop_after_start:
            # Do not abandon a stop intent in order to attach another project.
            self.error.emit('停止意图尚未确认，不能切换项目连接')
            self.backend.client = self.context_client
            self.backend.project = str(self.context_client.project)
            return
        old = self.context_client
        self.context_client = client
        self.runner_stopped = False
        self.generation += 1
        self.instance = self.run_id = self.observed_run = self.start_request_id = None
        self.cursor = 0
        self.pending = self.unknown = self.read_only = False
        self.queued_action = self.pending_operation = self.last_error = None
        self.state = RunState.IDLE
        self.backend.log_directory = None
        self.backend.artifacts = []
        self._restore_stop_request(client)
        if old:
            def release():
                try:
                    old.command('release')
                except Exception:
                    pass  # Lease expires; never release the new project's owner.
            self.pool.submit(release)

    def poll(self):
        if self.closed:
            return
        if self.detaching:
            # Drain already-running transport work without observing or submitting commands.
            if self.future is None or self.future.done():
                if self.future is not None:
                    try:
                        self.future.result()
                    except Exception as exc:
                        self.backend.logger.warning('界面断开请求收尾失败，控制权将按租约释放: %s', exc)
                self.future = None
                self.closed = True
                self.timer.stop()
                self.settled.emit()
            return
        self._sync_context()
        if self.future:
            if not self.future.done():
                return
            future, self.future = self.future, None
            if self.future_generation != self.generation:
                # Consume neither stale successes nor stale exceptions (including A→B→A).
                self.poll()
                return
            self.pending = self.queued_action is not None
            finished_operation = self.pending_operation if self.queued_action is None else None
            if finished_operation:
                self.pending_operation = None
            try:
                status, events = future.result()
                if status.get('runner_stopped'):
                    self.backend.logger.info('后台服务已正常退出，已确认项目Runner所有权释放 | project=%s', self.backend.project)
                    self.runner_stopped = True
                    self.unknown = False
                    self.backend.runner_status = dict(getattr(self.backend, 'runner_status', {}),
                                                      state='OFFLINE')
                    self.state = RunState.IDLE
                    self.state_changed.emit(self.state)
                    self.connection_changed.emit('后台 Runner 已退出；点击“连接/启动”可重新启动，不自动续算')
                    self.snapshot_changed.emit(self.backend.runner_status)
                    self.settled.emit()
                    return
                if status['project'] != self.backend.project:
                    return
                self.unknown = False
                self.instance = status['instance_id']
                self.run_id = status['run_id']
                self.observed_run = self.run_id
                self.backend.log_directory = status.get('log_directory')
                self.backend.artifacts = status.get('artifacts', [])
                self.backend.runner_status = dict(status)
                self.cursor = events['cursor']
                mapping = {'PREPARING': RunState.RUNNING, 'RUNNING': RunState.RUNNING,
                           'STOPPING': RunState.STOPPING, 'RECOVERING': RunState.RECOVERING,
                           'RECOVERY_REQUIRED': RunState.RECOVERY_REQUIRED, 'FAILED': RunState.FAILED}
                previous_state = self.state
                self.state = mapping.get(status['state'], RunState.READY if self.inputs_ready else RunState.IDLE)
                if status.get('execution_active') and status['state'] not in {
                        'PREPARING', 'RUNNING', 'STOPPING', 'RECOVERING'}:
                    self.state = RunState.RECOVERING if previous_state is RunState.RECOVERING else RunState.STOPPING
                self.recovery_count = int(self.state is RunState.RECOVERY_REQUIRED)
                if self.state is not previous_state:
                    self.state_changed.emit(self.state)
                self.stage_changed.emit(status.get('phase', ''))
                owner = status.get('owner_client')
                self.read_only = owner not in (None, getattr(self.backend.client, 'client_id', None))
                self.connection_changed.emit('已连接后台 Runner' if not self.read_only
                    else ('控制权租约已过期，可点击“申请控制权”' if not status.get('control_lease_valid', True)
                          else '已连接（其他窗口持有控制权，仅查看）'))
                self.snapshot_changed.emit(status)
                from GUI.lifecycle_display import runner_error_text
                error = runner_error_text(status)
                if error and error != self.last_error:
                    self.error.emit(error)
                self.last_error = error
                if finished_operation == 'cancel_start':
                    self.backend.client.clear_stop_request(self.start_request_id)
                    self.stop_after_start = False  # Runner durably owns the intent now.
                if self.stop_after_start and not self.pending and self.state not in {
                        RunState.RECOVERY_REQUIRED, RunState.RECOVERING}:
                    self._command('cancel_start', {'start_request_id': self.start_request_id})
                progress = status.get('last_progress')
                if progress:
                    names = {field.name for field in fields(CstProgressEvent)}
                    self.cst_progress.emit(CstProgressEvent(**{k:v for k,v in progress.items() if k in names}))
                for event in events['events']:
                    timestamp = {}
                    if event.get('timestamp'):
                        try:
                            timestamp['created'] = datetime.fromisoformat(event['timestamp']).timestamp()
                        except (ValueError, TypeError):
                            pass
                    record = logging.makeLogRecord({'name': self.backend.logger.name,
                        **timestamp,
                        'levelno': event.get('levelno', logging._nameToLevel.get(event.get('level', 'INFO'), 20)),
                        'levelname': event.get('level', 'INFO'), 'msg': event.get('message', ''),
                        'pathname': event.get('source', {}).get('file', ''),
                        'lineno': event.get('source', {}).get('line', 0),
                        'funcName': event.get('source', {}).get('function', ''),
                        'event': event.get('event'), 'phase': event.get('phase'),
                        'record_id': event.get('record_id'),
                        'exc_text': (event.get('error') or {}).get('traceback', ''),
                        **event.get('context', {})})
                    self.backend.logger.handle(record)
                if not self.has_active_work:
                    self.settled.emit()
            except Exception as exc:
                self.unknown = True
                self.connection_changed.emit('后台状态未知，正在重连；未确认任务停止')
                if str(exc) != self.last_error:
                    self.error.emit(str(exc))
                    self.last_error = str(exc)
        client = self.backend.client
        if client and not self.future and not self.runner_stopped:
            if self.queued_action is not None:
                action, self.queued_action = self.queued_action, None
                self.future = self.pool.submit(action)
            else:
                self.future = self.pool.submit(self._observe, client, self.instance, self.observed_run, self.cursor)
            self.future_generation = self.generation

    def _command(self, op, payload=None):
        self._sync_context()
        client = self.backend.client
        if self.closed or self.detaching or client is None or self.runner_stopped or self.unknown or self.pending or (self.read_only and op != 'claim'):
            return False
        run_id = self.run_id
        request_id = uuid4().hex
        if op == 'start':
            self.start_request_id = request_id
        instance, observed_run, cursor = self.instance, self.observed_run, self.cursor
        def action():
            client.connect()
            if op != 'claim':
                client.command('claim')
            client.command(op, payload, run_id=run_id, request_id=request_id)
            return self._observe(client, instance, observed_run, cursor)
        self.queued_action = action
        self.pending = True
        self.pending_operation = op
        self.poll()
        return True

    def start(self, resume=False, worker_count=1):
        if self.has_active_work or not self.inputs_ready:
            return False
        return self._command('start', self.backend.run_payload(bool(resume), worker_count))

    def request_stop(self):
        if self.start_request_id and ((self.pending and self.pending_operation == 'start')
                or self.unknown or self.state is RunState.RUNNING):
            try:
                self.backend.client.save_stop_request(self.start_request_id)
            except OSError as exc:
                self.error.emit(f'停止意图保存失败，尚未确认停止: {exc}')
                return False
            self.stop_after_start = True
            self.poll()
            return True
        return self._command('stop')

    def request_control(self):
        return self._command('claim')

    def request_shutdown(self):
        if (self.has_active_work or self.read_only or self.runner_stopped
                or self.state is RunState.RECOVERY_REQUIRED or not self.backend.client):
            return False
        client, run_id = self.backend.client, self.run_id
        self.queued_action = lambda: (client.shutdown_and_wait(run_id=run_id), {'cursor': self.cursor, 'events': []})
        self.pending = True
        self.pending_operation = 'shutdown'
        self.backend.logger.info('请求后台服务正常退出 | project=%s instance=%s run_id=%s',
                                 self.backend.project, self.instance, run_id)
        self.connection_changed.emit('正在请求 Runner 正常退出并等待所有权释放…')
        self.poll()
        return True

    def connect_runner(self):
        if not self.backend.project or self.pending or (self.has_active_work and not self.unknown):
            return False
        # Explicit action only: a successful shutdown must never trigger auto-launch.
        self.backend.select_project_directory(self.backend.project)
        self.poll()
        return True

    def request_recovery(self):
        return self._command('recover')

    def inspect_recovery_state(self):
        self.poll()
        return self.recovery_count

    def mark_recovery_required(self, count=0):
        self.state = RunState.RECOVERY_REQUIRED
        self.state_changed.emit(self.state)

    def detach(self):
        if self.closed or self.detaching:
            return
        self.detaching = True
        self.queued_action = None
        if self.future is not None and self.future.cancel():
            self.future = None
        client = self.backend.client
        # Release the current lease after transport finishes. Never execute queued starts.
        if client and not self.runner_stopped:
            def release():
                try:
                    client.command('release')
                except Exception as exc:
                    self.backend.logger.warning('界面控制权释放未确认，将等待租约到期: %s', exc)
            self.future = self.pool.submit(release)
        self.pool.shutdown(wait=False, cancel_futures=False)
        # Keep Qt alive until the serial transport and release have returned.
        self.poll()
