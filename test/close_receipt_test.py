"""L2 codec/generation gates only, not actual WinWrap execution."""
from dataclasses import replace
from pathlib import Path
import re

import pytest

from csttool.close_receipt import (CHOICES, FIELDS, MAX_SNAPSHOT_BYTES, CloseReceipt,
    declare_close_protocol, decode_close_receipt, encode_close_receipt,
    publish_close_receipt, read_close_protocol, read_close_receipt)
from csttool.close_receipt_contract import prepare_close_receipt_contract, verify_close_receipt_contract
from csttool.configuration import write_json_atomic
from csttool.runtime_protocol import (FileProtocol, ProtocolError, StopAcknowledge,
    encode_stop_ack, new_session_id, _encode, atomic_publish)
from csttool.session_closure import (CloseEvidence, evaluate_closure, read_stop_evidence,
    write_close_verification, read_recorded_exit)


DATA = Path(__file__).parent / 'data/close_receipt_v2'
SID = '22222222-2222-4222-8222-222222222222'
TASK = '11111111-1111-4111-8111-111111111111'


def fixture(name='saved'):
    return (DATA / (name + '.txt')).read_text(encoding='ascii')


def sample():
    return CloseReceipt(SID, TASK, 'stop-request', 'success', 'saved', 'committed',
                        'save', 'worker-input.cst', 8, 'none')


@pytest.mark.parametrize('name', ['saved', 'restored', 'failed', 'startup'])
def test_frozen_golden_vectors_round_trip_lf_crlf(name):
    text = fixture(name)
    receipt = decode_close_receipt(text)
    assert encode_close_receipt(receipt) == text
    assert decode_close_receipt(text.replace('\n', '\r\n')) == receipt


@pytest.mark.parametrize('damage', [
    lambda text: text.replace('CST_CLOSE_RECEIPT_V2', 'CST_STOP_ACK_V1'),
    lambda text: text + 'unexpected\nvalue\n',
    lambda text: text + 'session_id\n' + SID + '\n',
    lambda text: text.rsplit('error_code\n', 1)[0],
    lambda text: text.rstrip('\n').rsplit('\n', 1)[0],
    lambda text: text.replace('snapshot_bytes\n8', 'snapshot_bytes\n08'),
    lambda text: text.replace('snapshot_bytes\n8', 'snapshot_bytes\n+8'),
    lambda text: text.replace('snapshot_bytes\n8', 'snapshot_bytes\n8.0'),
    lambda text: text.replace('snapshot_bytes\n8', 'snapshot_bytes\n9223372036854775808'),
    lambda text: text.replace('worker-input.cst\n', '../worker-input.cst\n'),
    lambda text: text.replace('worker-input.cst\n', 'C:\\external.cst\n'),
    lambda text: text.replace('committed', '未知'),
    lambda text: text + 'x' * 4096,
])
def test_invalid_wire_is_rejected_without_retry(damage):
    with pytest.raises(ProtocolError):
        decode_close_receipt(damage(fixture()))


@pytest.mark.parametrize('changes', [
    {'session_id': 'not-a-uuid'}, {'last_task_id': 'none'}, {'task_outcome': 'not-started'},
    {'model_state': 'dirty'}, {'last_completed_phase': 'rebuild'}, {'snapshot_bytes': 0},
    {'snapshot_bytes': True}, {'snapshot_bytes': -1}, {'snapshot_bytes': 1.5},
    {'snapshot_ref': 'none'}, {'close_outcome': 'failed'}, {'error_code': 'CLOSE_SAVE_FAILED'},
    {'close_outcome': 'restored-saved'},
])
def test_field_relationships_are_strict(changes):
    with pytest.raises(ProtocolError):
        replace(sample(), **changes)


def test_int64_size_does_not_depend_on_vba_long_or_float():
    receipt = replace(sample(), snapshot_bytes=MAX_SNAPSHOT_BYTES)
    assert decode_close_receipt(encode_close_receipt(receipt)) == receipt


