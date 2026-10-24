import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from csttool.configuration import read_json, write_json_atomic
from csttool.run_store import RunStore
from csttool.runtime_protocol import new_session_id
from csttool.result_reconciliation import file_hash, find_received_result
from csttool.checkpoint_adoption import reconcile_checkpoint_adoptions


def fixture(project):
    task, sid = new_session_id(), new_session_id()
    store = RunStore(project, project / 'logs/run')
    workspace = store.directory / 'workers/0' / sid
    receipt_path = workspace / 'received' / (task + '.json')
    snapshot = project / 'result/project.cst'
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(b'confirmed synthetic model, not CST acceptance')
    receipt = dict(schema_version=1, task_id=task, session_id=sid, workspace=str(workspace),
        job='job', parameters={'R': 229}, status='Success', phase='acknowledged',
        snapshot=str(snapshot), snapshot_sha256=file_hash(snapshot), postprocess=[], execution_fingerprint='fp')
    write_json_atomic(receipt_path, receipt)
    store.event(task, 'submitted'); store.event(task, 'received'); store.event(task, 'acknowledged')
    result = dict(TaskID=task, TaskStatus='Success', RunName='job', RunParameters={'R': 229},
                  PostProcessResult=[], ProjectSnapshot=str(snapshot), ReceiptPath=str(receipt_path))
    checkpoint = project / 'save/standard_batch_checkpoint.json'
    write_json_atomic(checkpoint, dict(schema_version=1, task_signature='signature', results=[result], pending_index=1))
    return task, store, receipt_path, snapshot, checkpoint


def adoptions(store, task):
    return [json.loads(line) for line in (store.directory / 'events.jsonl').read_text().splitlines()
            if json.loads(line).get('event') == 'algorithm_adopted' and json.loads(line).get('task_id') == task]


@pytest.mark.parametrize('state', ['missing', 'receipt-only', 'index-only', 'journal-only', 'done', 'tail'])
def test_checkpoint_marker_repair_is_idempotent_and_never_reimports(tmp_path, state):
    task, store, receipt_path, snapshot, checkpoint = fixture(tmp_path)
    attempt = store.directory / 'tasks' / task / 'attempt.json'
    if state in {'receipt-only', 'done'}:
        write_json_atomic(receipt_path, dict(read_json(receipt_path), phase='algorithm_adopted'))
    if state in {'index-only', 'done'}:
        write_json_atomic(attempt, dict(read_json(attempt), event='algorithm_adopted'))
    if state in {'journal-only', 'done'}:
        with (store.directory / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(task_id=task, event='algorithm_adopted', utc='original')) + '\n')
    if state == 'tail':
        with (store.directory / 'events.jsonl').open('ab') as stream: stream.write(b'{"partial":')
    store._state.adopted = None  # Direct disk edits emulate a fresh process after exit.
    write_json_atomic(receipt_path.parents[1] / 'recovery.json', dict(schema_version=1,
        session_id=read_json(receipt_path)['session_id'], worker_id='0', disposition='standard-stop'))
    if state not in {'receipt-only', 'done'}:
        assert find_received_result([tmp_path], 'job', {'R': 229}, 'fp') is not None
    before = checkpoint.read_bytes(), snapshot.read_bytes()
    assert reconcile_checkpoint_adoptions(tmp_path) == [task]
    after = receipt_path.read_bytes(), attempt.read_bytes(), (store.directory / 'events.jsonl').read_bytes()
    reconcile_checkpoint_adoptions(tmp_path)
    assert after == (receipt_path.read_bytes(), attempt.read_bytes(), (store.directory / 'events.jsonl').read_bytes())
    assert before == (checkpoint.read_bytes(), snapshot.read_bytes())
    assert read_json(receipt_path)['phase'] == read_json(attempt)['event'] == 'algorithm_adopted'
    assert len(adoptions(store, task)) == 1
    if state == 'tail': assert list(store.directory.glob('events.truncated-*.bin'))[0].read_bytes() == b'{"partial":'
    assert find_received_result([tmp_path], 'job', {'R': 229}, 'fp') is None


