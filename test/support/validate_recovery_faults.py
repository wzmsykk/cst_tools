"""Serial, test-only real recovery fault injection. Never terminate CST."""
import argparse
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.acceptance_session import exclusive_probe, cst_processes
from csttool.configuration import read_json, write_json_atomic
from csttool.managed_cstworker import ManagedCSTWorker, ManagedWorkerShutdownError
from csttool.result_reconciliation import file_hash
from csttool.project_session_recovery import discover_managed_sessions, recover_project_sessions
from test.managed_hom_ten_modes_fault_resume_integration_test import _config


class RecoveryFaultWorker(ManagedCSTWorker):
    fault = None

    def _build_macro(self):
        super()._build_macro()
        if self.fault == 'rebuild':
            source = self.macro_path.read_text(encoding='ascii')
            anchor = '        If Not Rebuild Then Err.Raise vbObjectError + 2401'
            assert source.count(anchor) == 1
            # Real invalid parameter, not a mocked return or injected Err.Raise.
            source = source.replace(anchor, '        StoreParameter "nmodes", "0"\n' + anchor)
            self.macro_path.write_text(source, encoding='ascii', newline='\n')
            self.batch_script_path.write_text(source, encoding='ascii', newline='\n')


def reconcile_report(root):
    """Close only a confirmed dead isolated session, never reuse its damaged copy."""
    root = Path(root).resolve()
    root.relative_to((ROOT / 'artifacts').resolve())
    report = read_json(root / 'report.json')
    assert report.get('gate_passed'), report
    records = discover_managed_sessions(root)
    assert len(records) == 1 and records[0].process_alive is False, records
    recover_project_sessions(root)
    records = discover_managed_sessions(root)
    assert not any(record.needs_recovery for record in records), records
    report['recovery_disposition'] = records[0].recovery_disposition
    assert report['recovery_disposition'] == 'abandoned-dead', report
    write_json_atomic(root / 'report.json', report)
    return report['recovery_disposition']


def run_case(executable, root, fault):
    source = ROOT / 'artifacts/hom-mesh-baseline-de2d6b90/cell-30/prepared.cst'
    before = file_hash(source)
    config = _config(root, '0', executable, source)
    config['postProcess'] = [{'method': 'Frequency', 'resultName': 'frequency',
                              'params': {'iModeNumber': 1}}]
    RecoveryFaultWorker.fault = fault
    worker = None
    report = {'fault': fault, 'source_sha256': before}
    try:
        worker = RecoveryFaultWorker('0', config)
        failed = dict(worker.run_task('bad-rebuild', params={'nmodes': 0}))
        report['failed_result'] = failed
        assert failed['TaskStatus'] == 'Failure' and 'REBUILD_FAILED' in failed['FailureReport'], failed
        if fault in ('snapshot', 'receipt'):
            suffix = '.recovered.cst' if fault == 'snapshot' else '.recovery-saved'
            # Directory in a fresh, exact owned output path blocks a real file write.
            blocker = Path(str(worker.project_path) + suffix)
            blocker.mkdir()
            report['write_blocker'] = str(blocker)
        try:
            worker.stop()
            report['stop_rejected'] = False
        except ManagedWorkerShutdownError as error:
            report['stop_rejected'] = True
            report['stop_error'] = str(error)
        report['stop_ack'] = worker.protocol.read_stop_ack(worker.session_id) is not None
        report['exit_code'] = worker._process.poll()
        report['lifecycle'] = (worker.observation_root / 'lifecycle.log').read_text(errors='replace')
        report['solver_calls'] = report['lifecycle'].count('calling EigenmodeSolver.Start')
        report['active_cst'] = cst_processes()
        expected = {'rebuild': 'recovery-rebuild', 'snapshot': 'recovery-snapshot',
                    'receipt': 'recovery-receipt'}[fault]
        assert report['stop_rejected'] and not report['stop_ack'], report
        assert f'shutdown {expected} failed:' in report['lifecycle'], report
        assert report['exit_code'] is not None and not report['active_cst'], report
        assert report['solver_calls'] == 0, report
        assert not failed['PostProcessResult'] and not failed['ProjectSnapshot'], report
        report['gate_passed'] = True
    except BaseException as error:
        report['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['source_unchanged'] = file_hash(source) == before
        write_json_atomic(root / 'report.json', report)
    assert report['source_unchanged'], report
    reconcile_report(root)
    print(f'FAULT_PASSED {fault} root={root}', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True, type=Path)
    parser.add_argument('--fault', choices=('all', 'rebuild', 'snapshot', 'receipt'), default='all')
    parser.add_argument('--existing-root', type=Path, help='Reconcile saved passed fault reports without launching CST')
    args = parser.parse_args()
    if args.existing_root:
        for fault in ('rebuild', 'snapshot', 'receipt'):
            print(f'{fault}: {reconcile_report(args.existing_root / fault)}', flush=True)
        return
    root = ROOT / 'artifacts' / ('recovery-faults-' + uuid4().hex[:8])
    print(f'ACCEPTANCE_ROOT={root}', flush=True)
    for fault in (('rebuild', 'snapshot', 'receipt') if args.fault == 'all' else (args.fault,)):
        with exclusive_probe(ROOT):
            destination = root / fault
            destination.mkdir(parents=True)
            run_case(args.cst_exe, destination, fault)


if __name__ == '__main__':
    main()