def setup_workspace(root, receipt=None):
    receipt = receipt or sample()
    declare_close_protocol(root, SID, 'v2')
    (root / receipt.snapshot_ref).write_bytes(b'snapshot')
    write_json_atomic(root / 'task-context.json', dict(session_id=SID, task_id=TASK))
    FileProtocol(root / 'protocol').request_stop(SID)
    return receipt


def test_immutable_publication_is_idempotent_and_preserves_conflict(tmp_path):
    receipt = setup_workspace(tmp_path)
    path = publish_close_receipt(tmp_path, receipt)
    before = path.read_bytes()
    assert publish_close_receipt(tmp_path, receipt) == path
    assert read_close_receipt(tmp_path, SID, expected_task_id=TASK) == receipt
    with pytest.raises(ProtocolError, match='conflict'):
        publish_close_receipt(tmp_path, replace(receipt, task_outcome='failure'))
    assert path.read_bytes() == before
    with pytest.raises(ProtocolError):
        read_close_receipt(tmp_path, new_session_id())
    with pytest.raises(ProtocolError, match='another'):
        read_close_receipt(tmp_path, SID, expected_task_id=new_session_id())


def test_incomplete_publication_is_not_removed_or_treated_as_success(tmp_path):
    receipt = setup_workspace(tmp_path)
    partial = tmp_path / 'protocol/close.receipt.tmp'
    partial.write_bytes(b'partial')
    with pytest.raises(ProtocolError, match='incomplete'):
        publish_close_receipt(tmp_path, receipt)
    assert partial.read_bytes() == b'partial'
    assert not partial.with_suffix('').exists()


def test_concurrent_conflicting_publishers_cannot_overwrite_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    receipt = setup_workspace(tmp_path)
    receipts = [replace(receipt, last_task_id=new_session_id()) for _ in range(8)]
    barrier = Barrier(len(receipts))
    def publish(item):
        barrier.wait(timeout=5)
        try:
            publish_close_receipt(tmp_path, item)
            return item
        except ProtocolError:
            return None
    with ThreadPoolExecutor(max_workers=len(receipts)) as pool:
        winners = [item for item in pool.map(publish, receipts) if item is not None]
    assert len(winners) == 1
    assert read_close_receipt(tmp_path, SID) == winners[0]


def test_declaration_is_static_and_never_silently_downgraded(tmp_path):
    assert read_close_protocol(tmp_path, SID) == 'v1'  # Old workspace.
    with pytest.raises(ProtocolError):
        read_close_protocol(tmp_path, SID, expected_version='v2')
    path = declare_close_protocol(tmp_path, SID, 'v2')
    before = path.read_bytes()
    assert declare_close_protocol(tmp_path, SID, 'v2') == path
    with pytest.raises(ProtocolError):
        declare_close_protocol(tmp_path, SID, 'v1')
    with pytest.raises(ProtocolError):
        declare_close_protocol(tmp_path, new_session_id(), 'v2')
    with pytest.raises(ProtocolError):
        declare_close_protocol(tmp_path, SID, 'v3')
    assert path.read_bytes() == before
    with pytest.raises(ProtocolError):
        read_close_receipt(tmp_path, SID)


@pytest.mark.parametrize('raw', ['{}', '[]', 'not json',
    '{"schema_version":1,"session_id":"' + SID + '","close_protocol":"v1","close_protocol":"v2"}',
    '{"schema_version":true,"session_id":"' + SID + '","close_protocol":"v2"}'])
def test_corrupt_declaration_is_not_legacy_v1(tmp_path, raw):
    (tmp_path / 'close-protocol.json').write_text(raw, encoding='ascii')
    with pytest.raises(ProtocolError):
        read_close_protocol(tmp_path, SID)
    with pytest.raises(ProtocolError):
        declare_close_protocol(tmp_path, SID, 'v2')


