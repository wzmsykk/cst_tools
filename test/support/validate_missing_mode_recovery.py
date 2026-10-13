"""Real missing-mode readout failure followed by same-worker recovery; no kill."""
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
    args = parser.parse_args()
    with exclusive_probe(ROOT):
        destination = ROOT / 'artifacts' / ('missing-mode-recovery-' + uuid4().hex[:8])
        destination.mkdir(parents=True)
        source = ROOT / 'artifacts/hom-mesh-baseline-de2d6b90/cell-30/prepared.cst'
        before = file_hash(source)
        report = {'source_sha256': before, 'results': []}
        config = _config(destination, '0', args.cst_exe, source)
        config['postProcess'] = [
            {'method': 'Frequency', 'resultName': 'mode_2_frequency',
             'params': {'iModeNumber': 2}},
        ]
        worker = None
        print(f'ACCEPTANCE_ROOT={destination}', flush=True)
        try:
            worker = ManagedCSTWorker('0', config)
            for count in (1, 2):
                result = dict(worker.run_task(f'mode_2_readout_nmodes_{count}', params={
                    'nmodes': count, 'fmin': 513.492631838138,
                    'fmax': 713.492631838138}))
                report['results'].append(result)
                write_json_atomic(destination / 'report.json', report)
                print(f'TASK_COMPLETE nmodes={count} status={result["TaskStatus"]}', flush=True)
                if count == 1:
                    assert result['TaskStatus'] == 'Failure', result
                    assert not result['PostProcessResult'], result
                    assert 'Missing eigenmode #2' in str(result), result
                else:
                    assert result['TaskStatus'] == 'Success', result
                    assert len(result['PostProcessResult']) == 1, result
                    assert float(result['PostProcessResult'][0]['value']) > 0, result
            report['same_worker_recovered'] = True
        except BaseException as error:
            report['failure'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            try:
                if worker is not None:
                    report['stop_returned'] = worker.stop()
                    report['stop_ack'] = worker.protocol.read_stop_ack(worker.session_id) is not None
                    report['exit_code'] = worker._process.poll()
                    log = worker.log_path.read_text(errors='replace')
                    report['shutdown_errors'] = [token for token in (
                        'Unable to close sheet while a batch job is running',
                        'Expecting an existing scalar var.',
                        'EvaluateInternal CDbl(concaveL)') if token in log]
            finally:
                report['source_unchanged'] = file_hash(source) == before
                write_json_atomic(destination / 'report.json', report)
        assert report['stop_returned'] and report['stop_ack'], report
        assert report['exit_code'] == 0 and report['source_unchanged'], report
        assert not report['shutdown_errors'], report
        print('ACCEPTANCE_PASSED', flush=True)


if __name__ == '__main__':
    main()
