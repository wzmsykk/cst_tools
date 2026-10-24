"""Frozen close-receipt v2 codec; task/completion/ACK remain v1.

Only static workspace version selection lives here, not worker state changes,
solver calls or policies for accepting process exit codes.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

from .runtime_protocol import ProtocolError, _decode, _encode, _validate_uuid


CLOSE_RECEIPT_MAGIC = 'CST_CLOSE_RECEIPT_V2'
MAX_FRAME_BYTES = 4096
MAX_SNAPSHOT_BYTES = 9223372036854775807
FIELDS = ('session_id', 'last_task_id', 'close_origin', 'task_outcome', 'close_outcome',
          'model_state', 'last_completed_phase', 'snapshot_ref', 'snapshot_bytes', 'error_code')
CHOICES = {
    'close_origin': {'stop-request', 'worker-failure'},
    'task_outcome': {'not-started', 'success', 'failure', 'cancelled', 'unknown'},
    'close_outcome': {'saved', 'restored-saved', 'failed'},
    'model_state': {'prepared', 'committed', 'dirty', 'restored-saved', 'restore-failed', 'unknown'},
    'last_completed_phase': {'none', 'restore', 'rebuild', 'backup', 'save', 'receipt'},
    'snapshot_ref': {'none', 'worker-input.cst', 'worker-input.cst.recovered.cst', 'worker-input.cst.closed.cst'},
    'error_code': {'none', 'CLOSE_RESTORE_FAILED', 'CLOSE_REBUILD_FAILED', 'CLOSE_BACKUP_FAILED',
                   'CLOSE_SAVE_FAILED', 'CLOSE_RECEIPT_FAILED', 'CLOSE_PROTOCOL_ERROR', 'CLOSE_INTERNAL_ERROR'},
}


@dataclass(frozen=True, slots=True)
class CloseReceipt:
    session_id: str
    last_task_id: str
    close_origin: str
    task_outcome: str
    close_outcome: str
    model_state: str
    last_completed_phase: str
    snapshot_ref: str
    snapshot_bytes: int
    error_code: str

    def __post_init__(self):
        _validate_uuid('session_id', self.session_id)
        if self.last_task_id != 'none':
            _validate_uuid('last_task_id', self.last_task_id)
        for name, allowed in CHOICES.items():
            value = getattr(self, name)
            if not isinstance(value, str) or value not in allowed:
                raise ProtocolError('invalid close receipt ' + name)
        if type(self.snapshot_bytes) is not int or not 0 <= self.snapshot_bytes <= MAX_SNAPSHOT_BYTES:
            raise ProtocolError('snapshot_bytes must be a non-negative int64')
        if ((self.last_task_id == 'none' and self.task_outcome not in {'not-started', 'unknown'})
                or (self.last_task_id != 'none' and self.task_outcome == 'not-started')):
            raise ProtocolError('task identity/outcome mismatch')
        if (self.snapshot_ref == 'none') != (self.snapshot_bytes == 0):
            raise ProtocolError('snapshot reference/size mismatch')
        if (self.close_outcome == 'failed') != (self.error_code != 'none'):
            raise ProtocolError('close outcome/error code mismatch')
        if self.close_outcome != 'failed':
            if self.last_completed_phase not in {'save', 'receipt'} or self.snapshot_bytes == 0:
                raise ProtocolError('successful close requires a saved snapshot')
            if self.close_outcome == 'saved':
                if self.model_state not in {'prepared', 'committed'} or self.snapshot_ref not in {'worker-input.cst', 'worker-input.cst.closed.cst'}:
                    raise ProtocolError('saved close/model/snapshot mismatch')
            elif (self.model_state != 'restored-saved'
                  or self.snapshot_ref != 'worker-input.cst.recovered.cst'):
                raise ProtocolError('restored close/model/snapshot mismatch')


def encode_close_receipt(receipt: CloseReceipt) -> str:
    return _encode(CLOSE_RECEIPT_MAGIC,
                   ((name, str(getattr(receipt, name))) for name in FIELDS))


def decode_close_receipt(text: str) -> CloseReceipt:
    if not isinstance(text, str) or not text.isascii() or len(text) > MAX_FRAME_BYTES:
        raise ProtocolError('close receipt must be bounded ASCII')
    values = _decode(text, CLOSE_RECEIPT_MAGIC)
    if set(values) != set(FIELDS):
        raise ProtocolError('close receipt contains missing or unknown fields')
    if not re.fullmatch(r'0|[1-9][0-9]{0,18}', values['snapshot_bytes']):
        raise ProtocolError('snapshot_bytes is not a canonical int64')
    return CloseReceipt(**{**values, 'snapshot_bytes': int(values['snapshot_bytes'])})


def _publish_immutable(path, text, decode, expected):
    path = Path(path)
    def existing():
        try:
            with path.open('rb') as stream:
                content = stream.read(MAX_FRAME_BYTES + 1)
            if len(content) > MAX_FRAME_BYTES:
                raise ProtocolError('oversized immutable output')
            return decode(content.decode('ascii'))
        except (OSError, UnicodeError, ValueError) as exc:
            raise ProtocolError('existing protocol output is invalid: ' + str(exc)) from exc
    if path.exists():
        if existing() != expected:
            raise ProtocolError('conflicting immutable protocol output: ' + path.name)
        return path
    try:
        # Unlike replace(), these commit operations cannot overwrite a winner
        # that appeared after the initial existence check. Keep failed temp
        # files for diagnostics, and never remove another producer's temp.
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.tmp')
        with temporary.open('x', encoding='ascii', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == 'nt':
            os.rename(temporary, path)  # Windows rename is no-replace.
        else:
            os.link(temporary, path)  # POSIX rename would replace.
            temporary.unlink()
        return path
    except FileExistsError:
        if path.is_file() and existing() == expected:
            return path
        raise ProtocolError('protocol output is conflicting or publication is incomplete: ' + path.name) from None


def _strict_json(text):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ProtocolError('duplicate declaration field: ' + key)
            value[key] = item
        return value
    value = json.loads(text, object_pairs_hook=unique)
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'session_id', 'close_protocol'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or not isinstance(value['close_protocol'], str) or value['close_protocol'] not in {'v1', 'v2'}):
        raise ProtocolError('invalid static close protocol declaration')
    _validate_uuid('session_id', value['session_id'])
    return value


def declare_close_protocol(root, session_id, version='v1'):
    """Declare once BEFORE generating/launching the workspace; no negotiation."""
    _validate_uuid('session_id', session_id)
    if version not in {'v1', 'v2'}:
        raise ProtocolError('unsupported close protocol')
    value = dict(schema_version=1, session_id=session_id, close_protocol=version)
    return _publish_immutable(Path(root) / 'close-protocol.json',
        json.dumps(value, sort_keys=True) + '\n', _strict_json, value)


def read_close_protocol(root, session_id, *, expected_version=None):
    root = Path(root)
    if expected_version not in {None, 'v1', 'v2'}:
        raise ProtocolError('unsupported expected close protocol')
    path = root / 'close-protocol.json'
    if not path.exists():
        if expected_version == 'v2' or (root / 'protocol/close.receipt').exists():
            raise ProtocolError('missing static close protocol declaration; no v2 downgrade')
        return 'v1'  # Legacy workspaces only.
    try:
        if path.stat().st_size > MAX_FRAME_BYTES:
            raise ProtocolError('oversized close protocol declaration')
        with path.open('rb') as stream:
            value = _strict_json(stream.read(MAX_FRAME_BYTES + 1).decode('ascii'))
        if (not isinstance(value, dict) or set(value) != {'schema_version', 'session_id', 'close_protocol'}
                or type(value['schema_version']) is not int or value['schema_version'] != 1
                or value['session_id'] != session_id or value['close_protocol'] not in {'v1', 'v2'}):
            raise ProtocolError('invalid static close protocol declaration')
        if expected_version is not None and value['close_protocol'] != expected_version:
            raise ProtocolError('close protocol mismatch; no downgrade')
        if value['close_protocol'] == 'v1' and (root / 'protocol/close.receipt').exists():
            raise ProtocolError('v2 receipt conflicts with v1 declaration')
        return value['close_protocol']
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise ProtocolError('close protocol declaration rejected: ' + str(exc)) from exc


def publish_close_receipt(root, receipt):
    read_close_protocol(root, receipt.session_id, expected_version='v2')
    return _publish_immutable(Path(root) / 'protocol/close.receipt', encode_close_receipt(receipt),
                              decode_close_receipt, receipt)


def read_close_receipt(root, session_id, *, expected_task_id=None, validate_snapshot=True):
    """Strict v2 read, including identity and fixed-path artifact checks."""
    root = Path(root)
    read_close_protocol(root, session_id, expected_version='v2')
    path = root / 'protocol/close.receipt'
    try:
        with path.open('rb') as stream:
            data = stream.read(MAX_FRAME_BYTES + 1)
        receipt = decode_close_receipt(data.decode('ascii'))
        if receipt.session_id != session_id or (
                expected_task_id is not None and receipt.last_task_id != expected_task_id):
            raise ProtocolError('close receipt belongs to another session/task')
        if validate_snapshot and receipt.snapshot_ref != 'none':
            snapshot = root / receipt.snapshot_ref
            if (not snapshot.resolve().is_relative_to(root.resolve()) or not snapshot.is_file()
                    or snapshot.stat().st_size != receipt.snapshot_bytes):
                raise ProtocolError('close receipt snapshot is missing, outside workspace, or changed')
        return receipt
    except (OSError, UnicodeError) as exc:
        raise ProtocolError('close receipt unavailable: ' + str(exc)) from exc
