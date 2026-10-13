from pathlib import Path

def test_saved_export_returns_without_quit():
    # Static lifecycle contract independent of export parameter schema.
    template = Path('csttool/saved_field_export.py').read_text()
    assert '\n    Quit\n' not in template
    assert 'ProbeStage "failed-returning"' in template


def test_benchmark_failure_does_not_save_or_quit():
    macro = Path('test/support/field_public_native.bas').read_text()
    failure = macro.split('Failed:')[1]
    assert '\n    Save\n' not in failure
    assert '\n    Quit\n' not in failure
