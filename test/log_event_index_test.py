from pathlib import Path

from csttool.log_event_index import render_event_table


def test_documented_events_match_source():
    root = Path(__file__).resolve().parents[1]
    document = (root / 'docs/log-event-index.md').read_text(encoding='utf-8')
    documented = [line for line in document.splitlines() if line.startswith('| `')]
    generated = [line for line in render_event_table(root).splitlines() if line.startswith('| `')]
    assert sorted(documented) == sorted(generated)
