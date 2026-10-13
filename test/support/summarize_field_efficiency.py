"""Summarize matched repetitions; do not double-count native export sampling."""
import argparse
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.configuration import read_json, write_json_atomic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    report = read_json(args.report)
    summary = {'completion': report['completion'], 'exit_code': report['exit_code'],
               'source_unchanged': report['source_unchanged'],
               'cst_process_seconds': report['cst_process_seconds'], 'levels': []}
    for count in sorted({row['points'] for row in report['python']}):
        rows = [r for r in report['python'] if r['points'] == count]
        stages = {stage: statistics.median(float(x['seconds']) for x in report['cst_timings']
                  if int(x['points']) == count and x['stage'] == stage)
                  for stage in ('sample','vba-sum','csv-write','native-ascii','native-hdf5')}
        routes = {'vba': [], 'csv_python': [], 'hdf_python': []}
        for row in rows:
            timing = {x['stage']: float(x['seconds']) for x in report['cst_timings']
                      if int(x['points']) == count and int(x['repeat']) == row['repeat']}
            routes['vba'].append(timing['sample'] + timing['vba-sum'])
            routes['csv_python'].append(timing['sample'] + timing['csv-write']
                + row['read_seconds'] + row['conversion_seconds'] + row['compute_seconds'])
            routes['hdf_python'].append(timing['native-hdf5'] + row['hdf_read_seconds']
                + row['hdf_conversion_seconds'] + row['hdf_compute_seconds'])
        summary['levels'].append({'points': count, 'cst_stage_medians': stages,
            'route_medians': {k: statistics.median(v) for k,v in routes.items()},
            'route_ranges': {k: [min(v),max(v)] for k,v in routes.items()},
            'python_stage_medians': {k: statistics.median(r[k] for r in rows)
                 for k in ('read_seconds','compute_seconds','hdf_read_seconds','hdf_conversion_seconds','hdf_compute_seconds')},
            'hdf_pair_bytes': rows[0]['native_hdf5_bytes'],
            'maximum_norm_scaled_error': max(r['hdf_maximum_norm_scaled_error'] for r in rows),
            'maximum_field_difference': max(r['hdf_vs_sample_maximum_relative_field_error'] for r in rows)})
    write_json_atomic(args.report.with_name('summary.json'), summary)
    print(summary)


if __name__ == '__main__':
    main()
