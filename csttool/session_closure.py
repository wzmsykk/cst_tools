"""Shared v1/v2 closure evidence; no signalling, solver calls or result adoption."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from .configuration import write_json_atomic
from .runtime_protocol import decode_stop_ack
from .close_receipt import read_close_protocol, read_close_receipt


def _validate_last_received_task(root, session_id, receipt, expected_task):
    """Dispatch metadata may be one task ahead when stop wins before read-task."""
    if receipt.last_task_id == expected_task:
        return
    from .runtime_protocol import Acknowledge, decode_ack
    latest_ack = root / 'protocol' / ('current.ack.' + expected_task + '.accepted')
    if latest_ack.exists():
        raise ValueError('close receipt predates an acknowledged current task')
    if receipt.last_task_id == 'none' and receipt.task_outcome in {'not-started', 'unknown'}:
        return  # No accepted task; the pending dispatch is NOT a completed solve.
    prior = root / 'protocol' / ('current.ack.' + receipt.last_task_id + '.accepted')
    if (not prior.is_file() or decode_ack(prior.read_text(encoding='ascii'))
            != Acknowledge(receipt.last_task_id, session_id)):
        raise ValueError('close receipt task is neither current nor verified previously acknowledged')


@dataclass(frozen=True, slots=True)
class CloseEvidence:
    session_id: str
    process_alive: bool | None
    exit_code: int | None = None
    stop_ack: str = 'missing'
    recovery_saved: bool = False
    abandoned: bool = False
    unresolved_completion: bool = False
    protocol_error: str | None = None
    task_outcome: str = 'unknown'
    result_state: str = 'unknown'
    model_state: str = 'unknown'
    stop_ack_required: bool = True
    unresolved_result: bool = False


@dataclass(frozen=True, slots=True)
class ClosureAssessment:
    session_id: str
    process_state: str
    exit_code: int | None
    exit_classification: str
    model_state: str
    task_outcome: str
    result_state: str
    disposition: str
    standard_closed: bool
    needs_recovery: bool
    missing_evidence: tuple[str, ...]


def evaluate_closure(evidence: CloseEvidence) -> ClosureAssessment:
    """Do not conflate task failure, saved model, and process termination."""
    process = 'exited' if evidence.process_alive is False else 'running' if evidence.process_alive is True else 'unknown'
    code = evidence.exit_code
    classification = ('not-observed' if code is None else 'zero' if code == 0
                      else 'recovered-4' if code == 4 and evidence.recovery_saved else 'abnormal')
    missing = []
    if process != 'exited':
        missing.append('process-exit-unconfirmed')
    if evidence.stop_ack_required and evidence.stop_ack != 'valid':
        missing.append('stop-ack-' + evidence.stop_ack)
    if code is None:
        missing.append('exit-code-unobserved')
    elif not accepted_exit_code(code, evidence.recovery_saved):
        missing.append('exit-code-not-accepted')
    if evidence.protocol_error:
        missing.append(evidence.protocol_error)
    closed = not missing
    abandoned = (process == 'exited' and evidence.abandoned and (
        not evidence.protocol_error or evidence.protocol_error.startswith('close-declared-failed:')))
    disposition = ('standard-stop' if closed else 'abandoned-dead' if abandoned
                   else 'still-running' if process == 'running' else 'unconfirmed')
    if evidence.unresolved_completion:
        missing.append('completion-not-reconciled')
    if evidence.unresolved_result:
        missing.append('received-result-not-reconciled')
    return ClosureAssessment(evidence.session_id, process, code, classification,
        'restored-saved' if evidence.recovery_saved else evidence.model_state,
        evidence.task_outcome, evidence.result_state, disposition, closed,
        not (closed or abandoned) or evidence.unresolved_completion or evidence.unresolved_result, tuple(missing))


def read_stop_evidence(root, session_id, *, project_path=None, expected_close_protocol=None):
    """Read without creating protocol directories or trusting file existence."""
    root = Path(root)
    ack_path = root / 'protocol/stop.ack'
    try:
        ack = decode_stop_ack(ack_path.read_text(encoding='utf-8'))
        if ack.session_id != session_id:
            raise ValueError('stop acknowledge belongs to another worker session')
        ack_state, error = 'valid', None
    except FileNotFoundError:
        ack_state, error = 'missing', None
    except (OSError, UnicodeError, ValueError) as exc:
        ack_state, error = 'invalid', f'stop-ack-invalid: {type(exc).__name__}: {exc}'
    project = Path(project_path) if project_path else root / 'worker-input.cst'
    try:
        recovered = (Path(str(project) + '.recovery-saved').read_text(encoding='ascii').splitlines()
                     == ['CST_RECOVERY_SAVED_V1', session_id]
                     and Path(str(project) + '.recovered.cst').stat().st_size > 0
                     and Path(str(project) + '.recovered.cst').is_file())
    except (OSError, UnicodeError):
        recovered = False
    try:
        context_path = root / 'task-context.json'
        context = None
        if context_path.exists():
            context = json.loads(context_path.read_text(encoding='utf-8'))
            if not isinstance(context, dict):
                raise ValueError('invalid task context')
            declared_context_version = context.get('close_protocol')
            if expected_close_protocol is None:
                expected_close_protocol = declared_context_version
            elif declared_context_version is not None and expected_close_protocol != declared_context_version:
                raise ValueError('task context close protocol mismatch')
        if read_close_protocol(root, session_id, expected_version=expected_close_protocol) == 'v2':
            expected_task = 'none'
            if context is not None:
                if context.get('session_id') != session_id:
                    raise ValueError('task context identity mismatch')
                expected_task = context['task_id']
                from .runtime_protocol import _validate_uuid
                _validate_uuid('task context task_id', expected_task)
            if not (root / 'protocol/close.receipt').exists():
                return ack_state, recovered, error or 'close-receipt-pending'
            receipt = read_close_receipt(root, session_id)
            _validate_last_received_task(root, session_id, receipt, expected_task)
            if receipt.close_origin == 'stop-request':
                from .runtime_protocol import decode_stop_request
                request = decode_stop_request((root / 'protocol/stop.request').read_text(encoding='utf-8'))
                if request.session_id != session_id:
                    raise ValueError('close receipt stop request identity mismatch')
            if receipt.close_outcome == 'failed':
                return ack_state, recovered, error or ('close-declared-failed: VBA declared close failure: ' + receipt.error_code)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        # Never let an existing v1 StopAck/exit-code pair bypass a v2 declaration.
        error = 'close-protocol-invalid: ' + str(exc)
    return ack_state, recovered, error


def collect_close_evidence(root, session_id, process_alive, exit_code=None, *,
                           project_path=None, expected_close_protocol=None,
                           abandoned=False, unresolved_completion=False,
                           unresolved_result=False, result_state='unknown'):
    """Keep actual v2 task/model facts even when process exit is unacceptable."""
    ack, saved, error = read_stop_evidence(root, session_id, project_path=project_path,
                                          expected_close_protocol=expected_close_protocol)
    task_outcome, model_state, ack_required = 'unknown', 'unknown', True
    try:
        if read_close_protocol(root, session_id, expected_version=expected_close_protocol) == 'v2':
            receipt = read_close_receipt(root, session_id)
            task_outcome, model_state = receipt.task_outcome, receipt.model_state
            ack_required = receipt.close_origin == 'stop-request'
    except (OSError, UnicodeError, ValueError, TypeError):
        pass  # The strict reader above retains the error; never treat it as v1.
    return CloseEvidence(session_id, process_alive, exit_code, ack, saved, abandoned,
        unresolved_completion, error, task_outcome=task_outcome,
        model_state=model_state, stop_ack_required=ack_required,
        unresolved_result=unresolved_result, result_state=result_state)


def accepted_exit_code(code, recovered):
    """Legacy exception only; exit 1 is deliberately NOT accepted."""
    return code == 0 or (code == 4 and recovered)


def _file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _proof_hashes(root, recovered):
    paths = ['protocol/stop.ack']
    paths += ['close-protocol.json', 'protocol/close.receipt']
    if (root / 'protocol/close.receipt').is_file():
        paths += ['worker-input.cst', 'worker-input.cst.recovered.cst', 'worker-input.cst.closed.cst']
    if recovered:
        paths += ['worker-input.cst.recovery-saved', 'worker-input.cst.recovered.cst']
    return {name: _file_hash(root / name) for name in dict.fromkeys(paths) if (root / name).is_file()}


def write_close_verification(root, pid, assessment):
    """Persist Python's observed exit; does NOT forge a VBA receipt."""
    root = Path(root)
    document = dict(schema_version=1, session_id=assessment.session_id, process_id=pid,
                    assessment=asdict(assessment),
                    evidence_sha256=_proof_hashes(root, assessment.model_state == 'restored-saved'))
    write_json_atomic(root / 'close-verification.json', document)


def read_recorded_exit(root, session_id, pid):
    """Unknown is different from exit 0; reject stale or changed saved proofs."""
    root = Path(root)
    try:
        data = json.loads((root / 'close-verification.json').read_text(encoding='utf-8'))
        assessment = data['assessment']
        if (data['schema_version'] != 1 or data['session_id'] != session_id
                or data['process_id'] != pid or type(pid) is not int
                or assessment['session_id'] != session_id
                or assessment['process_state'] != 'exited'
                or type(assessment['exit_code']) is not int):
            return None
        # Fixed paths only; no arbitrary file paths from an untrusted record.
        hashes = _proof_hashes(root, assessment['model_state'] == 'restored-saved')
        if hashes != data['evidence_sha256']:
            return None
        return assessment['exit_code']
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return None
