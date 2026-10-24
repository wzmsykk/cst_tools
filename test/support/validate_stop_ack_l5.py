"""Real serial stop/ACK timing probes, with test-only scheduling gates."""
import argparse
from dataclasses import asdict
from pathlib import Path
import sys
import time
import json
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.acceptance_session import exclusive_probe, cst_processes
from csttool.configuration import write_json_atomic, read_json
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.runtime_protocol import (Task, atomic_publish, encode_task, decode_completion,
                                     validate_completion, Acknowledge, publish_ack_idempotently)
from csttool.result_reconciliation import file_hash, recover_completed_result, find_received_result
from csttool.project_session_recovery import recover_project_sessions, discover_managed_sessions
from test.managed_hom_ten_modes_fault_resume_integration_test import _config

CASES = ('before-parameters', 'after-rebuild', 'during-solver', 'after-solver',
         'completion-before-receive', 'received-before-ack', 'ack-accepted',
         'task-deleted', 'completion-deleted', 'ready-before-adopt', 'wrong-ack', 'truncated-ack')


class TimingWorker(ManagedCSTWorker):
    point = None

    def _build_macro(self):
        super()._build_macro()
        anchors = {
            'before-parameters': ('            CSTPMW_CheckStop "before-parameters"', False),
            'after-rebuild': ('            CSTPMW_CheckStop "after-rebuild"', False),
            'after-solver': ('            CSTPMW_CheckStop "after-solver"', False),
            'completion-before-receive': ('WaitForAck:', True),
            'ack-accepted': ('                    stage = "ack-cleanup"', True),
            'task-deleted': (f'                    Kill "{self.task_path}"', True),
            'completion-deleted': (f'                    Kill "{self.completion_path}"', True),
        }
        if self.point not in anchors:
            return
        anchor, after = anchors[self.point]
        source = self.macro_path.read_text(encoding='ascii')
        assert source.count(anchor) == 1
        ready = str(self.root / 'timing.entered')
        release = str(self.root / 'timing.release')
        gate = f'\n    CSTPMW_WriteMarker "{ready}", "{self.point}"\n    Do While Dir("{release}") = ""\n        Wait 0.1\n    Loop\n'
        source = source.replace(anchor, anchor + gate if after else gate + anchor)
        self.macro_path.write_text(source, encoding='ascii', newline='\n')
        self.batch_script_path.write_text(source, encoding='ascii', newline='\n')


def wait_until(worker, predicate, timeout=None):
    deadline = None if timeout is None else time.monotonic() + timeout
    while not predicate():
        if worker._process.poll() is not None:
            raise RuntimeError('owned CST exited before timing checkpoint')
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError('timing checkpoint was not reached')
        time.sleep(.01)


def read_current_completion(worker, task):
    if not worker.completion_path.exists():
        return None
    value = decode_completion(worker.completion_path.read_text(encoding='utf-8'))
    validate_completion(task, value)
    return value


def run_timing(executable, source, root, point):
    root.mkdir(parents=True)
    config = _config(root, '0', executable, source)
    pps = [dict(resultName='frequency', method='Frequency', params=dict(iModeNumber=1))]
    config['postProcess'] = pps
    fingerprint = file_hash(source) + ':frequency-v1'
    params = dict(nmodes=1, fmin=500, fmax=800)
    report = dict(point=point, source_sha256=file_hash(source), passed=False,
                  scheduling='test-only gate' if point not in {'during-solver', 'received-before-ack', 'ready-before-adopt'} else 'native observation')
    worker = None
    try:
        TimingWorker.point = point
        worker = TimingWorker('0', config)
        task = Task.create(worker.session_id, params)
        result_root = worker.result_root / task.task_id
        receipt_path = worker.root / 'received' / (task.task_id + '.json')
        write_json_atomic(worker.root / 'task-context.json', dict(schema_version=1,
            task_id=task.task_id, session_id=task.session_id, close_protocol='v2', job='timing',
            parameters=params, postprocess=pps, result_root=str(result_root),
            receipt_path=str(receipt_path), execution_fingerprint=fingerprint))
        atomic_publish(worker.task_path, encode_task(task))
        ack_cases = {'ack-accepted', 'task-deleted', 'completion-deleted', 'ready-before-adopt'}
        bad_acks = {'wrong-ack', 'truncated-ack'}
        if point in ack_cases or point == 'received-before-ack' or point in bad_acks:
            wait_until(worker, lambda: read_current_completion(worker, task) is not None)
            completion = read_current_completion(worker, task)
            assert completion.status.value == 'success'
            assert recover_completed_result(worker.root) == receipt_path
            if point in ack_cases:
                publish_ack_idempotently(worker.ack_path, Acknowledge(task.task_id, task.session_id))
            if point in bad_acks:
                from csttool.runtime_protocol import encode_ack, new_session_id
                invalid = encode_ack(Acknowledge(task.task_id, new_session_id())) if point == 'wrong-ack' else 'CST_ACK_V1\ntask_id\n'
                atomic_publish(worker.ack_path, invalid)
                wait_until(worker, lambda: 'ACK_BLOCKED' in worker.marker_path.read_text(), timeout=120)
                report['invalid_ack_sha256'] = file_hash(worker.ack_path)
        if point == 'during-solver':
            lifecycle = worker.observation_root / 'lifecycle.log'
            wait_until(worker, lambda: lifecycle.exists() and 'calling EigenmodeSolver.Start' in lifecycle.read_text())
            assert 'returned=' not in lifecycle.read_text(), 'solver finished before stop; overlap unproven'
            report['stop_during_native_start'] = True
        elif point == 'ready-before-adopt':
            wait_until(worker, lambda: worker.marker_path.read_text().strip() == 'ready:' + task.task_id)
        elif point != 'received-before-ack' and point not in bad_acks:
            wait_until(worker, lambda: (worker.root / 'timing.entered').exists(),
                       timeout=120 if point in {'before-parameters', 'after-rebuild'} else None)
        worker.request_stop()
        (worker.root / 'timing.release').write_text('release')
        worker.stop()
        report['close'] = asdict(worker._shutdown_assessment())
        assert report['close']['standard_closed'], report
        before = discover_managed_sessions(root)
        report['before_recovery'] = [asdict(r.closure) for r in before]
        recover_project_sessions(root, timeout_per_session=120)
        report['after_recovery'] = [asdict(r.closure) for r in discover_managed_sessions(root)]
        assert not any(r.needs_recovery for r in discover_managed_sessions(root))
        candidate = find_received_result([root], 'timing', params, fingerprint)
        if point in ack_cases or point in {'completion-before-receive', 'received-before-ack'} or point in bad_acks:
            assert candidate is not None, 'completed solve was not available for reconciliation'
            receipt_path, receipt = candidate
            report['frequency'] = receipt['postprocess'][0]['value']
            assert 500 <= float(report['frequency']) <= 800
            # Use the real Manager idempotent adoption method without creating a pool.
            from csttool.cstmanager import CSTManager
            manager = CSTManager.__new__(CSTManager)
            manager._received_paths = {task.task_id: receipt_path}
            from csttool.run_store import RunStore
            manager.run_store = RunStore(root, root / 'adoption')
            manager.run_store.event(task.task_id, 'reconciled')
            manager.adopt_result(task.task_id)
            saved = receipt_path.read_bytes()
            manager.adopt_result(task.task_id)
            assert receipt_path.read_bytes() == saved
            assert find_received_result([root], 'timing', params, fingerprint) is None
            report['adopted_once'] = True
            if point in bad_acks:
                assert file_hash(worker.ack_path) == report['invalid_ack_sha256']
                report['invalid_ack_preserved'] = True
        else:
            assert candidate is None
            report['cancelled_not_adopted'] = True
        report['solver_calls'] = (worker.observation_root / 'lifecycle.log').read_text().count('calling EigenmodeSolver.Start')
        assert report['solver_calls'] <= 1
        report['passed'] = True
    except BaseException as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if worker is not None:
            (worker.root / 'timing.release').write_text('release')
            if worker._process.poll() is None:
                try:
                    worker.stop()
                except Exception as exc:
                    report['cleanup_error'] = str(exc)
        report['source_unchanged'] = file_hash(source) == report['source_sha256']
        report['cst_processes_after'] = cst_processes()
        write_json_atomic(root / 'report.json', report)
        print(f'REPORT={root / "report.json"}', flush=True)


