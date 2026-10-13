"""Permutation-insensitive scalar diagnostics; not physical mode identification."""
import argparse
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.configuration import read_json, write_json_atomic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    report = read_json(args.report)
    points = []
    previous = None
    stable = 0
    recommendation = None
    for raw in report['points']:
        result = raw.get('result') or {}
        if result.get('TaskStatus') != 'Success':
            continue
        metrics = {item['resultName']: item['value'] for item in result['PostProcessResult']}
        # Two polarization-like scalar signatures: this is ONLY a heuristic.
        order = sorted(metrics['R_divide_Q'], key=metrics['R_divide_Q'].get)
        values = {f'{name}:signature-{index}': float(mode_values[mode])
                  for name, mode_values in metrics.items()
                  for index, mode in enumerate(order)}
        frequencies = list(metrics['frequency'].values())
        point = {'cell': raw['cell'], 'signature_order': order,
                 'center_frequency_mhz': sum(frequencies) / len(frequencies),
                 'splitting_mhz': max(frequencies) - min(frequencies),
                 'r_over_q_sums': {name: sum(v.values()) for name, v in metrics.items()
                                  if name.startswith('R_divide_Q')},
                 'raw_maximum_change': raw.get('maximum_relative_change')}
        mesh_log = Path(raw['output.txt']).with_name('log.tet')
        if mesh_log.exists():
            stats = re.findall(r'Volume mesh stats: Nb nodes = (\d+).*?Nb tets = (\d+)',
                               mesh_log.read_text(encoding='utf-8', errors='replace'))
            if stats:
                point['mesh_nodes'], point['tetrahedra'] = map(int, stats[-1])
        if previous is not None:
            changes = {key: abs(value - previous[key]) / max(abs(value), abs(previous[key]), 1e-30)
                       for key, value in values.items()}
            point['signature_relative_changes'] = changes
            point['signature_maximum_change'] = max(changes.values())
            stable = stable + 1 if max(changes.values()) <= 0.05 else 0
            if stable >= 2 and recommendation is None:
                recommendation = raw['cell']
        points.append(point)
        previous = values
    analysis = {'tolerance': 0.05, 'physical_mode_identity_verified': False,
                'provisional_signature_stable_cell': recommendation,
                'warning': 'R/Q sorting is a diagnostic heuristic, not field overlap or proof of a polarization pair.',
                'points': points}
    write_json_atomic(args.report.with_name('scalar-analysis.json'), analysis)
    print(analysis)


if __name__ == '__main__':
    main()
