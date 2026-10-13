"""Real CST missing-result export and real saved HDF5 faults; no solve/rebuild."""
import argparse
from dataclasses import replace
from pathlib import Path
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.configuration import read_json, write_json_atomic
from csttool.field_artifacts import artifacts_from_result
from csttool.field_diagnostics import run_field_diagnostic
from csttool.mode_matching import MatchPolicy
from csttool.result_reconciliation import file_hash
from csttool.saved_field_export import export_saved_fields


def diagnose_saved_faults(reference, root):
    """Mutate owned copies only; source reference file is never changed."""
    import h5py
    before = file_hash(reference.path)
    cases = []
    for name in ('missing-file', 'hash-change', 'missing-dataset', 'wrong-coordinates'):
        directory = root / name
        directory.mkdir(parents=True)
        path = directory / 'field.h5'
        shutil.copy2(reference.path, path)
        candidate = replace(reference, path=path)
        if name == 'missing-file':
            path.rename(directory / 'quarantined.h5')
        elif name == 'hash-change':
            # Replacing a compound field with different bytes is a real HDF change.
            with h5py.File(path, 'r+') as stream:
                stream.attrs['fault-probe'] = 'changed'
        elif name == 'missing-dataset':
            with h5py.File(path, 'r+') as stream:
                del stream[f'{reference.field_kind}-Field']
            candidate = replace(candidate, file_sha256=file_hash(path))
        else:
            with h5py.File(path, 'r+') as stream:
                positions = stream['Position'][...]
                positions['x'] += 1
                stream['Position'][...] = positions
            candidate = replace(candidate, file_sha256=file_hash(path))
        policy = MatchPolicy(minimum_mac=0.9, minimum_margin=0.05, minimum_subspace_overlap=0.99)
        failed = run_field_diagnostic([reference], [candidate], policy, directory / 'failed.json')
        assert failed['status'] == 'incomplete', failed
        # Restore only exported field data; no project parameter mutation or Solver callback.
        shutil.copy2(reference.path, path)
        restored = replace(reference, path=path)
        recovered = run_field_diagnostic([reference], [restored], policy, directory / 'recovered.json')
        assert recovered['status'] == 'complete' and not recovered['physical_identity_confirmed'], recovered
        cases.append({'fault': name, 'failure': failed, 'recovered_status': recovered['status']})
    assert file_hash(reference.path) == before
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True, type=Path)
    parser.add_argument('--resume-root', type=Path, help='Use captured missing-export evidence; rerun analysis only')
    args = parser.parse_args()
    root = (args.resume_root.resolve() if args.resume_root else
            ROOT / 'artifacts' / ('field-failure-recovery-' + uuid4().hex[:8]))
    root.relative_to((ROOT / 'artifacts').resolve())
    root.mkdir(parents=True, exist_ok=bool(args.resume_root))
    print(f'ACCEPTANCE_ROOT={root}', flush=True)
    previous = read_json(ROOT / 'artifacts/cross-mesh-fields-4a14f7cc/cell-30/export-result.json')
    source = Path(previous['source'])
    before = file_hash(source)
    reference = artifacts_from_result(previous['result_directory'], [p for p in previous['PostProcessResult']
        if p['value']['field_kind'] == 'E' and p['value']['mode'] == 1])[0]
    report = {'source_sha256': before}
    try:
        if args.resume_root:
            previous_probe = read_json(root / 'report.json')
            assert previous_probe['source_sha256'] == before
            report['previous_probe_failure'] = previous_probe.get('failure')
            report['analysis_only_retry'] = True
            result = previous_probe['missing_result_export']
        else:
            owned = root / 'cst-only'
            owned.mkdir()
            copy = owned / 'missing-fields.cst'
            shutil.copy2(source, copy)  # Intentionally exclude native result sibling folder.
            settings = [{'method': 'ExportModeField', 'resultName': 'E_missing', 'params': {
                'iModeNumber': 1, 'field_kind': 'E', 'sampling': reference.sampling.to_mapping()}}]
            result = export_saved_fields(args.cst_exe, copy, root / 'missing-export', settings)
        report['missing_result_export'] = result
        assert result['status'] == 'incomplete' and result['solver_run'] is False, result
        assert result['source_unchanged'] and result['session']['exit_confirmed'], result
        assert all(p['value']['status'] == 'unavailable' for p in result['PostProcessResult']), result
        report['saved_hdf_faults'] = diagnose_saved_faults(reference, root / ('analysis-' + uuid4().hex[:8]))
        report['solver_replayed'] = False
        report['gate_passed'] = True
    except BaseException as error:
        report['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['source_unchanged'] = file_hash(source) == before
        write_json_atomic(root / 'report.json', report)
    assert report['source_unchanged']
    print('FIELD_FAILURE_RECOVERY_PASSED', flush=True)


if __name__ == '__main__':
    main()
