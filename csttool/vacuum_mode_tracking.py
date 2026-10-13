"""Opt-in fixed-reference tracking for declared closed PEC/vacuum cavities.

No solver callbacks, automatic reference drift, physical mode merging or HOM
interval acceptance. Numerical matches are conditional on supplied domain evidence.
"""
from dataclasses import asdict, dataclass
from itertools import combinations, permutations
import logging

import numpy as np

from .configuration import read_json, write_json_atomic
from .field_artifacts import FieldArtifact, artifacts_from_result, read_field
from .geometry_support import load_material_support
from .mode_matching import (
    MatchPolicy, OverlapMatrices, compare_subspaces, match_modes, normalized_mac, weighted_overlap,
)
from .physical_domain import DomainSupport, common_quadrature


@dataclass(frozen=True)
class VacuumTrackingDomain:
    geometry_id: str
    background: str
    interior: str
    closed: bool
    boundary_evidence: str
    coverage_evidence: str
    sampling_evidence: str

    def __post_init__(self):
        if self.background != 'PEC' or self.interior != 'Vacuum' or self.closed is not True:
            raise ValueError('v1 requires a closed PEC background / Vacuum interior')
        if any(not isinstance(x, str) or not x.strip() for x in (
                self.geometry_id, self.boundary_evidence, self.coverage_evidence, self.sampling_evidence)):
            raise ValueError('explicit geometry, boundary, coverage and sampling evidence required')


@dataclass(frozen=True)
class TrackingSnapshot:
    snapshot_id: str
    fields: tuple[FieldArtifact, ...]
    support: DomainSupport

    def __post_init__(self):
        object.__setattr__(self, 'fields', tuple(self.fields))
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError('snapshot identity required')


def _validate_snapshot(snapshot, domain):
    if not snapshot.fields or len(snapshot.fields) > 8:
        raise ValueError('one to eight E-field candidates required')
    if snapshot.support.geometry_id != domain.geometry_id:
        raise ValueError('geometry identity changed')
    if snapshot.support.sampling.scope != 'specified-domain':
        raise ValueError('ROI is not a full-domain tracking input')
    if not set(snapshot.support.material_labels) <= {'Vacuum', 'excluded'}:
        raise ValueError('multi-material support is outside v1')
    if len({f.mode for f in snapshot.fields}) != len(snapshot.fields):
        raise ValueError('duplicate mode identity')
    if any(f.field_kind != 'E' or f.sampling.identity != snapshot.support.sampling.identity
           for f in snapshot.fields):
        raise ValueError('E-field and material sampling identity required')


def _fingerprint(snapshot):
    return {'snapshot_id': snapshot.snapshot_id, 'support_id': snapshot.support.identity,
            'fields': [{'mode': f.mode, 'frequency_hz': f.frequency_hz,
                        'sha256': f.file_sha256} for f in snapshot.fields]}