def verify_timing_reports(roots, output):
    """Recheck saved real evidence before large files are cleaned."""
    reports = {}
    for root in roots:
        for path in root.rglob('report.json'):
            report = read_json(path)
            if not report.get('passed'):
                continue
            point = report['point']
            assert point not in reports, 'select one passed report per timing point'
            assert report['source_unchanged'] and not report['cst_processes_after']
            assert report['close']['standard_closed']
            assert all(not item['needs_recovery'] for item in report['after_recovery'])
            assert report['solver_calls'] == (0 if point in {'before-parameters', 'after-rebuild'} else 1)
            session = next((path.parent / 'temp/worker_0').iterdir())
            context = read_json(session / 'task-context.json')
            from csttool.close_receipt import read_close_receipt
            receipt = read_close_receipt(session, context['session_id'], expected_task_id=context['task_id'])
            entry = dict(report=str(path), close_outcome=receipt.close_outcome,
                         task_outcome=receipt.task_outcome, solver_calls=report['solver_calls'])
            if point in {'during-solver', 'after-solver'}:
                snapshot = Path(context['result_root']) / 'interrupted-project.cst'
                assert snapshot.is_file() and snapshot.stat().st_size > 0
                fields = {}
                for name in ('e1.m3t', 'h1.m3t'):
                    active = session / 'worker-input/Result' / name
                    saved = snapshot.with_suffix('') / 'Result' / name
                    assert active.is_file() and saved.is_file()
                    assert active.stat().st_size > 0 and file_hash(active) == file_hash(saved)
                    fields[name] = file_hash(saved)
                entry['preserved_fields'] = fields
            if report.get('adopted_once'):
                events = [json.loads(line) for line in (path.parent / 'adoption/events.jsonl').read_text().splitlines()]
                assert sum(event['event'] == 'algorithm_adopted' for event in events) == 1
                entry['algorithm_adoptions'] = 1
            reports[point] = entry
    assert set(reports) == set(CASES), set(CASES) - set(reports)
    write_json_atomic(output, dict(passed=True, points=reports))
    return reports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--verify-root', action='append', type=Path)
    parser.add_argument('--verification-output', type=Path)
    parser.add_argument('--point', choices=CASES + ('all', 'ack-tail', 'bad-acks'), default='all')
    args = parser.parse_args()
    if args.verify_root:
        if not args.verification_output:
            parser.error('--verification-output is required')
        verify_timing_reports(args.verify_root, args.verification_output)
        return
    if args.cst_exe is None or args.source is None:
        parser.error('--cst-exe and --source are required for real execution')
    with exclusive_probe(ROOT):
        root = ROOT / 'artifacts' / ('stop-ack-l5-' + uuid4().hex[:8])
        points = {'all': CASES, 'ack-tail': CASES[7:10], 'bad-acks': CASES[10:]}.get(args.point, (args.point,))
        for point in points:
            assert not cst_processes(), 'previous copy has not exited'
            print('POINT_BEGIN=' + point, flush=True)
            run_timing(args.cst_exe, args.source.resolve(), root / point, point)


if __name__ == '__main__':
    main()
