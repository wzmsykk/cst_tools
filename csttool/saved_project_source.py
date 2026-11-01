"""Strict saved-project byte source; no live settings or VBA interpretation."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType
import zlib

from ._vendor.cstv_readonly import CstFile, CstFormatError


class SourceError(ValueError):
    def __init__(self, status, reason, member=None):
        self.status, self.reason, self.member = status, reason, member
        super().__init__(f'{status}: {reason}' + (f' [{member}]' if member else ''))


@dataclass(frozen=True)
class ReadLimits:
    container_bytes: int = 256 * 1024 * 1024
    member_bytes: int = 32 * 1024 * 1024
    total_bytes: int = 64 * 1024 * 1024
    members: int = 10000

    def __post_init__(self):
        for value in (self.container_bytes, self.member_bytes, self.total_bytes, self.members):
            if type(value) is not int or value < 0:
                raise ValueError('read budgets must be nonnegative integers')


@dataclass(frozen=True)
class SavedSource:
    path: str
    sha256: str
    scope: str
    scopes: tuple
    members: object
    member_hashes: object

    def text(self, name, *, encoding=None):
        raw = self.members.get(name)
        if raw is None:
            return None
        if encoding not in (None, 'utf-8'):
            raise SourceError('unsupported', 'encoding-profile-missing', name)
        try:
            return raw.decode('utf-8', errors='strict')
        except UnicodeDecodeError as exc:
            raise SourceError('malformed' if encoding else 'unsupported',
                              'declared-encoding-violation' if encoding else 'encoding-profile-missing', name) from exc

    def json(self, name):
        text = self.text(name, encoding='utf-8')
        if text is None:
            return None
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError('duplicate JSON key')
                result[key] = value
            return result
        def constant(value):
            raise ValueError('non-finite JSON number')
        def number(value):
            result = float(value)
            if not math.isfinite(result):
                raise ValueError('non-finite JSON number')
            return result
        try:
            value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant,
                               parse_float=number)
            if not isinstance(value, dict):
                raise ValueError('JSON object required')
            return value
        except ValueError as exc:
            raise SourceError('malformed', 'invalid-json', name) from exc


def _identity(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def read_saved_source(path, *, scope, limits=ReadLimits()):
    """Read one bounded immutable snapshot; scope is an exact resolved identity.

    CRC covers selected members only. Other payloads are never inflated.
    """
    path = Path(path).resolve(strict=True)
    before = _identity(path.stat())
    if before[2] > limits.container_bytes:
        raise SourceError('rejected', 'container-budget-exceeded')
    with path.open('rb') as stream:
        raw = stream.read(limits.container_bytes + 1)
    if len(raw) > limits.container_bytes:
        raise SourceError('rejected', 'container-budget-exceeded')
    try:
        container = CstFile.from_bytes(raw, str(path))
        entries = container._central_entries()
        eidx = raw.rfind(b'PK\x05\x06')
        if (eidx + 22 + int.from_bytes(raw[eidx+20:eidx+22], 'little') != len(raw)
                or raw[eidx+8:eidx+10] != raw[eidx+10:eidx+12]):
            raise SourceError('malformed', 'invalid-directory-trailer')
        previous_end = 0
        for entry in entries:
            offset = entry['local_offset']
            if (offset < previous_end
                    or raw[offset+6:offset+8] != entry['flags'].to_bytes(2, 'little')
                    or raw[offset+8:offset+10] != entry['method'].to_bytes(2, 'little')):
                raise SourceError('malformed', 'local-directory-disagreement', entry['name'])
            if not entry['flags'] & 8:
                for local, central in [('crc_off', 'crc'), ('cs_off', 'csize'), ('us_off', 'usize')]:
                    start = offset + entry['layout'][local]
                    if int.from_bytes(raw[start:start+4], 'little') != entry[central]:
                        raise SourceError('malformed', 'local-directory-disagreement', entry['name'])
            previous_end = entry['data_end']
        if len(entries) > limits.members:
            raise SourceError('rejected', 'member-count-budget-exceeded')
        scopes = tuple(container.project_scopes())
        if not isinstance(scope, str) or scope not in scopes:
            raise SourceError('rejected', 'exact-scope-required')
        selected = {}
        total = 0
        wanted = {'Model/3D/Model.mod', 'Model/Parameters.json',
                  'Model/simulationproperties.json', 'Model/Model.prj'}
        for relative in sorted(wanted):
            name = container.scoped_member(relative, scope)
            entry = container._entry_by_name(name)
            if entry is None:
                continue
            if entry['flags'] & 1 or entry['method'] not in (0, 8):
                raise SourceError('unsupported', 'member-compression-or-encryption', name)
            total += entry['usize']
            if entry['usize'] > limits.member_bytes or total > limits.total_bytes:
                raise SourceError('rejected', 'expanded-budget-exceeded', name)
            # Bound actual output even if an attacker lies about usize.
            if entry['method'] == 8:
                payload = raw[entry['data_start']:entry['data_end']]
                decoder = zlib.decompressobj(-15)
                output = decoder.decompress(payload, entry['usize'] + 1)
                if len(output) > entry['usize']:
                    raise SourceError('rejected', 'expanded-budget-exceeded', name)
                if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise SourceError('malformed', 'invalid-deflate-boundary', name)
            selected[relative] = container.read_member(name)
    except (CstFormatError, UnicodeError, zlib.error) as exc:
        raise SourceError('malformed', 'container-integrity') from exc
    if before != _identity(path.stat()):
        raise SourceError('stale', 'source-changed-during-read')
    # Re-read bounded bytes to catch content mutation even with restored timestamps.
    with path.open('rb') as stream:
        check = stream.read(limits.container_bytes + 1)
    if raw != check or before != _identity(path.stat()):
        raise SourceError('stale', 'source-changed-during-read')
    return SavedSource(str(path), hashlib.sha256(raw).hexdigest(), scope, scopes,
                       MappingProxyType(selected), MappingProxyType({
                           n: hashlib.sha256(v).hexdigest() for n, v in selected.items()}))
