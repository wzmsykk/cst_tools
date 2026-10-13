"""Link/symbol integrity only; prose correctness requires implementation review."""
import ast
from pathlib import Path
import re

ROOT = Path(__file__).parents[1]


def test_feature_index_links_and_source_symbols():
    index = ROOT / 'docs/feature-index.md'
    text = index.read_text(encoding='utf-8')
    for target in re.findall(r'\]\(([^)]+)\)', text):
        assert (index.parent / target).is_file(), target
    ids = []
    for row in text.splitlines():
        if not re.match(r'^\|F\d+', row):
            continue
        fields = row.strip('|').split('|')
        ids.append(fields[0])
        path = index.parent / re.search(r'\]\(([^)]+)\)', fields[2]).group(1)
        symbols = re.findall(r'`([^`]+)`', fields[3])
        source = path.read_text(encoding='utf-8')
        if path.suffix == '.py':
            tree = ast.parse(source)
            available = {node.name for node in tree.body
                         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    available.update(f'{node.name}.{child.name}' for child in node.body
                                     if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)))
        else:
            available = set(re.findall(r'(?im)^\s*(?:(?:Public|Private)\s+)?(?:Sub|Function)\s+(\w+)', source))
        assert set(symbols) <= available, (path, set(symbols) - available)
    assert len(ids) >= 12 and len(ids) == len(set(ids))


def test_agent_instructions_require_documentation_sync():
    text = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    assert '同一工作批次主动同步' in text
    assert 'docs/feature-index.md' in text and 'docs/current-status.md' in text
