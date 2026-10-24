"""Reuse received HOM results only after explicit session recovery."""
import hashlib
import json
from pathlib import Path


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def execution_fingerprint(project, postprocess):
    return hashlib.sha256((file_hash(project) + json.dumps(postprocess, sort_keys=True)).encode()).hexdigest()


def reconcile_archive_receipt(context, receipt_path, receipt):
    """Rebind only a proven completed archive; never search arbitrary CST files."""
    from .configuration import read_json, write_json_atomic
    snapshot = Path(receipt['snapshot'])
    expected = receipt.get('snapshot_sha256')
    if snapshot.is_file():
        if file_hash(snapshot) != expected:
            raise ValueError('received snapshot changed; preserve evidence, do not replay Solver')
        return
    original = Path(context['result_root']).resolve()
    task_id = context['task_id']
    if original.name != task_id or snapshot.resolve() != original / 'project.cst':
        raise ValueError('received snapshot is missing outside the known archive transition')
    indexes = list(original.parent.glob('*__' + task_id + '/task_result.json'))
    if len(indexes) != 1:
        raise ValueError('missing or ambiguous task archive index; do not replay Solver')
    index_path = indexes[0]
    index = read_json(index_path)
    name = index.get('projectSnapshot')
    if (index.get('schemaVersion') != 1 or index.get('taskId') != task_id
            or index.get('sessionId') != context['session_id']
            or index.get('taskName') != context['job']
            or index.get('postprocess') != receipt.get('postprocess')
            or not isinstance(name, str) or Path(name).name != name or Path(name).suffix.lower() != '.cst'
            or index_path.parent.resolve().parent != original.parent):
        raise ValueError('task archive index identity/path mismatch')
    relocated = index_path.parent / name
    if (relocated.resolve().parent != index_path.parent.resolve() or not relocated.is_file()
            or file_hash(relocated) != expected):
        raise ValueError('archived snapshot hash/path mismatch')
    write_json_atomic(receipt_path, {**receipt, 'snapshot': str(relocated.resolve()),
        'result_directory': str(index_path.parent.resolve()), 'archive_reconciled_from': str(snapshot)})


def recover_completed_result(session_root):
    """Import a published completion BEFORE recovery can ACK/clean protocol files.

    Old sessions without task-context remain legacy recovery; no result is invented.
    New sessions fail closed on corrupt or incomplete acceptance evidence.
    """
    from .configuration import read_json, write_json_atomic
    from .runtime_protocol import decode_completion, CompletionStatus
    from .postprocess_cst import CstPostProcessor
    root = Path(session_root)
    context_path = root / 'task-context.json'
    completion_path = root / 'protocol/current.completion'
    if not context_path.exists():
        return None
    context = read_json(context_path)
    completion = (decode_completion(completion_path.read_text(encoding='utf-8'))
                  if completion_path.exists() else None)
    if completion is not None and (completion.task_id != context['task_id'] or completion.session_id != context['session_id']):
        raise ValueError('recovery task/completion identity mismatch')
    receipt_path = Path(context.get('receipt_path', root / 'received' / (context['task_id'] + '.json')))
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        if receipt.get('task_id') != context['task_id'] or receipt.get('session_id') != context['session_id']:
            raise ValueError('recovery received receipt identity mismatch')
        if receipt.get('status') == 'Success':
            reconcile_archive_receipt(context, receipt_path, receipt)
        return receipt_path
    if completion is None or completion.status is not CompletionStatus.SUCCESS:
        return None
    result_root = Path(context['result_root'])
    snapshot = result_root / 'project.cst'
    if not snapshot.is_file() or not snapshot.stat().st_size:
        raise ValueError('completed result has no usable CST snapshot; do not replay blindly')
    processor = CstPostProcessor()
    processor.configure(context['postprocess'])
    processor.set_result_directory(result_root)
    processor.set_cst_run_result_directory(result_root / 'project')
    values = processor.read_all_results()
    fields = [item for item in values if isinstance(item.get('value'), dict)
              and item['value'].get('kind') == 'field-artifact']
    write_json_atomic(receipt_path, {
        'schema_version': 1, 'phase': 'received', 'task_id': completion.task_id,
        'session_id': completion.session_id, 'job': context['job'],
        'parameters': context['parameters'], 'status': 'Success', 'failure': None,
        'postprocess': [item for item in values if item not in fields], 'field_artifacts': fields,
        'snapshot': str(snapshot.resolve()), 'snapshot_sha256': file_hash(snapshot),
        'workspace': str(root.resolve()), 'execution_fingerprint': context['execution_fingerprint'],
        'recovered_from_completion': True,
        'optional_analysis_pending': bool(context.get('optional_analysis_pending', False)),
    })
    return receipt_path


def find_received_result(roots, job, parameters, fingerprint):
    candidates = []
    for root in roots:
        for path in Path(root).glob('**/received/*.json'):
            receipt = json.loads(path.read_text(encoding='utf-8'))
            if (receipt.get('phase') not in ('received', 'acknowledged')
                    or receipt.get('status') != 'Success' or receipt.get('job') != job
                    or receipt.get('parameters') != dict(parameters)
                    or receipt.get('execution_fingerprint') != fingerprint):
                continue
            recovery = Path(receipt['workspace']) / 'recovery.json'
            supplementary = recovery.with_name('recovery-l1.json')
            if supplementary.exists():
                recovery = supplementary
            if not recovery.exists():
                continue
            recovered = json.loads(recovery.read_text(encoding='utf-8'))
            if recovery == supplementary and (recovered.get('schema_version') != 1
                    or recovered.get('session_id') != Path(receipt['workspace']).name):
                raise ValueError('supplementary recovery identity mismatch')
            if recovered.get('disposition') not in ('standard-stop', 'abandoned-dead'):
                continue
            snapshot = Path(receipt['snapshot'])
            if not snapshot.exists():
                # Older recovery decisions may predate archive-path repair.
                context_path = Path(receipt['workspace']) / 'task-context.json'
                if context_path.is_file():
                    context = json.loads(context_path.read_text(encoding='utf-8'))
                    if (context.get('task_id') != receipt.get('task_id')
                            or context.get('session_id') != receipt.get('session_id')):
                        raise ValueError('received archive context identity mismatch')
                    reconcile_archive_receipt(context, path, receipt)
                    receipt = json.loads(path.read_text(encoding='utf-8'))
                    snapshot = Path(receipt['snapshot'])
            if not snapshot.is_file() or file_hash(snapshot) != receipt.get('snapshot_sha256'):
                raise ValueError('received snapshot is missing or changed')
            if not isinstance(receipt.get('postprocess'), list):
                raise ValueError('received postprocess is unavailable')
            candidates.append((path, receipt))
    if len(candidates) > 1:
        raise ValueError('multiple received attempts require explicit reconciliation')
    return candidates[0] if candidates else None
