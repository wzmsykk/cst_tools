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
    if not context_path.exists() or not completion_path.exists():
        return None
    context = read_json(context_path)
    completion = decode_completion(completion_path.read_text(encoding='utf-8'))
    if (completion.task_id != context['task_id'] or completion.session_id != context['session_id']):
        raise ValueError('recovery task/completion identity mismatch')
    receipt_path = Path(context.get('receipt_path', root / 'received' / (completion.task_id + '.json')))
    if receipt_path.exists():
        return receipt_path
    if completion.status is not CompletionStatus.SUCCESS:
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
            if not recovery.exists():
                continue
            recovered = json.loads(recovery.read_text(encoding='utf-8'))
            if recovered.get('disposition') not in ('standard-stop', 'abandoned-dead'):
                continue
            snapshot = Path(receipt['snapshot'])
            if not snapshot.is_file() or file_hash(snapshot) != receipt.get('snapshot_sha256'):
                raise ValueError('received snapshot is missing or changed')
            if not isinstance(receipt.get('postprocess'), list):
                raise ValueError('received postprocess is unavailable')
            candidates.append((path, receipt))
    if len(candidates) > 1:
        raise ValueError('multiple received attempts require explicit reconciliation')
    return candidates[0] if candidates else None
