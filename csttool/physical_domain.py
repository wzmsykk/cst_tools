"""Explicit common support and SI midpoint volume quadrature, never inferred from E=0."""
from dataclasses import dataclass
from hashlib import sha256
import json
import numpy as np
from .field_artifacts import SamplingSpec


@dataclass(frozen=True)
class DomainSupport:
    sampling: SamplingSpec
    material_labels: tuple[str, ...]
    geometry_id: str
    provenance: str
    verified: bool

    def __post_init__(self):
        object.__setattr__(self,'material_labels',tuple(self.material_labels))
        if len(self.material_labels) != int(np.prod(self.sampling.counts)):
            raise ValueError('material/support inventory differs from sampling')
        if not self.geometry_id or not self.provenance or self.verified is not True:
            raise ValueError('unverified geometry/material support')
        if any(not isinstance(label, str) or not label for label in self.material_labels):
            raise ValueError('unknown material classification')

    @property
    def identity(self):
        value = {'sampling': self.sampling.identity, 'materials': self.material_labels,
                 'geometry': self.geometry_id, 'provenance': self.provenance}
        return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class CommonQuadrature:
    sampling: SamplingSpec
    weights_m3: tuple[float, ...]
    materials: tuple[str, ...]
    support_ids: tuple[str, ...]
    scope: str
    support_disagreement_fraction: float
    support_evidence: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        object.__setattr__(self,'weights_m3',tuple(self.weights_m3))
        object.__setattr__(self,'materials',tuple(self.materials))
        object.__setattr__(self,'support_ids',tuple(self.support_ids))
        object.__setattr__(self,'support_evidence',tuple(tuple(item) for item in self.support_evidence))
        values = np.asarray(self.weights_m3)
        if values.shape != (int(np.prod(self.sampling.counts)),) or not np.isfinite(values).all():
            raise ValueError('invalid quadrature inventory')
        if np.any(values < 0) or not np.any(values > 0):
            raise ValueError('empty/negative common volume')
        if self.scope not in ('common-material-domain','common-intersection'):
            raise ValueError('invalid common-domain scope')
        if not np.isfinite(self.support_disagreement_fraction) or not 0 <= self.support_disagreement_fraction <= 1:
            raise ValueError('invalid support disagreement fraction')

    @property
    def volume_m3(self):
        return float(np.sum(self.weights_m3))

    @property
    def identity(self):
        value = {'sampling': self.sampling.identity, 'weights_m3': self.weights_m3,
                 'materials': self.materials, 'support_ids': self.support_ids,
                 'rule': 'masked-cell-midpoint-volume-v1', 'scope': self.scope}
        return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    def to_mapping(self):
        return {'identity': self.identity, 'sampling_id': self.sampling.identity,
                'scope': self.scope, 'rule': 'masked-cell-midpoint-volume-v1',
                'volume_m3': self.volume_m3, 'weight_unit': 'm^3',
                'materials': list(self.materials), 'support_ids': list(self.support_ids),
                'support_evidence':[{'geometry_id':g,'provenance':p} for g,p in self.support_evidence],
                'sampling_scope':self.sampling.scope,
                'coverage_claim':'selected materials in declared sampling box; whole geometry requires independent gate',
                'support_disagreement_fraction': self.support_disagreement_fraction,
                'boundary_rule': 'point-classification; cut-cell error requires refinement',
                'physical_identity_confirmed': False}


def common_quadrature(supports, materials, *, allow_intersection=False):
    supports = tuple(supports)
    materials = tuple(sorted(set(materials)))
    if not supports or not materials or any(not isinstance(x, str) or not x or x=='excluded' for x in materials):
        raise ValueError('explicit nonempty supports/material selection required')
    first = supports[0].sampling
    if any(s.sampling.identity != first.identity for s in supports):
        raise ValueError('supports need identical common physical points')
    labels = np.array([s.material_labels for s in supports])
    eligible = np.isin(labels, materials)
    # Also reject differing material identities even when both happen to be selected.
    agreement = np.all(labels == labels[0], axis=0)
    disagreement = np.any(eligible, axis=0) & (~agreement | np.any(eligible != eligible[0], axis=0))
    fraction = float(np.mean(disagreement))
    geometry_changed = len({s.geometry_id for s in supports}) > 1
    if (fraction or geometry_changed) and not allow_intersection:
        raise ValueError('geometry/material support changed; not a common full domain')
    common = np.all(eligible, axis=0) & agreement
    return CommonQuadrature(first, tuple(first.weights() * common), materials,
                            tuple(s.identity for s in supports),
                            'common-intersection' if fraction or geometry_changed else 'common-material-domain', fraction,
                            tuple((s.geometry_id,s.provenance) for s in supports))