def select_vacuum_modes(reference, candidate, domain, policy):
    """Choose one mode or an entire declared degenerate reference group.

    The caller declares which reference modes form a group. Frequency closeness
    does not create a group. Group matching does not assign polarization members.
    """
    if policy.maximum_frequency_change is None:
        raise ValueError('tracking requires an explicit relative frequency gate')
    _validate_snapshot(reference, domain)
    _validate_snapshot(candidate, domain)
    n, m = len(reference.fields), len(candidate.fields)
    if n > 4:
        raise ValueError('v1 reference group is limited to four modes')
    q = common_quadrature([reference.support, candidate.support], ['Vacuum'])
    base = {'reference': _fingerprint(reference), 'candidate': _fingerprint(candidate),
            'quadrature': q.to_mapping(), 'selected_modes': [],
            'physical_identity_confirmed': False, 'policy_calibrated': False,
            'member_identity_confirmed': False}
    if m < n:
        return {**base, 'status': 'unconfirmed', 'reason': 'missing-candidates'}
    a = np.stack([read_field(f) for f in reference.fields], axis=-1)
    b = np.stack([read_field(f) for f in candidate.fields], axis=-1)
    matrices = weighted_overlap(a, b, q.weights_m3, scope=q.scope)
    mac = normalized_mac(matrices, policy.numerical_tolerance)
    base['mac'] = mac.tolist()
    fa = np.array([f.frequency_hz for f in reference.fields])
    fb = np.array([f.frequency_hz for f in candidate.fields])
    if n == 1:
        match = match_modes(mac, (fa, fb), policy)
        modes = [candidate.fields[p['candidate_index']].mode for p in match['pairs']]
        return {**base, 'status': match['status'], 'reason': match['reason'],
                'selected_modes': modes, 'members': match,
                'match_kind': 'single-mode'}
    options = []
    for indices in combinations(range(m), n):
        # Spectral eligibility is independent of polarization/MAC assignment.
        if not any(np.all(np.abs(fa-fb[list(order)]) / np.maximum(fa, fb[list(order)])
                          <= policy.maximum_frequency_change) for order in permutations(indices)):
            continue
        # Prepare/accumulate fields once; candidate subsets only slice small matrices.
        subset = OverlapMatrices(matrices.reference,
                                 matrices.candidate[np.ix_(indices, indices)],
                                 matrices.cross[:, indices], scope=q.scope)
        group = compare_subspaces(subset, policy)
        if group['status'] == 'matched':
            options.append((group['minimum_squared_overlap'], indices, group))
    options.sort(key=lambda option: option[0], reverse=True)
    if not options:
        return {**base, 'status': 'unconfirmed', 'reason': 'no-eligible-subspace'}
    margin = options[0][0] - options[1][0] if len(options) > 1 else None
    if margin is not None and margin <= policy.minimum_margin:
        return {**base, 'status': 'unconfirmed', 'reason': 'ambiguous-subspace',
                'margin': margin}
    _, indices, group = options[0]
    return {**base, 'status': 'matched', 'reason': 'explicit-policy-passed',
            'selected_modes': [candidate.fields[i].mode for i in indices],
            'group': group, 'margin': margin, 'match_kind': 'declared-mode-subspace'}


class VacuumModeTracker:
    """Fixed reference; failed or ambiguous steps never promote candidate fields."""

    def __init__(self, reference, domain, policy):
        _validate_snapshot(reference, domain)
        if len(reference.fields) > 4 or policy.maximum_frequency_change is None:
            raise ValueError('four-mode reference limit and explicit frequency gate required')
        q = common_quadrature([reference.support], ['Vacuum'])
        data = np.stack([read_field(f) for f in reference.fields], axis=-1)
        anchor = compare_subspaces(weighted_overlap(data, data, q.weights_m3, scope=q.scope), policy)
        if anchor['status'] != 'matched':
            raise ValueError('invalid or rank-deficient reference group')
        self.reference, self.domain, self.policy = reference, domain, policy

    def evaluate(self, candidate, destination):
        try:
            result = select_vacuum_modes(self.reference, candidate, self.domain, self.policy)
        except Exception as error:
            result = {'status': 'unconfirmed', 'reason': f'{type(error).__name__}: {error}',
                      'selected_modes': [], 'reference': _fingerprint(self.reference),
                      'candidate': _fingerprint(candidate)}
        result = {**result, 'schema_version': 1, 'domain': asdict(self.domain),
                  'policy': asdict(self.policy), 'reference_strategy': 'fixed-anchor',
                  'physical_identity_confirmed': False, 'policy_calibrated': False,
                  'member_identity_confirmed': False,
                  'recovery_action': 'none' if result['status'] == 'matched' else
                      'retain-reference; inspect input or obtain additional candidates; no automatic solver replay'}
        # Propagate persistence failures: a report must not be claimed durable.
        write_json_atomic(destination, result)
        logging.getLogger(__name__).info(
            '真空腔模式追踪 | status=%s reference=%s candidate=%s reason=%s report=%s',
            result['status'], self.reference.snapshot_id, candidate.snapshot_id,
            result['reason'], destination,
            extra={'event': 'VACUUM_MODE_TRACKING', 'phase': 'field-analysis',
                   'reference': self.reference.snapshot_id, 'candidate': candidate.snapshot_id})
        return result


