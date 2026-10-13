"""Opt-in field diagnostics; never mutate physical results or scan decisions."""
from dataclasses import dataclass
from itertools import permutations
import numpy as np


@dataclass(frozen=True)
class OverlapMatrices:
    reference: np.ndarray
    candidate: np.ndarray
    cross: np.ndarray
    metric_kind: str = "weighted-sampled-field"
    scope: str = "specified-common-domain"


@dataclass(frozen=True)
class MatchPolicy:
    minimum_mac: float
    minimum_margin: float
    minimum_subspace_overlap: float
    rank_tolerance: float = 1e-10
    numerical_tolerance: float = 1e-8
    maximum_frequency_change: float | None = None

    def __post_init__(self):
        for name in ("minimum_mac", "minimum_margin", "minimum_subspace_overlap"):
            value = getattr(self, name)
            if not np.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"invalid {name}")
        for name in ("rank_tolerance", "numerical_tolerance"):
            if not 0 < getattr(self, name) < 1:
                raise ValueError(f"invalid {name}")
        if self.maximum_frequency_change is not None and (
            not np.isfinite(self.maximum_frequency_change) or self.maximum_frequency_change <= 0
        ):
            raise ValueError("invalid frequency gate")


def _field(values):
    field = np.asarray(values, dtype=np.complex128)
    if field.ndim != 3 or field.shape[1] != 3 or min(field.shape) < 1:
        raise ValueError("fields must have shape (points, 3, modes)")
    if not np.isfinite(field).all():
        raise ValueError("nonfinite field")
    return field


def weighted_overlap(reference, candidates, weights, *, scope="specified-common-domain"):
    """Gram/cross matrices of scaled fields, for scale-invariant matching only.

    Input shape is (points, 3, modes). Per-mode amplitude and a common weight
    factor are removed; returned diagonal entries are not physical energy.
    """
    a, b = _field(reference), _field(candidates)
    w = np.asarray(weights, dtype=float)
    if a.shape[:2] != b.shape[:2] or w.shape != (a.shape[0],):
        raise ValueError("point/weight inventory differs")
    if not np.isfinite(w).all() or np.any(w < 0) or not np.any(w > 0):
        raise ValueError("weights must be finite, nonnegative and nonempty")
    # Scale each mode before accumulating to avoid arbitrary field scaling overflow.
    scale_a = np.max(np.abs(a), axis=(0, 1))
    scale_b = np.max(np.abs(b), axis=(0, 1))
    if np.any(scale_a == 0) or np.any(scale_b == 0):
        raise ValueError("zero field")
    w = w / np.max(w)
    af = (a / scale_a * np.sqrt(w)[:, None, None]).reshape(-1, a.shape[2])
    bf = (b / scale_b * np.sqrt(w)[:, None, None]).reshape(-1, b.shape[2])
    return OverlapMatrices(af.conj().T @ af, bf.conj().T @ bf, af.conj().T @ bf,
                           scope=scope)


def _gram(matrix, tolerance):
    g = np.asarray(matrix, dtype=np.complex128)
    if g.ndim != 2 or g.shape[0] != g.shape[1] or g.shape[0] == 0 or not np.isfinite(g).all():
        raise ValueError("invalid Gram matrix")
    scale = max(float(np.max(np.abs(g))), np.finfo(float).tiny)
    if np.max(np.abs(g - g.conj().T)) > tolerance * scale:
        raise ValueError("Gram matrix not Hermitian")
    g = (g + g.conj().T) / 2
    if np.min(np.linalg.eigvalsh(g)) < -tolerance * scale:
        raise ValueError("Gram matrix not positive semidefinite")
    return g


def validate_matrices(matrices, numerical_tolerance=1e-8):
    ga = _gram(matrices.reference, numerical_tolerance)
    gb = _gram(matrices.candidate, numerical_tolerance)
    c = np.asarray(matrices.cross, dtype=np.complex128)
    if c.shape != (len(ga), len(gb)) or not np.isfinite(c).all():
        raise ValueError("invalid cross matrix")
    # The joint Gram must describe a consistent positive inner product.
    _gram(np.block([[ga, c], [c.conj().T, gb]]), numerical_tolerance)
    if np.any(np.diag(ga).real <= 0) or np.any(np.diag(gb).real <= 0):
        raise ValueError("zero weighted norm")
    return ga, gb, c


