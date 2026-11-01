from pathlib import Path
import hashlib
import json
import struct
import zlib

import pytest
from csttool.saved_project_source import read_saved_source, SourceError, ReadLimits

ROOT = Path(__file__).parents[1]
HISTORY = 'Model/3D/Model.mod'


def container(items):
    data = bytearray(); central = bytearray()
    for name, value in items:
        name = name.encode(); offset = len(data); crc = zlib.crc32(value)
        # Native vendor layout (+4 bytes before CRC/lengths).
        local = bytearray(34); local[:4] = b'DE\x03\x04'
        struct.pack_into('<IIIHH', local, 18, crc, len(value), len(value), len(name), 0)
        data += local + name + value
        cd = bytearray(50); cd[:4] = b'DE\x01\x02'
        struct.pack_into('<III', cd, 20, crc, len(value), len(value))
        struct.pack_into('<H', cd, 32, len(name)); struct.pack_into('<I', cd, 46, offset)
        central += cd + name
    end = bytearray(22); end[:4] = b'PK\x05\x06'
    struct.pack_into('<HHII', end, 8, len(items), len(items), len(central), len(data))
    return data + central + end


def write(tmp_path, items):
    path = tmp_path / 'copy.cst'; path.write_bytes(container(items)); return path


def test_real_sources_and_scope():
    p = read_saved_source(ROOT/'model/Pillbox.cst', scope='root')
    assert p.text(HISTORY)
    assert p.json('Model/Parameters.json')['parameters']
    e = read_saved_source(ROOT/'model/Enlarged.cst', scope='SP/FME')
    assert 'SP/FMF' in e.scopes
    assert e.sha256 == hashlib.sha256((ROOT/'model/Enlarged.cst').read_bytes()).hexdigest()
    with pytest.raises(SourceError, match='encoding-profile-missing'):
        e.text(HISTORY)
    with pytest.raises(SourceError, match='declared-encoding-violation'):
        e.text(HISTORY, encoding='utf-8')


@pytest.mark.parametrize('scope', [None, '', 'FME', 'SP/missing', '/root'])
def test_no_scope_defaults(scope):
    with pytest.raises(SourceError, match='exact-scope-required'):
        read_saved_source(ROOT/'model/Pillbox.cst', scope=scope)


@pytest.mark.parametrize('value', [b'{', b'{"a":1,"a":2}', b'[]', b'{"a":NaN}'])
def test_json_failures(tmp_path, value):
    p = read_saved_source(write(tmp_path, [('Model/simulationproperties.json', value)]), scope='root')
    assert p.json('Model/Parameters.json') is None
    with pytest.raises(SourceError, match='invalid-json'):
        p.json('Model/simulationproperties.json')


def test_crc_duplicate_and_budgets(tmp_path):
    path = write(tmp_path, [(HISTORY, b'hello')])
    raw = bytearray(path.read_bytes()); raw[34+len(HISTORY)] ^= 1; path.write_bytes(raw)
    with pytest.raises(SourceError, match='container-integrity'):
        read_saved_source(path, scope='root')
    path = write(tmp_path, [(HISTORY,b'a'),(HISTORY,b'b')])
    with pytest.raises(SourceError, match='container-integrity'):
        read_saved_source(path, scope='root')
    path = write(tmp_path, [(HISTORY,b'hello')])
    for limits in [ReadLimits(container_bytes=2), ReadLimits(member_bytes=2), ReadLimits(total_bytes=2), ReadLimits(members=0)]:
        with pytest.raises(SourceError, match='budget-exceeded'):
            read_saved_source(path, scope='root', limits=limits)


def test_mutation_during_read(tmp_path, monkeypatch):
    path = write(tmp_path, [(HISTORY,b'hello')])
    from csttool._vendor.cstv_readonly import CstFile
    original = CstFile.read_member
    def mutate(self, name):
        result = original(self, name)
        path.write_bytes(path.read_bytes()+b'changed')
        return result
    monkeypatch.setattr(CstFile, 'read_member', mutate)
    with pytest.raises(SourceError, match='source-changed'):
        read_saved_source(path, scope='root')


def test_pin():
    vendor = ROOT/'csttool/_vendor'
    provenance = json.loads((vendor/'provenance.json').read_text())
    assert hashlib.sha256((vendor/'cstv_readonly.py').read_bytes()).hexdigest() == provenance['extracted_sha256']

@pytest.mark.parametrize('kind', ['trailer', 'method', 'deflate', 'bomb'])
def test_container_rejection(tmp_path, kind):
    path = write(tmp_path, [(HISTORY,b'hello')]); raw = bytearray(path.read_bytes())
    cd = raw.index(b'DE\x01\x02')
    if kind == 'trailer':
        raw += b'garbage'
    else:
        method = 99 if kind == 'method' else 8
        struct.pack_into('<H',raw,8,method); struct.pack_into('<H',raw,cd+10,method)
        if kind == 'bomb':
            compressor=zlib.compressobj(wbits=-15)
            payload=compressor.compress(b'x'*1000)+compressor.flush()
            start=34+len(HISTORY); raw[start:cd]=payload
            newcd=start+len(payload)
            struct.pack_into('<I',raw,22,len(payload))
            struct.pack_into('<I',raw,newcd+24,len(payload))
            end=len(raw)-22;struct.pack_into('<II',raw,end+12,len(raw)-22-newcd,newcd)
    path.write_bytes(raw)
    with pytest.raises(SourceError):
        read_saved_source(path,scope='root')