@pytest.mark.parametrize('fault', ['snapshot', 'identity', 'job', 'ambiguous', 'project', 'duplicate-checkpoint'])
def test_bad_checkpoint_evidence_does_not_change_markers(tmp_path, fault):
    task, store, receipt_path, snapshot, checkpoint = fixture(tmp_path)
    if fault == 'snapshot': snapshot.write_bytes(b'changed')
    if fault == 'identity': write_json_atomic(receipt_path, dict(read_json(receipt_path), task_id=new_session_id()))
    if fault == 'job':
        cp = read_json(checkpoint); cp['results'][0]['RunName'] = 'other'; write_json_atomic(checkpoint, cp)
    if fault == 'project': write_json_atomic(store.directory / 'run.json', dict(schema_version=1, project='other'))
    if fault == 'ambiguous': write_json_atomic(tmp_path / 'logs/other/workers/0' / new_session_id() / 'received' / (task + '.json'), read_json(receipt_path))
    if fault == 'duplicate-checkpoint':
        cp = read_json(checkpoint); cp['results'] *= 2; cp['pending_index'] = 2; write_json_atomic(checkpoint, cp)
    before = receipt_path.read_bytes(), (store.directory / 'events.jsonl').read_bytes(), checkpoint.read_bytes()
    with pytest.raises((ValueError, KeyError, FileNotFoundError)): reconcile_checkpoint_adoptions(tmp_path)
    assert before == (receipt_path.read_bytes(), (store.directory / 'events.jsonl').read_bytes(), checkpoint.read_bytes())


def test_append_or_index_interruption_retries_without_second_adoption(tmp_path, monkeypatch):
    task, store, receipt_path, snapshot, checkpoint = fixture(tmp_path)
    import csttool.run_store as module
    original = module.write_json_atomic
    def fail(path, value):
        if Path(path).name == 'attempt.json' and value.get('event') == 'algorithm_adopted':
            raise OSError('injected index write interruption')
        original(path, value)
    monkeypatch.setattr(module, 'write_json_atomic', fail)
    with pytest.raises(OSError): reconcile_checkpoint_adoptions(tmp_path)
    assert read_json(receipt_path)['phase'] == 'acknowledged'
    assert len(adoptions(store, task)) == 1
    monkeypatch.setattr(module, 'write_json_atomic', original)
    reconcile_checkpoint_adoptions(tmp_path)
    assert len(adoptions(store, task)) == 1
    # A failed ordinary append must not leave a stale shared adoption cache.
    project = tmp_path / 'generic-append'
    task2, store2, receipt2, _, _ = fixture(project)
    original_open = Path.open
    class FailingAppend:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def write(self, value):
            self.stream.write('{"partial":'); self.stream.flush()
            raise OSError('injected partial event append')
    def opened(path, mode='r', *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        return FailingAppend(stream) if path == store2.directory / 'events.jsonl' and mode == 'a' else stream
    monkeypatch.setattr(Path, 'open', opened)
    with pytest.raises(OSError): store2.event(task2, 'ack_pending')
    monkeypatch.setattr(Path, 'open', original_open)
    reconcile_checkpoint_adoptions(project)
    assert len(adoptions(store2, task2)) == 1
    assert read_json(receipt2)['phase'] == 'algorithm_adopted'
    assert list(store2.directory.glob('events.truncated-*.bin'))[0].read_bytes() == b'{"partial":'


def test_shared_runstore_instances_serialize_adoption(tmp_path):
    task, store, receipt_path, snapshot, checkpoint = fixture(tmp_path)
    stores = [RunStore(tmp_path, store.directory) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda item: item.ensure_adopted(task), stores))
    assert len(adoptions(store, task)) == 1


@pytest.mark.parametrize('empty', [False, True])
@pytest.mark.parametrize('relative', [False, True])
def test_hom_checkpoint_including_empty_completed_task_is_authority(tmp_path, empty, relative):
    task, store, receipt_path, snapshot, checkpoint = fixture(tmp_path)
    checkpoint.unlink()
    from csttool.hom_scan import ScanCheckpointStore, ScanPolicy, ScanReport, ScanInterval, ModeResult
    report = ScanReport(completed=[ScanInterval(400, 800)], adopted_task_ids=[task])
    if not empty:
        path = str(snapshot.relative_to(tmp_path)) if relative else str(snapshot)
        report.modes = [ModeResult(i, frequency, {}, path, 'job', task)
                        for i, frequency in ((1, 500), (2, 600))]
    hom = tmp_path / 'save/csv/hom_scan_checkpoint.json'
    ScanCheckpointStore(hom).save(ScanPolicy(400, 800, 800), {}, report, [], snapshot_path=snapshot)
    before = hom.read_bytes()
    reconcile_checkpoint_adoptions(tmp_path)
    assert hom.read_bytes() == before
    assert read_json(receipt_path)['phase'] == 'algorithm_adopted'


