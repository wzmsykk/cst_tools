"""Opt-in full managed-macro startup/standard-stop comparison, without solving."""
import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.worker_models import WorkerConfig
from csttool.runtime_protocol import atomic_publish
from test.cst_integration_support import cst_processes, windows_process_snapshot, new_cst_processes


def run_comparison(executable):
    root = ROOT / '.pytest_cache/worker-startup-comparison' / uuid4().hex[:8]
    root.mkdir(parents=True)
    logging.basicConfig(level=logging.INFO)
    reports = []
    for name, background in [('normal', False), ('minimized', True)]:
        case = root / name
        config = WorkerConfig(case / 'temp', case / 'results', Path(executable),
                              ROOT / 'model/Pillbox_2015.cst', (), background=background)
        baseline = cst_processes(windows_process_snapshot())
        started = time.monotonic()
        worker = None
        entry = {'case': name, 'ready': False, 'standard_stop': False,
                 'qt_qpa_platform': os.environ.get('QT_QPA_PLATFORM')}
        try:
            worker = ManagedCSTWorker('0', config)
            entry['ready'] = True
            entry['session'] = worker.session_id
            entry['standard_stop'] = worker.stop()
            entry['stop_ack'] = worker.protocol.read_stop_ack(worker.session_id) is not None
            entry['exit_code'] = worker._process.poll()
        except Exception as exc:
            entry['error'] = f'{type(exc).__name__}: {exc}'
        finally:
            if worker is not None:
                worker._close_log()
        entry['elapsed'] = time.monotonic() - started
        entry['remaining'] = new_cst_processes(baseline)
        reports.append(entry)
        atomic_publish(case / 'report.json', json.dumps(entry, indent=2))
        print(json.dumps(entry), flush=True)
        if entry['remaining']:
            print('Live sessions require standard recovery; stopping comparison.', flush=True)
            break
    atomic_publish(root / 'report.json', json.dumps(reports, indent=2))
    print(f'Report: {root / "report.json"}', flush=True)
    return reports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True)
    args = parser.parse_args()
    run_comparison(args.cst_exe)


if __name__ == '__main__':
    main()
