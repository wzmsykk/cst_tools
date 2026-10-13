"""Explicit real-CST comparison; all inputs copy only .cst, never companions."""
import argparse
import logging
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from csttool.configuration import read_json, write_json_atomic
from csttool.hom_project_profile import HOM_PROFILE_V1
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.result_reconciliation import file_hash
from test.managed_hom_ten_modes_fault_resume_integration_test import _config


def run_case(directory, executable, source, parameters, prime=None, all_modes=False):
    started = time.monotonic()
    worker = None
    report = {'source': str(source), 'source_sha256': file_hash(source),
              'parameters': parameters, 'prime_parameters': prime, 'result': None}
    try:
        config = _config(directory, '0', executable, source)
        if all_modes:
            config['postProcess'] = [
                {**item, 'method': item['method'] + '_All',
                 'params': {key: value for key, value in item['params'].items()
                            if key != 'iModeNumber'}}
                for item in config['postProcess']
            ]
        report['postprocess'] = config['postProcess']
        worker = ManagedCSTWorker('0', config)
        report['session'] = worker.session_id
        report['workspace'] = str(worker.root)
        if prime is not None:
            report['prime_result'] = dict(worker.run_task('prime_previous_window', params=prime))
            if report['prime_result']['TaskStatus'] != 'Success':
                report['comparison_valid'] = False
                return report
        report['result'] = dict(worker.run_task('controlled_failed_window', params=parameters))
        report['comparison_valid'] = True
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        report['comparison_valid'] = False
    finally:
        if worker is not None:
            try:
                report['stop_returned'] = worker.stop()
            except Exception as exc:
                report['shutdown_error'] = f'{type(exc).__name__}: {exc}'
            report['stop_ack'] = worker.protocol.read_stop_ack(worker.session_id) is not None
            report['exit_code'] = worker._process.poll()
            report['process_alive'] = report['exit_code'] is None
            for name in ('output.txt', 'progress.log', 'Model.log'):
                path = worker.project_path.with_suffix('') / 'Result' / name
                if path.exists():
                    report[name] = str(path)
        report['elapsed_seconds'] = time.monotonic() - started
        report['source_unchanged'] = report['source_sha256'] == file_hash(source)
        write_json_atomic(directory / 'comparison.json', report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--nmodes', type=int, default=1)
    parser.add_argument('--all-modes', action='store_true')
    parser.add_argument('--window-widths', type=float, nargs='+',
                        help='Only vary fmax from the same fmin; stop at first successful solve.')
    args = parser.parse_args()
    if args.nmodes < 1:
        parser.error('--nmodes must be positive')
    evidence = Path(args.evidence).resolve()
    failed = [read_json(p) for p in (evidence / 'temp' / 'worker_1').glob('*/received/*.json')]
    assert len(failed) == 1 and failed[0]['status'] == 'Failure'
    parameters = failed[0]['parameters']
    previous = [read_json(p) for p in (evidence / 'temp' / 'worker_0').glob('*/received/*.json')]
    previous = [r for r in previous if r['status'] == 'Success']
    last = max(previous, key=lambda r: float(r['parameters']['fmin']))
    snapshot = Path(last['snapshot'])
    assert snapshot.is_file()
    assert file_hash(snapshot) == last['snapshot_sha256']
    source = ROOT / HOM_PROFILE_V1.source_project
    destination = ROOT / '.pytest_cache' / 'controlled' / uuid4().hex[:8]
    destination.mkdir(parents=True)
    cases = [
        ('original_cold', source, None),
        ('snapshot_cold', snapshot, None),
        ('snapshot_warm', snapshot, last['parameters']),
    ]
    if args.window_widths:
        if any(width <= 0 for width in args.window_widths):
            raise ValueError('window widths must be positive')
        cases = [(f'width_{width:g}', source, None) for width in args.window_widths]
    results = {}
    print(f'COMPARISON_ROOT={destination}', flush=True)
    for name, project, prime in cases:
        case_parameters = dict(parameters)
        case_parameters['nmodes'] = args.nmodes
        if args.window_widths:
            width = float(name.removeprefix('width_'))
            case_parameters['fmax'] = case_parameters['fmin'] + width
        print(f'START {name} parameters={case_parameters}', flush=True)
        results[name] = run_case(destination / name, Path(args.cst_exe), project, case_parameters, prime, args.all_modes)
        result = results[name].get('result') or {}
        print(f'END {name} status={result.get("TaskStatus")} failure={result.get("FailureReport")} stop_ack={results[name].get("stop_ack")} alive={results[name].get("process_alive")}', flush=True)
        write_json_atomic(destination / 'report.json', results)
        if results[name].get('process_alive'):
            print('HALTED: test session still alive; no further cases or automatic kill.', flush=True)
            return 2
        if args.window_widths and result.get('TaskStatus') == 'Success':
            break
    return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
