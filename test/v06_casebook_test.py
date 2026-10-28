"""Casebook structure/provenance only; no settings interpreter is exercised.

Passing these checks MUST NOT be reported as V06 semantic acceptance.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / 'fixtures/cst_settings_verifier_v06'


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, f'duplicate fixture key: {key}'
        result[key] = value
    return result


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'),
                      object_pairs_hook=_unique_object)


def test_casebook_structure_and_unexecuted_semantic_status():
    book = _load('cases.json')
    assert book['schema_version'] == 1
    assert book['semantic_implementation'] == 'not-implemented'
    ids = [case['id'] for case in book['cases']]
    assert len(ids) == 56 and len(ids) == len(set(ids))
    assert {c['group'] for c in book['cases']} == {'history', 'scope', 'mesh', 'source', 'execution'}
    statuses = {'resolved', 'unresolved', 'unsupported', 'malformed', 'stale', 'rejected',
                'ambiguous', 'execution-match', 'execution-mismatch'}
    for case in book['cases']:
        assert case['origin'] == 'normative-synthetic'
        assert case['semantic_execution'] == 'not-run'
        assert isinstance(case['input']['available_scopes'], list)
        assert isinstance(case['input']['histories'], dict)
        assert isinstance(case['input']['parameters'], dict)
        expected = case['expected']
        assert expected['status'] in statuses
        assert isinstance(expected['fields'], dict) and isinstance(expected['reasons'], list)
        assert expected['publish_ready'] is False
        assert 'live_value' not in expected
        if expected['status'] != 'resolved':
            assert expected['reasons'] or expected['status'] == 'execution-match'
        if case['group'] == 'execution':
            assert case['input']['expected_execution_config']
            assert case['input']['calibration_profile']['float_format']['significant_digits'] == 6


def test_saved_history_anchors_and_original_sources_have_recorded_hashes():
    manifest = _load('evidence.json')
    assert len(manifest['anchors']) == 5
    assert len({a['id'] for a in manifest['anchors']}) == 5
    checked_sources = {}
    for anchor in manifest['anchors']:
        path = (FIXTURES / anchor['fixture']).resolve()
        assert path.is_relative_to(FIXTURES.resolve())
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == anchor['fixture_sha256']
        assert len(data.splitlines()) == anchor['line_end'] - anchor['line_start'] + 1
        source = (ROOT / anchor['source']).resolve()
        assert source.is_relative_to((ROOT / 'model').resolve())
        if source not in checked_sources:
            checked_sources[source] = hashlib.sha256(source.read_bytes()).hexdigest()
        assert checked_sources[source] == anchor['source_sha256']
        assert anchor['member'].endswith('Model/3D/Model.mod')
        assert len(anchor['member_sha256']) == 64
    disabled = next(a for a in manifest['anchors'] if a['id'] == 'pillbox-root-step60')
    assert disabled['disabled'] and b'.SetNumberOfModes "12"' in (FIXTURES / disabled['fixture']).read_bytes()
    active = next(a for a in manifest['anchors'] if a['id'] == 'pillbox-root-step61')
    assert not active['disabled'] and b'.SetNumberOfModes "1"' in (FIXTURES / active['fixture']).read_bytes()


def test_encoding_evidence_does_not_turn_replacement_decoding_into_support():
    anchors = _load('evidence.json')['anchors']
    assert any(a['member_encoding']['strict_utf8'] for a in anchors)
    legacy = [a for a in anchors if not a['member_encoding']['strict_utf8']]
    assert len(legacy) == 3
    for anchor in legacy:
        assert anchor['source'] == 'model/Enlarged.cst'
        assert anchor['member_encoding']['semantic_fallback_used'] is False
        assert anchor['member_encoding']['first_error_offset'] >= 0
        assert bytes.fromhex(anchor['member_encoding']['context_hex'])


def test_required_boundary_oracles_remain_distinct():
    cases = {c['id']: c for c in _load('cases.json')['cases']}
    # These are expectations, not calls to a parser or verification engine.
    assert cases['H08']['expected']['status'] == 'unresolved'
    assert cases['S04']['input']['scope'] == 'FME'
    assert cases['S04']['expected']['status'] == 'rejected'
    assert cases['D06']['expected']['status'] == 'malformed'
    assert cases['D10']['expected']['status'] == 'unsupported'
    assert cases['E01']['input']['result_success'] is False
    assert cases['E01']['expected']['status'] == 'execution-match'
    assert cases['E10']['expected']['status'] == 'execution-mismatch'
    assert cases['E11']['expected']['status'] == 'execution-match'
