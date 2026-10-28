"""Strict boundaries for the test-only CBOR mesher evidence reader."""
import importlib.util
import importlib
import json
from pathlib import Path
import struct

import pytest

SPEC = importlib.util.spec_from_file_location(
    'tet_evidence', Path(__file__).parent / 'support/tet_options_evidence.py')
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


def test_options_float_and_nested_map():
    data = b'\xa1\x6aAttributes\xa1\x71d/step_near_model\xfb' + struct.pack('>d', 62.45676)
    # Text key has 17 bytes including d/ prefix.
    assert evidence.decode_options(data)['Attributes']['d/step_near_model'] == 62.45676


@pytest.mark.parametrize('data', [
    b'\xa1\x61a',  # missing value
    b'\xa2\x61a\x01\x61a\x02',  # duplicate key
    b'\xa0\x00',  # trailing data
    b'\xbf\xff',  # indefinite map outside this evidence subset
    b'\xc0\x00',  # tag outside this evidence subset
    b'\xa1\x01\x01',  # non-text key
    b'\xa1\x61a\xfb\x00',  # truncated float
    b'\x81' * 14 + b'\xa0',  # depth budget
])
def test_unsupported_or_corrupt_evidence_rejected(data):
    with pytest.raises(ValueError):
        evidence.decode_options(data)


def test_file_budget():
    with pytest.raises(ValueError, match='too large'):
        evidence.decode_options(b'\x00' * (1024 * 1024 + 1))


def test_zero_cells_and_exit_zero_do_not_become_mesh_success(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent / 'support'))
    mesh_probe = importlib.import_module('calibrate_tet_mesh')
    (tmp_path / 'mesh.tsv').write_text('0\t0\t0\tOK:0')
    native = tmp_path / 'input/Result'
    native.mkdir(parents=True)
    (native / 'output.txt').write_text('ERROR: mesh is not supported by the current solver')
    report = {'completed': True, 'exit_code': 0}
    with pytest.raises(RuntimeError, match='native mesh generation failed'):
        mesh_probe.collect_mesh_evidence(tmp_path, tmp_path / 'input.cst', report)
    saved = json.loads((tmp_path / 'report.json').read_text())
    assert saved['mesh_success'] is False and saved['mesh']['cells'] == 0
    assert (tmp_path / 'native-output.txt').read_text().startswith('ERROR:')


def test_positive_cell_count_without_native_success_is_rejected(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent / 'support'))
    mesh_probe = importlib.import_module('calibrate_tet_mesh')
    (tmp_path / 'mesh.tsv').write_text('100\t1\t2\tOK:1')
    native = tmp_path / 'input/Result'
    native.mkdir(parents=True)
    (native / 'output.txt').write_text('Meshing aborted')
    (native / 'Mesh_Input.Options.tet').write_bytes(b'\xa0')
    with pytest.raises(RuntimeError, match='native mesh generation failed'):
        mesh_probe.collect_mesh_evidence(tmp_path, tmp_path / 'input.cst', {})
