"""B3 execution-configuration evidence, never live state or solver success.

This module only validates supplied observations/closed artifacts. It neither
queries CST nor creates attempts. Expectations must come from the execution owner.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType


BUILD = '2022.5 Release from 2022-06-03 (change 981760)'
PROFILE_ID = 'cst-2022-root-tet-g6-v1'
_KEYS = ('SolverTypeTet', 'FrequencyTargetActive', 'FrequencyTargetValue',
         'AdaptionActiveTet', 'Modes', 'MeshType')
_METHODS = MappingProxyType({'1': 'Default', '2': 'General (Lossy)'})
_MESHES = MappingProxyType({'1': 'Tet'})
_EMPTY = MappingProxyType({})
_NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')


def is_cst_2022(value):
    """User-selected major-version compatibility, not proof of all 2022 builds."""
    return isinstance(value,str) and bool(re.fullmatch(r'(?:Version )?2022(?:\.[0-9]+)?(?:[ -][^\r\n]*)?',value))


def _time(text):
    if not isinstance(text, str) or len(text) > 64:
        raise ValueError('timezone-aware ISO timestamp required')
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone-aware ISO timestamp required')
    return value


def _decimal(text):
    if not isinstance(text, str) or len(text) > 128 or not _NUMBER.fullmatch(text):
        raise ValueError('finite decimal string required')
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('finite decimal string required') from exc
    if not value.is_finite() or (value and abs(value.adjusted()) > 100):
        raise ValueError('numeric range unsupported')
    return value


def _g6(value):
    # Fixed profile: CST database double -> %lg (six significant digits).
    # Do not derive a tolerance from the number of digits printed in the input.
    return Decimal(format(float(value), '.6g'))


@dataclass(frozen=True)
class ExecutionBinding:
    project_id: str
    attempt_id: str
    definition_revision: str
    database_sha256: str
    cst_build: str
    scope: str

    def __post_init__(self):
        for value in (self.project_id, self.attempt_id, self.definition_revision, self.cst_build, self.scope):
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise ValueError('nonempty bounded binding fields required')
        if not isinstance(self.database_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', self.database_sha256):
            raise ValueError('database SHA256 required')


@dataclass(frozen=True)
class ExecutionConfig:
    method: str
    mesh: str
    target_enabled: bool
    target_value: str
    adaptation_enabled: bool
    requested_modes: int

    def __post_init__(self):
        if type(self.target_enabled) is not bool or type(self.adaptation_enabled) is not bool:
            raise ValueError('boolean switches required')
        if type(self.requested_modes) is not int or not 1 <= self.requested_modes <= 2147483647:
            raise ValueError('positive integer mode count required')
        if not isinstance(self.method, str) or not isinstance(self.mesh, str):
            raise ValueError('method and mesh strings required')
        if _decimal(self.target_value) < 0:
            raise ValueError('negative target not supported')


@dataclass(frozen=True)
class ExecutionExpectation:
    binding: ExecutionBinding
    config: ExecutionConfig
    attempt_started_at: str
    attempt_finished_at: str
    result_success: object
    target_expression: object = None
    definition_sha256: object = None

    def __post_init__(self):
        if not isinstance(self.binding, ExecutionBinding) or not isinstance(self.config, ExecutionConfig):
            raise ValueError('typed binding and config required')
        if _time(self.attempt_finished_at) < _time(self.attempt_started_at):
            raise ValueError('invalid attempt observation window')
        if self.result_success is not None and type(self.result_success) is not bool:
            raise ValueError('result outcome must be independently known boolean or null')
        if self.target_expression is not None and (not isinstance(self.target_expression, str) or len(self.target_expression) > 4096):
            raise ValueError('bounded expression required')
        if self.definition_sha256 is not None and (not isinstance(self.definition_sha256,str)
                                                  or not re.fullmatch(r'[0-9a-f]{64}', self.definition_sha256)):
            raise ValueError('definition SHA256 required')


@dataclass(frozen=True)
class SnapshotReport:
    status: str
    reasons: tuple
    fields: object = field(default_factory=lambda: _EMPTY)
    comparisons: object = field(default_factory=lambda: _EMPTY)
    raw_values: object = field(default_factory=lambda: _EMPTY)
    binding: object = None
    observed_at: object = None
    profile_id: str = PROFILE_ID
    evidence: str = 'native-run-database'
    target_expression: object = None
    publish_ready: bool = False
    live_value: None = None
    database_verified: bool = False


def expectation_from_projection(binding, projection, *, definition_sha256,
                                attempt_started_at, attempt_finished_at, result_success):
    """Freeze execution-owner expectations from B1/B2, not observed database values.

    The owner supplies the published definition digest/revision and attempt times.
    This factory cannot itself authenticate a future RunStore/definition ledger.
    """
    if (projection.status != 'resolved' or projection.source_hash != definition_sha256
            or projection.scope != binding.scope or not re.fullmatch(r'[0-9a-f]{64}', definition_sha256)):
        raise ValueError('projection does not bind to the published definition')
    values = projection.fields
    if any(values.get(key) != expected for key, expected in
           [('units.frequency','MHz'), ('units.length','mm'), ('solver.family','HF Eigenmode')]):
        raise ValueError('projection identity missing')
    names = ('solver.selected_method', 'solver.selected_mesh', 'solver.frequency_target.enabled',
             'solver.frequency_target.value_mhz', 'solver.mesh_adaptation.tet', 'solver.requested_modes')
    if any(key not in values for key in names):
        raise ValueError('execution configuration incomplete')
    if names[3] not in projection.exact_values:
        raise ValueError('exact target value missing')
    config = ExecutionConfig(values[names[0]], values[names[1]], values[names[2]],
                             projection.exact_values[names[3]], values[names[4]], values[names[5]])
    return ExecutionExpectation(binding, config, attempt_started_at, attempt_finished_at, result_success,
                                values.get('expressions.solver.frequency_target.value_mhz'), definition_sha256)


def validate_execution_snapshot(expectation, snapshot, *, profile_id=PROFILE_ID):
    """Compare a bound observation. No file/hash I/O; owner-supplied binding is trusted.

    Use verify_execution_artifact as well when the actual closed database is present.
    profile_id only selects the fixed registered rule; callers cannot supply maps,
    numeric precision, an error tolerance, or a replacement expected config in JSON.
    """
    if not isinstance(expectation, ExecutionExpectation):
        raise TypeError('ExecutionExpectation required')

    def reject(status, reason, *, evidence='native-run-database'):
        return SnapshotReport(status, (reason,), profile_id=profile_id, evidence=evidence,
                              target_expression=expectation.target_expression)

    if profile_id != PROFILE_ID:
        return reject('unsupported', 'calibration-profile-unregistered')
    if not isinstance(snapshot, dict):
        return reject('malformed', 'invalid-execution-snapshot')
    if set(snapshot) != {'binding','phase','observed_at','values'}:
        return reject('malformed', 'invalid-execution-snapshot')
    try:
        binding = ExecutionBinding(**snapshot['binding'])
    except (TypeError, ValueError):
        return reject('unresolved', 'execution-binding-missing')
    if binding != expectation.binding:
        return reject('stale', 'execution-binding-mismatch')
    if (not is_cst_2022(binding.cst_build) or binding.scope != 'root' or expectation.config.mesh != 'Tet'
            or expectation.config.method not in _METHODS.values()):
        return reject('unsupported', 'calibration-context-unsupported')
    # Existing native database calibration covers Modes=1 only.
    if expectation.config.requested_modes != 1:
        return reject('unsupported', 'mode-count-profile-unverified')
    values = snapshot['values']
    if not isinstance(values, dict):
        return reject('malformed', 'invalid-execution-values')
    if any(key not in values or values[key] == '' for key in _KEYS):
        return reject('unresolved', 'execution-snapshot-missing', evidence='none')
    if set(values) != set(_KEYS) or any(not isinstance(value,str) or len(value)>128 for value in values.values()):
        return reject('malformed', 'invalid-execution-values')
    if snapshot['phase'] != 'post-attempt':
        return reject('unresolved', 'execution-phase-unverified')
    try:
        observed_at = _time(snapshot['observed_at'])
    except (ValueError, TypeError):
        return reject('malformed', 'invalid-observation-time')
    if not _time(expectation.attempt_started_at) <= observed_at <= _time(expectation.attempt_finished_at):
        return reject('stale', 'observation-outside-attempt')
    if values['SolverTypeTet'] not in _METHODS:
        return reject('unsupported', 'unknown-method-enum')
    if values['MeshType'] not in _MESHES:
        return reject('unsupported', 'unknown-mesh-enum')
    if any(values[key] not in ('True','False') for key in ('FrequencyTargetActive','AdaptionActiveTet')):
        return reject('malformed', 'invalid-native-boolean')
    if values['Modes'] != '1':
        return reject('unsupported', 'mode-count-profile-unverified')
    try:
        target = _decimal(values['FrequencyTargetValue'])
    except ValueError:
        return reject('malformed', 'invalid-native-number')
    if target < 0 or _g6(target) != target:
        return reject('malformed', 'native-number-format-invalid')
    expected = expectation.config
    observed = {'method':_METHODS[values['SolverTypeTet']], 'mesh':_MESHES[values['MeshType']],
                'target_enabled':values['FrequencyTargetActive']=='True',
                'target_value':values['FrequencyTargetValue'],
                'adaptation_enabled':values['AdaptionActiveTet']=='True', 'requested_modes':1}
    comparisons, reasons = {}, []
    for name, key in [('method','SolverTypeTet'), ('mesh','MeshType'),
                      ('target_enabled','FrequencyTargetActive'), ('target_value','FrequencyTargetValue'),
                      ('adaptation_enabled','AdaptionActiveTet'), ('requested_modes','Modes')]:
        wanted = getattr(expected, name)
        match = target == _g6(_decimal(wanted)) if name == 'target_value' else wanted == observed[name]
        comparisons[name] = MappingProxyType(dict(expected=wanted, observed=observed[name], matches=match,
                                                  source_key='objdata\\EigenmodeParameter\\'+key))
        if not match:
            reasons.append(name.replace('_','-')+'-mismatch')
    if target != _decimal(expected.target_value):
        reasons.append('native-double-formatted')
    fields = {'execution.'+key:value for key,value in observed.items()}
    fields['result_success'] = expectation.result_success
    fields['execution.effective_lower_bound_mhz'] = observed['target_value'] if observed['target_enabled'] else None
    return SnapshotReport('execution-snapshot-mismatch' if any(not item['matches'] for item in comparisons.values())
                          else 'execution-snapshot-match', tuple(reasons), MappingProxyType(fields),
                          MappingProxyType(comparisons), MappingProxyType(dict(values)), binding,
                          snapshot['observed_at'], profile_id, target_expression=expectation.target_expression)


def read_snapshot_record(path, *, max_bytes=64*1024):
    """Strict bounded UTF-8 JSON envelope; never decodes private Model.db contents."""
    if type(max_bytes) is not int or not 1 <= max_bytes <= 1024*1024:
        raise ValueError('snapshot budget must be 1..1048576')
    path = Path(path).resolve(strict=True)
    before = _identity(path)
    with path.open('rb') as stream:
        raw = stream.read(max_bytes+1)
    if len(raw) > max_bytes:
        raise ValueError('snapshot-record-budget-exceeded')
    with path.open('rb') as stream:
        repeated = stream.read(max_bytes+1)
    if before != _identity(path) or raw != repeated:
        raise ValueError('snapshot-record-changed-during-read')

    def pairs(items):
        result = {}
        for key,value in items:
            if key in result:
                raise ValueError('duplicate snapshot key')
            result[key] = value
        return result

    def constant(value):
        raise ValueError('non-finite snapshot constant')

    def floating(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('non-finite snapshot number')
        return result

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)
    except RecursionError as exc:
        raise ValueError('snapshot nesting exceeds parser budget') from exc
    if not isinstance(value,dict):
        raise ValueError('snapshot object required')
    return value


def _hash_database(path, limit):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while True:
            chunk = stream.read(min(1024*1024, limit-size+1))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ValueError('database-budget-exceeded')
            digest.update(chunk)
    return digest.hexdigest()


def _identity(path):
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def verify_execution_artifact(expectation, snapshot, *, database_path, max_bytes=64*1024*1024,
                              profile_id=PROFILE_ID):
    """Verify the actual closed database twice before adopting decoded fields.

    Path is an owner-resolved artifact, never an MCP arbitrary-path capability.
    Caller must ensure producer/attempt closure; this function provides no lock.
    """
    from dataclasses import replace

    report = validate_execution_snapshot(expectation, snapshot, profile_id=profile_id)
    if report.status not in ('execution-snapshot-match','execution-snapshot-mismatch'):
        return report
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError('positive database budget required')
    path = Path(database_path)
    try:
        before = _identity(path)
        if before[2] > max_bytes:
            raise ValueError('database-budget-exceeded')
        first = _hash_database(path,max_bytes)
        middle = _identity(path)
        second = _hash_database(path,max_bytes)
        after = _identity(path)
    except OSError:
        return SnapshotReport('unresolved',('database-artifact-unavailable',), profile_id=profile_id)
    except ValueError:
        return SnapshotReport('rejected',('database-budget-exceeded',), profile_id=profile_id)
    if before != middle or middle != after or first != second or first != expectation.binding.database_sha256:
        return SnapshotReport('stale',('database-artifact-changed',), profile_id=profile_id)
    return replace(report, database_verified=True)
