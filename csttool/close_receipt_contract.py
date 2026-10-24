"""Prepare an isolated WWB close-receipt contract; never launch CST here."""
from dataclasses import dataclass
from pathlib import Path

from install_compat import resource_path
from .close_receipt import CloseReceipt, declare_close_protocol, encode_close_receipt, read_close_receipt
from .runtime_protocol import ProtocolError, _decode, atomic_publish
from .vb_codec import quote_vb_string
from .configuration import write_json_atomic


@dataclass(frozen=True, slots=True)
class CloseReceiptWorkspace:
    root: Path
    macro_path: Path
    receipt_path: Path
    completion_path: Path


def prepare_close_receipt_contract(root, receipt: CloseReceipt, *, snapshot=b''):
    root = Path(root).resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError('close receipt contract requires a new/empty directory')
    if len(snapshot) != receipt.snapshot_bytes:
        raise ValueError('contract snapshot bytes do not match receipt')
    root.mkdir(parents=True, exist_ok=True)
    declare_close_protocol(root, receipt.session_id, 'v2')
    fixture = root / 'input.receipt'
    output = root / 'protocol/close.receipt'
    completed = root / 'contract-passed.txt'
    atomic_publish(fixture, encode_close_receipt(receipt))
    output.parent.mkdir(exist_ok=True)
    if receipt.snapshot_ref != 'none':
        (root / receipt.snapshot_ref).write_bytes(snapshot)
    if receipt.last_task_id != 'none':
        write_json_atomic(root / 'task-context.json', dict(session_id=receipt.session_id,
                                                         task_id=receipt.last_task_id))
    libraries = '\n'.join(Path(resource_path(name)).read_text(encoding='utf-8') for name in (
        'data/runtime_protocol_v1.vb', 'data/runtime_close_receipt_v2.vb'))
    main = f'''
Sub Main
    Dim receipt As CSTC2_CloseReceipt
    Dim storedReceipt As CSTC2_CloseReceipt
    Dim message As String
    Dim originalOrigin As String
    Dim keys(0 To 1) As String, values(0 To 1) As String
    If Not CSTC2_ReadCloseReceipt("{quote_vb_string(fixture)}", "{receipt.session_id}", "{receipt.last_task_id}", receipt, message) Then Err.Raise vbObjectError + 2501, "close contract", message
    If Not CSTC2_WriteCloseReceipt("{quote_vb_string(output)}", receipt, message) Then Err.Raise vbObjectError + 2502, "close contract", message
    If Not CSTC2_WriteCloseReceipt("{quote_vb_string(output)}", receipt, message) Then Err.Raise vbObjectError + 2503, "close contract", message
    originalOrigin = receipt.CloseOrigin
    If receipt.CloseOrigin = "stop-request" Then
        receipt.CloseOrigin = "worker-failure"
    Else
        receipt.CloseOrigin = "stop-request"
    End If
    If CSTC2_WriteCloseReceipt("{quote_vb_string(output)}", receipt, message) Then Err.Raise vbObjectError + 2504, "close contract", "conflict was accepted"
    receipt.CloseOrigin = originalOrigin
    If Not CSTC2_ReadCloseReceipt("{quote_vb_string(output)}", "{receipt.session_id}", "{receipt.last_task_id}", storedReceipt, message) Then Err.Raise vbObjectError + 2505, "close contract", message
    If Not CSTC2_Same(receipt, storedReceipt) Then Err.Raise vbObjectError + 2506, "close contract", "original receipt changed"
    keys(0) = "session_id": values(0) = "{receipt.session_id}"
    keys(1) = "status": values(1) = "passed"
    If Not CSTP_AtomicWrite("{quote_vb_string(completed)}", "CST_CLOSE_CONTRACT_V1", keys, values, 2, message) Then Err.Raise vbObjectError + 2507, "close contract", message
End Sub
'''
    macro = root / 'close-receipt-contract.bas'
    macro.write_text("'#Language \"WWB-COM\"\nOption Explicit\n"
                     + 'Private Const CSTC2_CONTRACT_PROTOCOL As String = "v2"\n' + libraries + main,
                     encoding='ascii', newline='\n')
    return CloseReceiptWorkspace(root, macro, output, completed)


def verify_close_receipt_contract(workspace, expected):
    """Verify codec outputs only; callers must ALSO verify CST process shutdown."""
    actual = read_close_receipt(workspace.root, expected.session_id,
                                expected_task_id=expected.last_task_id)
    if actual != expected:
        raise ProtocolError('contract receipt differs from expected input')
    try:
        with workspace.completion_path.open('rb') as stream:
            content = stream.read(4097).decode('ascii')
        if len(content) > 4096 or _decode(content, 'CST_CLOSE_CONTRACT_V1') != {
                'session_id': expected.session_id, 'status': 'passed'}:
            raise ProtocolError('close receipt contract completion is invalid')
    except (OSError, UnicodeError) as exc:
        raise ProtocolError('close receipt contract completion is missing or unreadable') from exc
    return actual
