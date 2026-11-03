"""D1 preservation proof against a frozen pre-migration index, not runtime proof."""
import copy
from pathlib import Path
import re

from scripts.project_inspect import load, render, validate

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'test/fixtures/feature-index-before-d1.md'


def rows(text):
    return [line.strip('|').split('|') for line in text.splitlines()
            if re.match(r'^\|F\d+\|', line)]


def normalized_links(cell, parent):
    return [(label, (parent / target.partition('#')[0]).resolve(), target.partition('#')[2])
            for label, target in re.findall(r'\[([^]]+)\]\(([^)]+)\)', cell)]


def test_all_136_features_preserved_in_order_and_content():
    old = rows(BASELINE.read_text(encoding='utf-8'))
    catalog = load(ROOT)
    new = rows(render(catalog))[:136]
    assert len(old) == len(new) == 136
    assert len(catalog['features']) == 137
    assert catalog['features'][-1]['id'] == 'F138'
    assert [r[0] for r in old] == [f['id'] for f in catalog['features'][:136]]
    assert len({f['id'] for f in catalog['features']}) == 137
    for before, after in zip(old, new):
        assert before[:2] == after[:2]
        assert re.findall(r'`([^`]+)`', before[3]) == re.findall(r'`([^`]+)`', after[3])
        for column in (2, 4, 5):
            assert normalized_links(before[column], ROOT / 'docs') == normalized_links(after[column], ROOT / 'docs')
            # Also preserve non-link information, including F133's manual verification note.
            plain = lambda value: re.sub(r'\[[^]]+\]\([^)]+\)', '', value).strip(' 、,;')
            assert plain(before[column]) == plain(after[column])
    assert (ROOT / 'docs/feature-index.md').read_text(encoding='utf-8') == render(catalog)


def test_duplicate_id_is_rejected():
    catalog = copy.deepcopy(load(ROOT))
    catalog['features'].append(copy.deepcopy(catalog['features'][0]))
    result = validate(ROOT, catalog)
    assert not result['valid']
    assert any(e.get('kind') == 'duplicate-feature-id' for e in result['errors'])


def test_each_source_symbol_and_missing_path_are_checked():
    catalog = copy.deepcopy(load(ROOT))
    catalog['features'][0]['sources'].append(dict(path='scripts/project_inspect.py', label='secondary', symbols=['missing_symbol']))
    result = validate(ROOT, catalog)
    assert not result['valid']
    assert any('missing_symbol' in e.get('message', '') for e in result['errors'])
    catalog['features'][0]['sources'][-1]['path'] = 'missing-file.py'
    assert not validate(ROOT, catalog)['valid']


def test_missing_feature_changes_baseline_and_stales_generated_index():
    catalog = copy.deepcopy(load(ROOT))
    catalog['features'].pop(0)
    assert catalog['features'][0]['id'] != rows(BASELINE.read_text(encoding='utf-8'))[0][0]
    assert any(e.get('kind') == 'derived-index-stale' for e in validate(ROOT, catalog)['errors'])


def test_fingerprint_warning_does_not_claim_semantic_review():
    catalog = copy.deepcopy(load(ROOT))
    path = next(iter(catalog['source_fingerprints']))
    catalog['source_fingerprints'][path] = '0' * 64
    result = validate(ROOT, catalog)
    assert result['valid']
    assert any(w['path'] == path for w in result['warnings'])
    assert result['semantic_and_runtime_validation'] is False