def test_without_checkpoint_nothing_is_adopted(tmp_path):
    task, store, receipt, snapshot, checkpoint = fixture(tmp_path)
    checkpoint.unlink()
    before = receipt.read_bytes(), (store.directory / 'events.jsonl').read_bytes()
    assert reconcile_checkpoint_adoptions(tmp_path) == []
    assert before == (receipt.read_bytes(), (store.directory / 'events.jsonl').read_bytes())


def test_hom_relative_snapshot_mismatch_still_blocks_before_markers(tmp_path):
    task, store, receipt, snapshot, checkpoint = fixture(tmp_path)
    checkpoint.unlink()
    from csttool.hom_scan import ScanCheckpointStore, ScanPolicy, ScanReport, ScanInterval, ModeResult
    report = ScanReport(completed=[ScanInterval(400, 800)], adopted_task_ids=[task],
                        modes=[ModeResult(1, 500, {}, 'result/other.cst', 'job', task)])
    hom = tmp_path / 'save/csv/hom_scan_checkpoint.json'
    ScanCheckpointStore(hom).save(ScanPolicy(400, 800, 800), {}, report, [], snapshot_path=snapshot)
    before = receipt.read_bytes(), (store.directory / 'events.jsonl').read_bytes(), hom.read_bytes()
    with pytest.raises(ValueError, match='HOM checkpoint result differs'):
        reconcile_checkpoint_adoptions(tmp_path)
    assert before == (receipt.read_bytes(), (store.directory / 'events.jsonl').read_bytes(), hom.read_bytes())


@pytest.mark.parametrize('kind', ['complete-tail', 'corrupt-middle', 'duplicate-event'])
def test_journal_repair_distinguishes_torn_tail_from_corruption(tmp_path, kind):
    task, store, receipt, snapshot, checkpoint = fixture(tmp_path)
    row = json.dumps(dict(task_id=task, event='algorithm_adopted', utc='prior')).encode()
    with (store.directory / 'events.jsonl').open('ab') as stream:
        stream.write(row if kind == 'complete-tail' else
                     b'broken\n' + row + b'\n' if kind == 'corrupt-middle' else row + b'\n' + row + b'\n')
    store._state.adopted = None
    if kind == 'complete-tail':
        reconcile_checkpoint_adoptions(tmp_path)
        assert len(adoptions(store, task)) == 1
    else:
        before = receipt.read_bytes(), (store.directory / 'events.jsonl').read_bytes()
        with pytest.raises(ValueError): reconcile_checkpoint_adoptions(tmp_path)
        assert before == (receipt.read_bytes(), (store.directory / 'events.jsonl').read_bytes())


def test_related_run_indexes_receive_one_marker_each_not_new_tasks(tmp_path):
    task, store, receipt, snapshot, checkpoint = fixture(tmp_path)
    related = RunStore(tmp_path, tmp_path / 'logs/replayed')
    related.event(task, 'submitted'); related.event(task, 'ack_pending')
    reconcile_checkpoint_adoptions(tmp_path)
    reconcile_checkpoint_adoptions(tmp_path)
    assert len(adoptions(store, task)) == len(adoptions(related, task)) == 1
    assert read_json(related.directory / 'tasks' / task / 'attempt.json')['event'] == 'algorithm_adopted'


def test_all_evidence_is_validated_before_first_marker_changes(tmp_path):
    task, store, receipt, snapshot, checkpoint = fixture(tmp_path)
    first = read_json(checkpoint)['results'][0]
    other, _, other_receipt, _, _ = fixture(tmp_path)
    cp = read_json(checkpoint); cp['results'].insert(0, first); cp['pending_index'] = 2
    write_json_atomic(checkpoint, cp)
    write_json_atomic(other_receipt, dict(read_json(other_receipt), job='wrong'))
    before = receipt.read_bytes(), other_receipt.read_bytes(), (store.directory / 'events.jsonl').read_bytes()
    with pytest.raises(ValueError): reconcile_checkpoint_adoptions(tmp_path)
    assert before == (receipt.read_bytes(), other_receipt.read_bytes(), (store.directory / 'events.jsonl').read_bytes())
