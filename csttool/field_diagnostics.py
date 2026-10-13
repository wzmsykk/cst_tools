"""Recoverable optional field analysis, independent of solver acceptance/Ack."""
from dataclasses import asdict
import logging
from pathlib import Path
import time
import numpy as np
from .configuration import write_json_atomic
from .field_artifacts import read_field
from .mode_matching import weighted_overlap, normalized_mac, match_modes, compare_subspaces


def compare_fields(reference, candidates, policy):
    all_fields=list(reference)+list(candidates)
    if not reference or not candidates:
        raise ValueError('reference and candidate groups must be nonempty')
    first=reference[0]
    if any(a.sampling.identity!=first.sampling.identity or a.field_kind!=first.field_kind
           or a.coordinates_unit!=first.coordinates_unit for a in all_fields):
        raise ValueError('sampling/field/units mismatch')
    for group in (reference,candidates):
        if len({a.mode for a in group})!=len(group):
            raise ValueError('duplicate mode identity')
    start=time.perf_counter()
    a=np.stack([read_field(f) for f in reference],axis=-1)
    b=np.stack([read_field(f) for f in candidates],axis=-1)
    prepared=time.perf_counter()
    matrices=weighted_overlap(a,b,first.sampling.weights(),scope=first.sampling.scope)
    mac=normalized_mac(matrices,policy.numerical_tolerance)
    matches=match_modes(mac,([f.frequency_hz for f in reference],[f.frequency_hz for f in candidates]),policy)
    group=compare_subspaces(matrices,policy)
    def complex_matrix(values):
        return {'real':values.real.tolist(),'imag':values.imag.tolist()}
    return {'schema_version':1,'status':'complete','scope':first.sampling.scope,
            'physical_identity_confirmed':False,
            'metric_kind':matrices.metric_kind,'sampling_id':first.sampling.identity,
            'policy':asdict(policy),'policy_calibrated':False,
            'reference':[{'mode':f.mode,'frequency_hz':f.frequency_hz,'sha256':f.file_sha256} for f in reference],
            'candidate':[{'mode':f.mode,'frequency_hz':f.frequency_hz,'sha256':f.file_sha256} for f in candidates],
            'mac':mac.tolist(),'members':matches,'group':group,
            'matrices':{'reference':complex_matrix(matrices.reference),'candidate':complex_matrix(matrices.candidate),'cross':complex_matrix(matrices.cross)},
            'normalization':'per-mode amplitude and common weight scale removed; not physical stored energy',
            'timing':{'prepare_seconds':prepared-start,'compute_seconds':time.perf_counter()-prepared},
            'warnings':['diagnostic scope only; matching policy not physically calibrated']}


def run_field_diagnostic(reference, candidates, policy, destination, *, context=None,
                         run_store=None, cancelled=lambda:False, logger=None):
    """Reruns only analysis of supplied artifacts; no CST/solver callback exists."""
    destination=Path(destination)
    logger=logger or logging.getLogger(__name__)
    context=dict(context or {})
    try:
        if cancelled():
            result={'status':'cancelled','reason':'stop-requested'}
        else:
            result=compare_fields(reference,candidates,policy)
            if cancelled():
                result={'status':'cancelled','reason':'stop-requested-after-analysis'}
    except Exception as exc:
        result={'status':'incomplete','reason':f'{type(exc).__name__}: {exc}'}
    result={**result,'context':context}
    # Persistence failure propagates; the caller must not manufacture a durable success.
    write_json_atomic(destination,result)
    logger.info('场诊断结束 | FIELD_DIAGNOSTIC_COMPLETE status=%s path=%s reason=%s',
                result['status'],destination,result.get('reason','none'),
                extra={'event':'FIELD_DIAGNOSTIC_COMPLETE','phase':'field-analysis',
                       'status':result['status'],'artifacts':{'diagnostic':str(destination)},**context})
    if run_store is not None:
        run_store.artifacts(context['task_id'],field_diagnostic=destination)
    return result
