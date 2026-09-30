"""Derive explicit event locations from source without importing CST modules."""

import ast
from pathlib import Path


def event_locations(root: Path) -> set[tuple[str, str]]:
    events = set()
    for directory in ('csttool', 'GUI'):
        for path in sorted((root / directory).rglob('*.py')):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                for key, value in zip(node.keys, node.values):
                    if (isinstance(key, ast.Constant) and key.value == 'event'
                            and isinstance(value, ast.Constant) and isinstance(value.value, str)):
                        events.add((value.value, path.relative_to(root).as_posix()))
    return events


def render_event_table(root: Path) -> str:
    return '\n'.join(['| 事件 | 实现模块 |', '| --- | --- |'] + [
        f'| `{event}` | `{path}` |' for event, path in sorted(event_locations(root))
    ])


if __name__ == '__main__':
    print(render_event_table(Path(__file__).resolve().parents[1]))
