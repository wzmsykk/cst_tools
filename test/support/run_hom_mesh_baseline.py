"""Explicit source-only CST fixed-mesh convergence experiment."""
import argparse
import logging
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from csttool.configuration import write_json_atomic
from csttool.cst_preprocessor import CstProjectPreprocessor
from csttool.result_reconciliation import file_hash
from test.support.compare_cst_snapshot_execution import run_case


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True)
    args = parser.parse_args()
    executable = Path(args.cst_exe)
    source = ROOT / 'project/HOM analysis/HOM analysis_clean.cst'
    original_hash = file_hash(source)
    directory = ROOT / 'artifacts' / ('hom-mesh-baseline-' + uuid4().hex[:8])
    directory.mkdir(parents=True)
    print(f'BASELINE_ROOT={directory}', flush=True)
    report = {'source': str(source), 'source_sha256': original_hash,
              'tolerance': 0.05, 'consecutive_required': 2,
              'recommended_cell': None, 'points': []}
    previous = None
    stable_count = 0
    for cell in (12, 18, 24, 30, 36):
        level = directory / f'cell-{cell}'
        level.mkdir()
        print(f'START cell={cell}', flush=True)
        try:
            prepared = CstProjectPreprocessor(
                executable, ROOT / 'data/preprocess_hom_parameters_v1.vb'
            ).preprocess(source, level / 'prepared.cst', level / 'parameters.json',
                         level / 'preprocess', mesh_cells_per_wavelength=cell)
            point = run_case(level / 'solve', executable, prepared.project_path,
                             {'nmodes': 2, 'fmin': 513.492631838138,
                              'fmax': 713.492631838138}, all_modes=True)
            point['cell'] = cell
            report['points'].append(point)
            result = point.get('result') or {}
            if result.get('TaskStatus') != 'Success' or point.get('process_alive') or not point.get('stop_ack'):
                report['halt_reason'] = 'solve or standard shutdown failed'
                break
            values = {f"{item['resultName']}:{mode}": float(value)
                      for item in result['PostProcessResult']
                      for mode, value in item['value'].items()}
            if len(values) != 14:
                report['halt_reason'] = 'expected seven metrics for two modes'
                break
            if previous is not None:
                if values.keys() != previous.keys():
                    report['halt_reason'] = 'mode/metric inventory changed'
                    break
                changes = {key: abs(value - previous[key]) / max(abs(value), abs(previous[key]), 1e-30)
                           for key, value in values.items()}
                point['relative_changes'] = changes
                point['maximum_relative_change'] = max(changes.values())
                stable_count = stable_count + 1 if max(changes.values()) <= report['tolerance'] else 0
            previous = values
            print(f"END cell={cell} max_change={point.get('maximum_relative_change')} values={values}", flush=True)
            if stable_count >= 2:
                report['recommended_cell'] = cell
                break
        except Exception as exc:
            report['halt_reason'] = f'{type(exc).__name__}: {exc}'
            break
        finally:
            report['source_unchanged'] = file_hash(source) == original_hash
            write_json_atomic(directory / 'report.json', report)
    print(f"FINAL recommended_cell={report['recommended_cell']} reason={report.get('halt_reason')}", flush=True)
    return 0 if report['recommended_cell'] is not None else 1


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
