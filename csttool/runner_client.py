"""Local Runner discovery and authenticated JSON transport, with no Qt dependency."""
from __future__ import annotations
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
from uuid import uuid4
from .configuration import read_json, write_json_atomic
from .runner_ownership import RunnerOwnership
from .execution_contract import RunnerSnapshot


class RunnerRejected(RuntimeError):
    """The peer replied with an explicit rejection; transport is not lost."""
    def __init__(self, message, path='/commands', code=None):
        self.path = path
        self.code = code
        super().__init__(message)


class RunnerStartupError(RuntimeError):
    """A bounded startup attempt failed; never permission to replace a Runner."""
    def __init__(self,message,diagnostics):
        self.diagnostics=diagnostics
        super().__init__(message)


class RunnerStartupTimeout(TimeoutError):
    """Readiness is unconfirmed, not evidence that the background process died."""
    def __init__(self,message,diagnostics):
        self.diagnostics=diagnostics
        super().__init__(message)


class _ReadinessBudgetExhausted(TimeoutError):
    pass


class RunnerClient:
    def __init__(self, project, client_id=None):
        self.project = Path(project).resolve()
        self.client_id = client_id or uuid4().hex
        self.endpoint = None
        self.launch_attempted = False
        self.connected_once = False
        self.last_startup = None
        self.startup_process = None
        self._startup_started = None
        self._startup_report_owned = False
        self.opener = build_opener(ProxyHandler({}))

    def request(self, path, value=None, *, timeout=2):
        endpoint = self.endpoint
        if endpoint is None:
            endpoint = read_json(self.project / 'control/runner.json')
            self.endpoint = endpoint
        if not isinstance(endpoint,dict):
            raise ValueError('Runner endpoint must be a JSON object')
        if (type(endpoint.get('port')) is not int or not 1<=endpoint['port']<=65535
                or not isinstance(endpoint.get('token'),str) or not endpoint['token']
                or not isinstance(endpoint.get('project'),str) or not endpoint['project']
                or not isinstance(endpoint.get('instance_id'),str) or not endpoint['instance_id']):
            raise ValueError('Runner endpoint identity/port is invalid')
        if Path(endpoint.get('project', '')).resolve() != self.project:
            raise ValueError('Runner project identity mismatch')
        request = Request(f"http://127.0.0.1:{int(endpoint['port'])}{path}",
            data=json.dumps(value, allow_nan=False).encode() if value is not None else None,
            headers={'Authorization': 'Bearer ' + endpoint['token'],
                     'Content-Type': 'application/json', 'X-Client-ID': self.client_id})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                result = json.load(response)
        except HTTPError as exc:
            try:error=json.loads(exc.read(65536))
            except ValueError:error={}
            # Only authenticated Runner business rejections use JSON/409.
            # HTML/403 or an unrelated listener is still an unverified peer.
            if exc.code!=409 or not isinstance(error,dict) or not isinstance(error.get('error'),str):raise
            raise RunnerRejected(error.get('error', f'HTTP {exc.code}'), path, error.get('code')) from exc
        if path == '/status' and result['instance_id'] != endpoint['instance_id']:
            raise ValueError('Runner instance changed')
        return result

    def status(self, *, timeout=2) -> RunnerSnapshot:
        return self.request('/status',timeout=timeout)

    def events(self, cursor=0):
        from urllib.parse import urlencode
        return self.request('/events?' + urlencode({'cursor': json.dumps(cursor)}))

    def command_record(self, request_id):
        return self.request('/commands/' + request_id)

    def simulation_results(self,run_id,result_revision=None):
        from urllib.parse import urlencode
        query={'run_id':run_id}
        if result_revision is not None:query['result_revision']=result_revision
        return self.request('/simulation-results?'+urlencode(query))

    def definition_result(self,run_id):
        from urllib.parse import urlencode
        return self.request('/definition-result?'+urlencode({'run_id':run_id}))

    def inspect_model(self,document_id,document_revision):
        from urllib.parse import urlencode
        return self.request('/model?'+urlencode(dict(document_id=document_id,document_revision=document_revision)))

    def installations(self):return self.request('/installations')

    @property
    def stop_request_path(self):
        return self.project / 'control/pending-ui-stop.json'

    def save_stop_request(self, request_id):
        write_json_atomic(self.stop_request_path, dict(schema_version=1,
            start_request_id=request_id, client_id=self.client_id, project=str(self.project)))

    def pending_stop_request(self):
        if self.stop_request_path.exists():
            return read_json(self.stop_request_path)['start_request_id']
        return None

    def clear_stop_request(self, request_id):
        if self.pending_stop_request() == request_id:
            self.stop_request_path.unlink(missing_ok=True)

    def command(self, operation, payload=None, *, run_id=None, request_id=None):
        return self.request('/commands', {'schema_version': 1,
            'request_id': request_id or uuid4().hex, 'client_id': self.client_id,
            'operation': operation, 'run_id': run_id, 'payload': payload or {}})

    def _startup_record(self,record):
        """Write only milestones, never every HTTP poll or endpoint credentials."""
        self.last_startup=record
        try:
            write_json_atomic(self.project/'control/bootstrap.json',record)
            event=dict(event='RUNNER_STARTUP_CLIENT',client_pid=os.getpid(),**record)
            with (self.project/'control/bootstrap.log').open('ab') as stream:
                stream.write((json.dumps(event,ensure_ascii=True,allow_nan=False)+'\n').encode('utf-8'))
        except OSError as error:record['diagnostic_write_error']=type(error).__name__+': '+str(error)

    def connect(self, *, launch=True, timeout=15):
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0:
            raise ValueError('Runner readiness timeout must be finite and positive')
        started=time.monotonic();deadline=started+timeout;probe_count=0
        def probe():
            nonlocal probe_count
            remaining=deadline-time.monotonic()
            if remaining<=0:raise _ReadinessBudgetExhausted('readiness budget exhausted')
            probe_count+=1
            self.endpoint=None
            return self.status(timeout=min(2,remaining))
        try:
            result = probe()
            self.connected_once = True
            if self.last_startup and self.last_startup.get('startup_state')!='ready':
                recovered=dict(self.last_startup,startup_state='ready',phase='connected-existing',
                    ready_instance_id=result['instance_id'],runtime=result.get('runtime'),
                    reconnected_at=datetime.now(timezone.utc).isoformat(),
                    previous_startup_state=self.last_startup['startup_state'])
                if self._startup_started is not None:recovered['elapsed_seconds']=round(time.monotonic()-self._startup_started,6)
                if self._startup_report_owned:self._startup_record(recovered)
                else:self.last_startup=recovered
            return result
        except (OSError, ValueError, RuntimeError) as error:
            if not launch:
                raise
            initial_error=error
        if self.launch_attempted or self.connected_once:
            raise RuntimeError('Runner unavailable; inspect control/bootstrap.log and reconnect explicitly; no automatic restart')
        record=dict(schema_version=1,attempt_id=uuid4().hex,project=str(self.project),
            started_at=datetime.now(timezone.utc).isoformat(),timeout_seconds=timeout,
            startup_state='waiting',source='csttool.runner_client.RunnerClient.connect',
            launcher_pid=None,launcher_exit_code=None,probe_count=probe_count,
            last_probe_error=dict(type=type(initial_error).__name__,message=str(initial_error)[:500]))
        record['initial_probe_error']=dict(record['last_probe_error'])
        self._startup_started=started
        process=None;bootstrap_lease=None;write_record=False
        def finish(state):
            record.update(startup_state=state,elapsed_seconds=round(time.monotonic()-started,6),probe_count=probe_count)
            if isinstance(self.endpoint,dict):
                record['last_endpoint']={k:self.endpoint.get(k) for k in ('pid','port','instance_id')}
            if process is not None:record['launcher_exit_code']=process.poll()
            if write_record:self._startup_record(record)
            else:self.last_startup=record
        def fail(state,cause=None):
            finish(state)
            if cause:record['error']=dict(type=type(cause).__name__,message=str(cause)[:500]);self._startup_record(record)
            path=self.project/'control/bootstrap.json'
            text=(f'Runner启动未确认 | phase={record.get("phase")} state={state} '
                  f'elapsed={record["elapsed_seconds"]:.2f}s launcher_pid={record["launcher_pid"]} '
                  f'exit_code={record["launcher_exit_code"]}；'
                  f'仅重新连接，不重复启动或提交任务；diagnostics={path}；log={self.project/"control/bootstrap.log"}')
            cls=RunnerStartupTimeout if state=='timeout' else RunnerStartupError
            raise cls(text,record) from cause
        try:
            # Serialize cooperating cold starts, separately from actual Runner ownership.
            try:bootstrap_lease=RunnerOwnership(self.project/'control/bootstrap.lock').acquire()
            except RuntimeError:record['phase']='waiting-other-startup'
            except OSError as error:
                record['phase']='bootstrap-ownership';write_record=True;self._startup_report_owned=True;fail('ownership-check-failed',error)
            else:
                write_record=True;self._startup_report_owned=True
                try:
                    result=probe();self.connected_once=True
                    record.update(phase='existing-ready',ready_instance_id=result['instance_id'],runtime=result.get('runtime'))
                    # A just-finished starter owns the on-disk attempt record.
                    write_record=False;self._startup_report_owned=False;finish('ready');return result
                except (OSError,ValueError,RuntimeError) as error:
                    record['probe_count']=probe_count
                    if not isinstance(error,_ReadinessBudgetExhausted):
                        record['last_probe_error']=dict(type=type(error).__name__,message=str(error)[:500])
                try:lease=RunnerOwnership(self.project/'control/runner.lock').acquire()
                except RuntimeError:record['phase']='waiting-existing-owner'
                except OSError as error:
                    record['phase']='runner-ownership';fail('ownership-check-failed',error)
                else:
                    lease.close()
                    if time.monotonic()>=deadline:record['phase']='before-spawn';fail('timeout')
                    record['phase']='spawn';self.launch_attempted=True;self._startup_record(record)
                    options={'close_fds':True,'stdin':subprocess.DEVNULL}
                    if os.name=='nt':options['creationflags']=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP
                    else:options['start_new_session']=True
                    try:
                        with (self.project/'control/bootstrap.log').open('ab') as bootstrap:
                            options.update(stdout=bootstrap,stderr=subprocess.STDOUT)
                            process=subprocess.Popen([sys.executable,'-m','csttool.runner','--project',str(self.project)],
                                cwd=Path(__file__).resolve().parents[1],**options)
                    except OSError as error:fail('spawn-failed',error)
                    self.startup_process=process
                    record.update(phase='waiting-http',launcher_pid=process.pid)
                self._startup_record(record)
            while time.monotonic()<deadline:
                try:
                    result=probe();self.connected_once=True
                    record['ready_instance_id']=result['instance_id'];record['runtime']=result.get('runtime')
                    finish('ready');return result
                except (OSError,ValueError,RuntimeError) as error:
                    record['probe_count']=probe_count
                    if not isinstance(error,_ReadinessBudgetExhausted):
                        record['last_probe_error']=dict(type=type(error).__name__,message=str(error)[:500])
                if process is not None and process.poll() is not None:fail('launcher-exited')
                time.sleep(max(0,min(.1,deadline-time.monotonic())))
            fail('timeout')
        finally:
            if bootstrap_lease:bootstrap_lease.close()

    def shutdown_and_wait(self, *, run_id=None, timeout=10):
        """Standard shutdown; confirm OS ownership release, never kill or relaunch."""
        try:
            self.connect(launch=False)
        except OSError:
            # No automatic restart. Lock absence alone does not prove CST safety.
            lease = RunnerOwnership(self.project / 'control/runner.lock').acquire()
            try:
                from .runner import verify_shutdown_safety
                facts = verify_shutdown_safety(self.project)
            finally:
                lease.close()
            return {'runner_stopped': True, 'already_offline': True,
                    'session_safety': facts['session_safety']}
        self.command('claim')
        try:
            self.command('shutdown', run_id=run_id)
        except (OSError, ValueError):
            # A lost response is not proof of failure or success; check ownership.
            pass
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                lease = RunnerOwnership(self.project / 'control/runner.lock').acquire()
            except RuntimeError:
                time.sleep(.1)
            else:
                lease.close()
                return {'runner_stopped': True}
        raise TimeoutError('Runner退出尚未确认；未强杀进程，请重新连接检查后台状态')


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Inspect/control an existing local Runner')
    parser.add_argument('--project', required=True)
    parser.add_argument('operation', choices=['status', 'start', 'stop', 'recover', 'shutdown'])
    parser.add_argument('--config', help='JSON run payload for start')
    parser.add_argument('--client-id', help='Stable UI-control identity, not an authentication token')
    args = parser.parse_args()
    client = RunnerClient(args.project, args.client_id)
    if args.operation == 'shutdown':
        result = client.shutdown_and_wait()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    status = client.connect(launch=False)
    if args.operation == 'status':
        result = status
    else:
        client.command('claim')
        payload = read_json(args.config) if args.config else {}
        result = client.command(args.operation, payload, run_id=status['run_id'])
        if args.operation != 'shutdown':
            client.command('release')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
