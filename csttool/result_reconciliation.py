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
