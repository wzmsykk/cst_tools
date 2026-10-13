"""Stop immediately after real failed history rebuild, without a recovery solve."""
import argparse
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.acceptance_session import exclusive_probe
from csttool.configuration import write_json_atomic
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.result_reconciliation import file_hash
from test.managed_hom_ten_modes_fault_resume_integration_test import _config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True, type=Path)
    parser.add_argument('--after-success', action='store_true')
    args = parser.parse_args()
    with exclusive_probe(ROOT):
        root = ROOT / 'artifacts' / ('failed-rebuild-stop-' + uuid4().hex[:8])
        root.mkdir(parents=True)
        source = ROOT / 'artifacts/hom-mesh-baseline-de2d6b90/cell-30/prepared.cst'
        before = file_hash(source)
        report = {'source_sha256': before, 'after_success': args.after_success}
        config = _config(root, '0', args.cst_exe, source)
        config['paramList'] += [{'name': 'Gap', 'type': 'double'},
                                {'name': 'transient_probe', 'type': 'double'}]
        config['postProcess'] = [{'method': 'Frequency', 'resultName': 'frequency',
                                  'params': {'iModeNumber': 1}}]
        worker = None
        print(f'ACCEPTANCE_ROOT={root}', flush=True)
        try:
            worker = ManagedCSTWorker('0', config)
            if args.after_success:
                result = dict(worker.run_task('good-before-bad', params={
                    'nmodes': 1, 'fmin': 513.492631838138,
                    'fmax': 713.492631838138, 'Gap': 150}))
                report['good_result'] = result
                assert result['TaskStatus'] == 'Success', result
                report['good_snapshot_sha256'] = file_hash(Path(result['ProjectSnapshot']))
            failed = dict(worker.run_task('invalid-modes-stop-directly', params={
                'nmodes': 0, 'Gap': 140, 'transient_probe': 7,
                'fmin': 513.492631838138, 'fmax': 713.492631838138}))
            report['failed_result'] = failed
            assert failed['TaskStatus'] == 'Failure', failed
            assert 'REBUILD_FAILED' in failed['FailureReport'], failed
            assert not failed['PostProcessResult'] and not failed['ProjectSnapshot'], failed
        except BaseException as error:
            report['failure'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            try:
                if worker is not None:
                    try:
                        report['stop_returned'] = worker.stop()
                    except Exception as error:
                        report['stop_returned'] = False
                        report['stop_error'] = str(error)
                    report['stop_ack'] = worker.protocol.read_stop_ack(worker.session_id) is not None
                    report['exit_code'] = worker._process.poll()
                    report['saved_recovery_snapshot'] = Path(str(worker.project_path) + '.recovered.cst').is_file()
                    report['recovery_receipt'] = Path(str(worker.project_path) + '.recovery-saved').read_text()
                    lifecycle = (worker.observation_root / 'lifecycle.log').read_text(errors='replace')
                    report['recovery_rebuild_passed'] = 'returned True' in lifecycle and 'stage=recovery-rebuild' in lifecycle
                    report['solver_calls'] = lifecycle.count('calling EigenmodeSolver.Start')
                    report['checkpoint'] = Path(str(worker.project_path) + '.last-good-parameters.tsv').read_text()
                    if args.after_success and 'good_result' in report:
                        snapshot = Path(report['good_result']['ProjectSnapshot'])
                        report['good_snapshot_unchanged'] = file_hash(snapshot) == report['good_snapshot_sha256']
            finally:
                report['source_unchanged'] = file_hash(source) == before
                write_json_atomic(root / 'report.json', report)
        assert report['stop_returned'] and report['stop_ack'] and report['exit_code'] in (0, 4), report
        assert report['saved_recovery_snapshot'], report
        assert report['source_unchanged'] and report['recovery_rebuild_passed'], report
        assert report['solver_calls'] == int(args.after_success), report
        assert 'concaveL\t(Leq-Gap)/2' in report['checkpoint'], report
        if args.after_success:
            assert report['good_snapshot_unchanged'], report
        print('FAILED_REBUILD_STOP_PASSED', flush=True)


if __name__ == '__main__':
    main()