def test_undeclared_or_v1_conflicting_v2_receipt_is_rejected(tmp_path):
    output = tmp_path / 'protocol/close.receipt'
    output.parent.mkdir()
    output.write_text(fixture(), encoding='ascii')
    with pytest.raises(ProtocolError):
        read_close_protocol(tmp_path, SID)
    declare_close_protocol(tmp_path, SID, 'v1')
    with pytest.raises(ProtocolError):
        read_close_protocol(tmp_path, SID)


@pytest.mark.parametrize('damage', ['missing', 'corrupt', 'wrong-task', 'snapshot', 'context'])
def test_v1_stop_ack_and_exit_zero_cannot_bypass_v2(tmp_path, damage):
    receipt = setup_workspace(tmp_path)
    output = tmp_path / 'protocol/close.receipt'
    if damage != 'missing':
        publish_close_receipt(tmp_path, receipt)
    if damage == 'corrupt':
        output.write_text('bad', encoding='ascii')
    elif damage == 'wrong-task':
        write_json_atomic(tmp_path / 'task-context.json', dict(session_id=SID, task_id=new_session_id()))
    elif damage == 'snapshot':
        (tmp_path / receipt.snapshot_ref).write_bytes(b'changed size')
    elif damage == 'context':
        write_json_atomic(tmp_path / 'task-context.json', dict(session_id=SID, task_id=None))
    (tmp_path / 'protocol/stop.ack').write_text(encode_stop_ack(StopAcknowledge(SID)), encoding='ascii')
    ack, recovered, error = read_stop_evidence(tmp_path, SID)
    assert ack == 'valid' and error.startswith('close-receipt-pending' if damage == 'missing' else 'close-protocol-invalid')
    assert evaluate_closure(CloseEvidence(SID, False, 0, ack, recovered, protocol_error=error)).needs_recovery


def test_valid_v2_never_turns_exit_one_into_success(tmp_path):
    receipt = setup_workspace(tmp_path)
    publish_close_receipt(tmp_path, receipt)
    (tmp_path / 'protocol/stop.ack').write_text(encode_stop_ack(StopAcknowledge(SID)), encoding='ascii')
    ack, recovered, error = read_stop_evidence(tmp_path, SID)
    assert error is None
    assessment = evaluate_closure(CloseEvidence(SID, False, 1, ack, recovered, protocol_error=error))
    assert not assessment.standard_closed
    write_close_verification(tmp_path, 123, assessment)
    assert read_recorded_exit(tmp_path, SID, 123) == 1
    (tmp_path / receipt.snapshot_ref).write_bytes(b'changed!')  # Same size, changed hash.
    assert read_recorded_exit(tmp_path, SID, 123) is None


@pytest.mark.parametrize('code', [0, 4])
def test_v2_does_not_expand_legacy_exit_rules(tmp_path, code):
    receipt = setup_workspace(tmp_path, decode_close_receipt(fixture('restored')))
    publish_close_receipt(tmp_path, receipt)
    (tmp_path / 'protocol/stop.ack').write_text(encode_stop_ack(StopAcknowledge(SID)), encoding='ascii')
    ack, recovered, error = read_stop_evidence(tmp_path, SID)
    assert error is None and not recovered  # v2 does not invent the legacy exit-4 proof.
    result = evaluate_closure(CloseEvidence(SID, False, code, ack, recovered, protocol_error=error))
    assert result.standard_closed == (code == 0)


def test_declared_v2_missing_receipt_cannot_be_abandoned_as_v1(tmp_path):
    from csttool.project_session_recovery import discover_managed_sessions, recover_project_sessions
    root = tmp_path / 'temp/worker_0' / SID
    setup_workspace(root)
    (root / 'worker.pid').write_text('99999999', encoding='ascii')
    (root / 'worker.state').write_text('stopped', encoding='ascii')
    (root / 'protocol/stop.ack').write_text(encode_stop_ack(StopAcknowledge(SID)), encoding='ascii')
    assert discover_managed_sessions(tmp_path)[0].needs_recovery
    with pytest.raises(RuntimeError, match='close protocol'):
        recover_project_sessions(tmp_path, timeout_per_session=.1)
    assert not (root / 'recovery.json').exists()
    assert read_close_protocol(root, SID) == 'v2'