def load_tracking_snapshot(descriptor, domain, *, base):
    """Load archived task/export JSON and a separately hashed native support TSV."""
    from pathlib import Path
    def path(value):
        p = Path(value)
        return p if p.is_absolute() else Path(base) / p
    result_file = path(descriptor['result_file']).resolve()
    result = read_json(result_file)
    directory = result.get('ResultDirectory', result.get('result_directory'))
    if not directory:
        raise ValueError('result directory missing')
    directory = Path(directory)
    if not directory.is_absolute():
        directory = result_file.parent / directory
    steps = result.get('FieldArtifacts') or result.get('PostProcessResult', [])
    # Saved-field export wraps the same collection at top level.
    steps = [s for s in steps if isinstance(s.get('value'), dict)
             and s['value'].get('kind') == 'field-artifact'
             and s['value'].get('field_kind', 'E') == 'E']
    fields = artifacts_from_result(directory, steps)
    selected = descriptor.get('modes')
    if selected is not None:
        if not selected or len(set(selected)) != len(selected):
            raise ValueError('explicit distinct mode selection required')
        by_mode = {f.mode: f for f in fields}
        if len(by_mode) != len(fields):
            raise ValueError('duplicate mode identity')
        fields = [by_mode[mode] for mode in selected]
    if descriptor.get('registration_file'):
        from .vacuum_domain_registry import load_registered_support
        source_sha = result.get('source_sha256')
        if not source_sha:
            raise ValueError('registered input requires source snapshot SHA in export result')
        support = load_registered_support(path(descriptor['registration_file']),
            source_sha256=source_sha, sampling=fields[0].sampling, geometry_id=domain.geometry_id)
    else:
        support = load_material_support(fields[0].sampling, path(descriptor['support_file']),
                                       expected_sha256=descriptor['support_sha256'],
                                       geometry_id=domain.geometry_id)
    snapshot = TrackingSnapshot(descriptor['snapshot_id'], tuple(fields), support)
    _validate_snapshot(snapshot, domain)
    return snapshot


def track_saved_sequence(request_path, output_directory):
    """Replay archived field analysis only; retain every step and input failure."""
    from pathlib import Path
    request_path, output_directory = Path(request_path).resolve(), Path(output_directory).resolve()
    request = read_json(request_path)
    domain = VacuumTrackingDomain(**request['domain'])
    policy = MatchPolicy(**request['policy'])
    reference = load_tracking_snapshot(request['reference'], domain, base=request_path.parent)
    tracker = VacuumModeTracker(reference, domain, policy)
    descriptors = request['candidates']
    identities = [item['snapshot_id'] for item in descriptors]
    if not identities or len(set(identities)) != len(identities):
        raise ValueError('nonempty distinct candidate snapshots required')
    decisions = []
    for index, descriptor in enumerate(descriptors, 1):
        destination = output_directory / f'step-{index:04d}.json'
        try:
            candidate = load_tracking_snapshot(descriptor, domain, base=request_path.parent)
        except Exception as error:
            decision = {'schema_version': 1, 'status': 'unconfirmed',
                        'reason': f'{type(error).__name__}: {error}', 'selected_modes': [],
                        'reference': _fingerprint(reference), 'candidate': descriptor,
                        'reference_strategy': 'fixed-anchor', 'physical_identity_confirmed': False,
                        'policy_calibrated': False, 'member_identity_confirmed': False,
                        'recovery_action': 'restore valid artifacts or supply candidates; no solver replay'}
            write_json_atomic(destination, decision)
            logging.getLogger(__name__).warning(
                '真空腔追踪输入未确认 | candidate=%s reason=%s report=%s',
                descriptor['snapshot_id'], decision['reason'], destination,
                extra={'event': 'VACUUM_MODE_TRACKING', 'phase': 'field-analysis',
                       'reference': reference.snapshot_id, 'candidate': descriptor['snapshot_id']})
        else:
            decision = tracker.evaluate(candidate, destination)
        decisions.append({'snapshot_id': descriptor['snapshot_id'], 'status': decision['status'],
                          'reason': decision['reason'], 'report': str(destination)})
        write_json_atomic(output_directory / 'summary.json', {
            'schema_version': 1, 'reference': _fingerprint(reference), 'steps': decisions,
            'status': 'matched' if all(d['status'] == 'matched' for d in decisions) else 'unconfirmed',
            'solver_replayed': False, 'physical_identity_confirmed': False})
    return decisions


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    decisions = track_saved_sequence(args.request, args.output)
    print(f'Tracking steps={len(decisions)} matched={sum(d["status"] == "matched" for d in decisions)}')
    return 0 if all(d['status'] == 'matched' for d in decisions) else 2


if __name__ == '__main__':
    raise SystemExit(main())