def normalized_mac(matrices, numerical_tolerance=1e-8):
    ga, gb, c = validate_matrices(matrices, numerical_tolerance)
    values = np.abs(c) ** 2 / np.outer(np.diag(ga).real, np.diag(gb).real)
    if not np.isfinite(values).all() or np.max(values) > 1 + numerical_tolerance:
        raise ValueError("MAC outside numerical bounds")
    return np.clip(values, 0, 1)


def match_modes(mac, frequencies, policy):
    """Small exact assignment; deliberately bounded to avoid factorial expansion."""
    scores = np.asarray(mac, dtype=float)
    if scores.ndim != 2 or scores.size == 0 or not np.isfinite(scores).all() or np.any((scores < 0)|(scores > 1)):
        raise ValueError("invalid MAC matrix")
    n, m = scores.shape
    if n > 4 or m > 8:
        return {"status": "unconfirmed", "reason": "assignment-size-not-supported", "pairs": []}
    if m < n:
        return {"status": "unconfirmed", "reason": "missing-candidates", "pairs": []}
    eligible = scores >= policy.minimum_mac
    if frequencies is not None:
        fa, fb = (np.asarray(f, dtype=float) for f in frequencies)
        if fa.shape != (n,) or fb.shape != (m,) or not np.isfinite(fa).all() or not np.isfinite(fb).all() or np.any(fa<=0) or np.any(fb<=0):
            raise ValueError("invalid frequencies")
        if policy.maximum_frequency_change is not None:
            eligible &= np.abs(fa[:,None]-fb[None,:])/np.maximum(fa[:,None],fb[None,:]) <= policy.maximum_frequency_change
    elif policy.maximum_frequency_change is not None:
        raise ValueError("frequency gate requires frequencies")
    options = [(float(sum(scores[i,j] for i,j in enumerate(p)))/n, p)
               for p in permutations(range(m), n) if all(eligible[i,j] for i,j in enumerate(p))]
    options.sort(reverse=True)
    if not options:
        return {"status": "unconfirmed", "reason": "no-eligible-assignment", "pairs": []}
    margin = options[0][0]-options[1][0] if len(options)>1 else None
    # Also gate local ambiguity even when constraints exclude alternative global assignments.
    local_margins = []
    for i,j in enumerate(options[0][1]):
        other = np.delete(scores[i], j)
        local_margins.append(float(scores[i,j]-np.max(other)) if other.size else None)
    if (margin is not None and margin <= policy.minimum_margin) or any(
        x is not None and x <= policy.minimum_margin for x in local_margins
    ):
        return {"status": "unconfirmed", "reason": "ambiguous-assignment", "pairs": [], "margin": margin}
    return {"status": "matched", "reason": "explicit-policy-passed", "margin": margin,
            "pairs": [{"reference_index": i, "candidate_index": j, "mac": float(scores[i,j])}
                      for i,j in enumerate(options[0][1])]}


def compare_subspaces(matrices, policy):
    ga, gb, c = validate_matrices(matrices, policy.numerical_tolerance)
    def whiten(g):
        values, vectors = np.linalg.eigh(g)
        keep = values > max(values[-1], np.finfo(float).tiny)*policy.rank_tolerance
        return vectors[:,keep]/np.sqrt(values[keep]), int(sum(keep)), values
    wa, rank_a, ea = whiten(ga)
    wb, rank_b, eb = whiten(gb)
    result = {"reference_rank": rank_a, "candidate_rank": rank_b,
              "scope": matrices.scope, "metric_kind": matrices.metric_kind}
    if rank_a != len(ga) or rank_b != len(gb) or rank_a != rank_b:
        return {**result, "status": "unconfirmed", "reason": "rank-or-dimension-mismatch", "singular_values": []}
    singular = np.linalg.svd(wa.conj().T @ c @ wb, compute_uv=False)
    if np.max(singular) > 1 + policy.numerical_tolerance:
        raise ValueError("subspace overlap outside numerical bounds")
    singular = np.clip(singular, 0, 1)
    worst = float(np.min(singular)**2)
    return {**result, "status": "matched" if worst >= policy.minimum_subspace_overlap else "unconfirmed",
            "reason": "explicit-policy-passed" if worst >= policy.minimum_subspace_overlap else "low-subspace-overlap",
            "singular_values": singular.tolist(), "minimum_squared_overlap": worst,
            "reference_condition": float(ea[-1]/ea[0]), "candidate_condition": float(eb[-1]/eb[0])}
