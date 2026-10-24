"""Backfill adoption metadata from durable checkpoints; never import or solve."""
from pathlib import Path
from .configuration import read_json, write_json_atomic
from .result_reconciliation import file_hash
from .run_store import RunStore


def mark_adopted(receipt_path, store, task_id, *, checkpoint=None):
    receipt = read_json(receipt_path)
    if receipt.get('task_id') != task_id or receipt.get('status') != 'Success':
        raise ValueError('adoption receipt identity/status mismatch')
    if receipt.get('phase') not in {'received', 'acknowledged', 'algorithm_adopted'}:
        raise ValueError('invalid adoption receipt phase')
    store.ensure_adopted(task_id, checkpoint=checkpoint)
    if receipt['phase'] != 'algorithm_adopted':
        write_json_atomic(receipt_path, {**receipt, 'phase': 'algorithm_adopted'})


def confirmed_tasks(project):
    """Return only IDs already in standard results or HOM adopted/mode records."""
    from .project_recovery_state import validate_recovery_checkpoint
    validate_recovery_checkpoint(project)
    project = Path(project)
    confirmed = {}
    standard = project / 'save/standard_batch_checkpoint.json'
    if standard.exists():
        for result in read_json(standard)['results']:
            task = result.get('TaskID')
            if not task: continue  # Legacy results have no identity to backfill.
            if task in confirmed or result.get('TaskStatus') != 'Success':
                raise ValueError('duplicate or failed standard checkpoint result')
            confirmed[task] = (standard, [result], 'standard')
    hom = project / 'save/csv/hom_scan_checkpoint.json'
    if hom.exists():
        report = read_json(hom)['report']
        ids = report.get('adopted_task_ids', [])
        if len(set(ids)) != len(ids): raise ValueError('duplicate HOM adopted task identity')
        modes = report['modes']
        for task in set(ids) | {item['task_id'] for item in modes if item.get('task_id')}:
            if task in confirmed: raise ValueError('task adopted by conflicting checkpoints')
            confirmed[task] = (hom, [m for m in modes if m.get('task_id') == task], 'hom')
    return confirmed


def reconcile_checkpoint_adoptions(project):
    """Caller holds project ownership and has reconciled physical sessions first."""
    from .project_session_recovery import project_runtime_directory
    from .runtime_protocol import _validate_uuid
    project = Path(project).resolve()
    tasks = confirmed_tasks(project)
    if not tasks: return []
    receipts = {task: set() for task in tasks}
    for base, pattern in ((project / 'logs', '*/workers/*/*/received/*.json'),
                          (project_runtime_directory(project), 'worker_*/*/received/*.json')):
        for path in base.glob(pattern):
            if path.stem in receipts: receipts[path.stem].add(path.resolve())
    stores, plan = {}, []
    for task, (checkpoint, records, kind) in sorted(tasks.items()):
        _validate_uuid('checkpoint task_id', task)
        if kind == 'standard' and records[0].get('ReceiptPath'):
            receipts[task].add(Path(records[0]['ReceiptPath']).resolve())
        if len(receipts[task]) != 1:
            raise ValueError('missing or ambiguous confirmed receipt: ' + task)
        path = next(iter(receipts[task]))
        receipt = read_json(path)
        _validate_uuid('receipt session_id', receipt.get('session_id'))
        if (receipt.get('task_id') != task or receipt.get('status') != 'Success'
                or receipt.get('phase') not in {'received', 'acknowledged', 'algorithm_adopted'}
                or Path(receipt['workspace']).name != receipt['session_id']):
            raise ValueError('checkpoint/receipt identity or status mismatch')
        snapshot = Path(receipt['snapshot'])
        if not snapshot.is_file() or file_hash(snapshot) != receipt.get('snapshot_sha256'):
            raise ValueError('confirmed checkpoint snapshot missing or changed')
        for record in records:
            if kind == 'standard':
                if (record.get('RunName') != receipt.get('job')
                        or record.get('RunParameters') != receipt.get('parameters')
                        or record.get('PostProcessResult') != receipt.get('postprocess')
                        or Path(record['ProjectSnapshot']).resolve() != snapshot.resolve()):
                    raise ValueError('standard checkpoint result differs from receipt')
            elif ((record.get('project_snapshot') and (project / record['project_snapshot']).resolve() != snapshot.resolve())
                  or (record.get('task_name') and record['task_name'] != receipt.get('job'))):
                raise ValueError('HOM checkpoint result differs from receipt')
        directories = {p.parents[2].resolve() for p in (project / 'logs').glob('*/tasks/' + task + '/attempt.json')}
        for ancestor in path.parents:
            if (ancestor / 'run.json').is_file():
                directories.add(ancestor.resolve()); break
            if ancestor == project: break
        if not directories: raise ValueError('confirmed task has no owned RunStore')
        for directory in directories:
            manifest = read_json(directory / 'run.json')
            if manifest.get('schema_version') != 1 or Path(manifest['project']).resolve() != project:
                raise ValueError('RunStore project identity mismatch')
            if directory not in stores: stores[directory] = RunStore(project, directory)
        plan.append((task, path, checkpoint, directories))
    # Validate every task before modifying any adoption metadata.
    proofs = {checkpoint: {'path': str(checkpoint.resolve()), 'sha256': file_hash(checkpoint)}
              for checkpoint in {item[2] for item in plan}}
    for task, path, checkpoint, directories in plan:
        proof = proofs[checkpoint]
        for directory in sorted(directories):
            mark_adopted(path, stores[directory], task, checkpoint=proof)
    return [item[0] for item in plan]
