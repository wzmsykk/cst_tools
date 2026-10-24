"""Local Runner discovery and authenticated JSON transport, with no Qt dependency."""
from __future__ import annotations
import json
import os
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


class RunnerClient:
    def __init__(self, project, client_id=None):
        self.project = Path(project).resolve()
        self.client_id = client_id or uuid4().hex
        self.endpoint = None
        self.launch_attempted = False
        self.connected_once = False
        self.opener = build_opener(ProxyHandler({}))

    def request(self, path, value=None):
        endpoint = self.endpoint
        if endpoint is None:
            endpoint = read_json(self.project / 'control/runner.json')
            self.endpoint = endpoint
        if Path(endpoint.get('project', '')).resolve() != self.project:
            raise ValueError('Runner project identity mismatch')
        request = Request(f"http://127.0.0.1:{int(endpoint['port'])}{path}",
            data=json.dumps(value, allow_nan=False).encode() if value is not None else None,
            headers={'Authorization': 'Bearer ' + endpoint['token'],
                     'Content-Type': 'application/json', 'X-Client-ID': self.client_id})
        try:
            with self.opener.open(request, timeout=2) as response:
                result = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(json.loads(exc.read()).get('error', f'HTTP {exc.code}')) from exc
        if path == '/status' and result['instance_id'] != endpoint['instance_id']:
            raise ValueError('Runner instance changed')
        return result

    def status(self) -> RunnerSnapshot:
        return self.request('/status')

    def events(self, cursor=0):
        from urllib.parse import urlencode
        return self.request('/events?' + urlencode({'cursor': json.dumps(cursor)}))

    def command_record(self, request_id):
        return self.request('/commands/' + request_id)

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

    def connect(self, *, launch=True, timeout=15):
        try:
            self.endpoint = None
            result = self.status()
            self.connected_once = True
            return result
        except (OSError, ValueError, RuntimeError):
            if not launch:
                raise
        if self.launch_attempted or self.connected_once:
            raise RuntimeError('Runner unavailable; inspect control/bootstrap.log and reconnect explicitly; no automatic restart')
        # Probe OS ownership; a live/unreachable Runner is never replaced.
        lease = RunnerOwnership(self.project / 'control/runner.lock').acquire()
        lease.close()
        self.launch_attempted = True
        options = {'close_fds': True, 'stdin': subprocess.DEVNULL,
                   'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
        if os.name == 'nt':
            options['creationflags'] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options['start_new_session'] = True
        with (self.project / 'control/bootstrap.log').open('ab') as bootstrap:
            options.update(stdout=bootstrap, stderr=subprocess.STDOUT)
            subprocess.Popen([sys.executable, '-m', 'csttool.runner', '--project', str(self.project)],
                             cwd=Path(__file__).resolve().parents[1], **options)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                self.endpoint = None
                result = self.status()
                self.connected_once = True
                return result
            except (OSError, ValueError, RuntimeError):
                time.sleep(.1)
        raise TimeoutError('Runner did not become ready; do not submit a second run')

    def shutdown_and_wait(self, *, run_id=None, timeout=10):
        """Standard shutdown; confirm OS ownership release, never kill or relaunch."""
        self.connect(launch=False)
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
