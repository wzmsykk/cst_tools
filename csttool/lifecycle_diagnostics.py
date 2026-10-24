"""Read-only lifecycle projections. Never ACK, adopt, rebuild, or clear a gate."""
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone


def project_lifecycle(project):
    from .project_session_recovery import discover_managed_sessions
    return lifecycle_facts(discover_managed_sessions(project))


def lifecycle_facts(records):
    sessions = []
    for record in records:
        assessment = record.closure
        sessions.append(dict(asdict(assessment), worker_id=record.worker_id,
                             workspace=str(record.root),
                             evidence_path=str(record.root / 'close-verification.json'),
                             receipt_path=str(record.root / 'protocol/close.receipt')))
        sessions[-1]['result_observation'] = result_observation(record.root, record.session_id)
    # Physical closure is independent of pending Completion reconciliation.
    safety = ('unknown' if any(s['process_state'] == 'unknown' for s in sessions)
              else 'running' if any(s['process_state'] == 'running' for s in sessions)
              else 'confirmed-closed' if all(s['standard_closed'] for s in sessions)
              else 'exited-unverified')
    selected = sorted(sessions, key=lambda s: not s['needs_recovery'])[:100]
    return dict(schema_version=1, observed_at=datetime.now(timezone.utc).isoformat(),
                session_safety=safety, session_count=len(sessions),
                recovery_required=any(s['needs_recovery'] for s in sessions),
                omitted_sessions=max(0, len(sessions) - len(selected)),
                sessions=selected, source='csttool.session_closure.evaluate_closure')


def result_observation(root, session_id):
    """Display persisted Python receipt phase, never substitute for artifact validation."""
    from .configuration import read_json
    context_path = Path(root) / 'task-context.json'
    try:
        if not context_path.exists():
            return dict(state='unknown')
        context = read_json(context_path)
        if context['session_id'] != session_id:
            raise ValueError('task context session mismatch')
        path = Path(context.get('receipt_path', Path(root) / 'received' / (context['task_id'] + '.json')))
        if not path.exists():
            return dict(state='not-received', task_id=context['task_id'])
        receipt = read_json(path)
        if receipt['session_id'] != session_id or receipt['task_id'] != context['task_id']:
            raise ValueError('result receipt identity mismatch')
        phase = receipt['phase']
        if phase not in {'received', 'acknowledged', 'algorithm_adopted'}:
            raise ValueError('unknown result receipt phase')
        return dict(state=phase, status=receipt.get('status', 'unknown'),
                    task_id=context['task_id'], receipt_path=str(path),
                    optional_analysis_pending=receipt.get('optional_analysis_pending', False),
                    validation='receipt-observation-only')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return dict(state='unknown', error=f'{type(exc).__name__}: {exc}')


def error_diagnostic(exc, phase):
    """Retain the actual cause chain and implementation locations across HTTP."""
    chain, seen = [], set()
    while exc is not None and id(exc) not in seen and len(chain) < 16:
        seen.add(id(exc))
        trace = exc.__traceback__
        locations = []
        while trace is not None:
            frame = trace.tb_frame
            locations.append(dict(path=frame.f_code.co_filename, line=trace.tb_lineno,
                                  function=frame.f_code.co_name))
            trace = trace.tb_next
        chain.append(dict(type=type(exc).__name__, message=str(exc), locations=locations[-16:]))
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return dict(schema_version=1, phase=phase, chain=chain)
