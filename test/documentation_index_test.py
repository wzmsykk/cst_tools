"""Link/symbol integrity only; prose correctness requires implementation review."""
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_feature_index_links_and_source_symbols():
    from scripts.project_inspect import load, validate
    result = validate(ROOT, load(ROOT))
    assert result['valid'], result['errors']
    assert result['warnings'] == []
    assert result['semantic_and_runtime_validation'] is False


def test_agent_instructions_require_documentation_sync():
    text = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    assert '同一工作批次主动同步' in text
    assert 'docs/feature-index.md' in text and 'docs/current-status.md' in text