def test_failed_receipt_is_readable_but_not_a_successful_close(tmp_path):
    receipt = decode_close_receipt(fixture('failed'))
    declare_close_protocol(tmp_path, SID, 'v2')
    write_json_atomic(tmp_path / 'task-context.json', dict(session_id=SID, task_id=TASK))
    publish_close_receipt(tmp_path, receipt)
    assert read_close_receipt(tmp_path, SID) == receipt
    _, _, error = read_stop_evidence(tmp_path, SID)
    assert 'VBA declared close failure' in error


def test_explicit_v2_expectation_survives_missing_manifest_and_receipt(tmp_path):
    setup_workspace(tmp_path)
    (tmp_path / 'close-protocol.json').unlink()
    ack, saved, error = read_stop_evidence(tmp_path, SID, expected_close_protocol='v2')
    assert error.startswith('close-protocol-invalid')
    assert evaluate_closure(CloseEvidence(SID, False, 0, 'valid', saved, protocol_error=error)).needs_recovery


def test_generated_contract_has_both_libraries_and_no_solver(tmp_path):
    root = tmp_path / '含空格 路径'
    workspace = prepare_close_receipt_contract(root, sample(), snapshot=b'snapshot')
    macro = workspace.macro_path.read_text(encoding='ascii')
    assert macro.lower().count('sub main') == 1
    assert 'Private Const CSTC2_CONTRACT_PROTOCOL As String = "v2"' in macro
    assert 'Public Function CSTC2_ReadCloseReceipt' in macro
    assert 'Public Function CSTC2_WriteCloseReceipt' in macro
    assert 'ChrW(' in macro
    from csttool.vb_codec import quote_vb_string
    assert quote_vb_string('a"b') == 'a""b'
    assert 'EigenmodeSolver' not in macro and '\n    Save\n' not in macro and '\n    Quit\n' not in macro
    assert not workspace.receipt_path.exists()  # Preparing never executes VBA.
    assert not workspace.completion_path.exists()
    assert 'conflict was accepted' in macro and 'original receipt changed' in macro
    before = workspace.macro_path.read_bytes()
    with pytest.raises(ValueError, match='empty'):
        prepare_close_receipt_contract(root, sample(), snapshot=b'snapshot')
    assert workspace.macro_path.read_bytes() == before


def test_contract_requires_actual_outputs_and_final_marker(tmp_path):
    workspace = prepare_close_receipt_contract(tmp_path, sample(), snapshot=b'snapshot')
    with pytest.raises(ProtocolError):
        verify_close_receipt_contract(workspace, sample())
    publish_close_receipt(tmp_path, sample())  # Synthetic Python output, not a VBA execution claim.
    with pytest.raises(ProtocolError, match='completion'):
        verify_close_receipt_contract(workspace, sample())
    atomic_publish(workspace.completion_path, _encode('CST_CLOSE_CONTRACT_V1', (
        ('session_id', SID), ('status', 'passed'))))
    assert verify_close_receipt_contract(workspace, sample()) == sample()


def test_vba_field_order_choices_bounds_and_atomic_idempotence_match_python():
    source = Path('data/runtime_close_receipt_v2.vb').read_text(encoding='ascii')
    assert 'sub main' not in source.lower()
    fields = re.findall(r'keys\(\d\) = "([a-z_]+)"', source)
    assert fields == list(FIELDS)
    for choices in CHOICES.values():
        for choice in choices:
            assert choice in source
    assert 'SnapshotBytes As String' in source
    assert str(MAX_SNAPSHOT_BYTES) in source
    assert 'fieldCount <> 10' in source and 'FileLen(filePath) > 4096' in source
    writer = source.split('Public Function CSTC2_WriteCloseReceipt', 1)[1]
    assert writer.index('CSTC2_Validate') < writer.index('CSTP_AtomicWrite')
    assert 'CSTC2_ReadCloseReceipt' in writer and 'CSTC2_Same' in writer
    assert 'Kill ' not in writer  # Preserve conflicting output and partial publication.