def cylinder_support(sampling, radius_m, zmin_m, zmax_m, *, center_xy_m=(0., 0.),
                     material='Vacuum', geometry_id='analytic-cylinder'):
    """Analytic benchmark only: does not certify arbitrary CST geometry."""
    params = np.array([radius_m, zmin_m, zmax_m, *center_xy_m])
    if not np.isfinite(params).all() or radius_m <= 0 or zmin_m >= zmax_m:
        raise ValueError('invalid cylinder')
    required = (center_xy_m[0]-radius_m, center_xy_m[0]+radius_m,
                center_xy_m[1]-radius_m, center_xy_m[1]+radius_m, zmin_m, zmax_m)
    if any(sampling.bounds_m[2*i] > required[2*i] or
           sampling.bounds_m[2*i+1] < required[2*i+1] for i in range(3)):
        raise ValueError('sampling box does not cover whole cylinder')
    points = sampling.points()
    inside = (np.sum((points[:, :2] - center_xy_m)**2, axis=1) < radius_m**2)
    inside &= (points[:, 2] > zmin_m) & (points[:, 2] < zmax_m)
    digest = sha256(json.dumps(params.tolist()).encode()).hexdigest()
    return DomainSupport(sampling, tuple(np.where(inside, material, 'excluded').tolist()),
                         geometry_id + ':' + digest, 'analytic-cylinder-with-explicit-material', True)


def sampling_convergence(levels, *, tolerance, expected_volume_m3=None):
    """Gate volume and phase/amplitude-invariant normalized Gram matrices at >=3 levels."""
    if not 0 < tolerance < 1 or len(levels) < 3:
        raise ValueError('three sampling levels and explicit tolerance required')
    errors = []
    previous = None
    previous_cells = 0
    for level in levels:
        counts = tuple(level['counts'])
        if len(counts)!=3 or any(isinstance(n,bool) or not isinstance(n,int) or n<1 for n in counts):
            raise ValueError('invalid refinement counts')
        cells = int(np.prod(counts))
        volume = float(level['volume_m3'])
        gram = np.asarray(level['normalized_gram_abs'], dtype=float)
        norms = np.asarray(level['mode_l2_norms'], dtype=float)
        if cells <= previous_cells or volume <= 0 or not np.isfinite(volume) or not np.isfinite(gram).all():
            raise ValueError('invalid/non-increasing convergence level')
        if gram.ndim != 2 or gram.shape[0] != gram.shape[1] or not gram.size:
            raise ValueError('invalid Gram matrix')
        if np.any(gram < 0) or np.any(gram > 1+1e-8) or not np.allclose(gram,gram.T,atol=1e-8):
            raise ValueError('invalid normalized Gram magnitudes')
        if norms.shape != (len(gram),) or not np.isfinite(norms).all() or np.any(norms <= 0):
            raise ValueError('invalid field L2 norms')
        if previous is not None:
            if gram.shape != previous[1].shape:
                raise ValueError('mode group size changed during refinement')
            errors.append({'volume_relative_change': abs(volume-previous[0])/volume,
                           'gram_max_abs_change': float(np.max(np.abs(gram-previous[1]))),
                           'l2_max_relative_change': float(np.max(np.abs(norms-previous[2])/norms))})
        previous, previous_cells = (volume, gram, norms), cells
    volume_error = None
    if expected_volume_m3 is not None:
        if not np.isfinite(expected_volume_m3) or expected_volume_m3 <= 0:
            raise ValueError('invalid analytic volume')
        volume_error = abs(previous[0]-expected_volume_m3)/expected_volume_m3
    passed = all(max(row.values()) <= tolerance for row in errors[-2:])
    passed &= volume_error is None or volume_error <= tolerance
    return {'status': 'converged' if passed else 'unconfirmed', 'tolerance': tolerance,
            'changes': errors, 'analytic_volume_relative_error': volume_error,
            'physical_identity_confirmed': False,
            'warning': 'sampling convergence is not solver mesh convergence or physical identity'}
