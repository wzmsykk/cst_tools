"""Execute exactly the standalone comparison under pytest, without solving."""
import pytest
from test.support.compare_worker_startup import run_comparison

pytestmark = pytest.mark.integration


def test_identical_worker_startup_inside_pytest(cst_executable):
    reports = run_comparison(cst_executable)
    assert len(reports) == 2, reports
    for report in reports:
        assert report['ready'], report
        assert report['standard_stop'], report
        assert report['stop_ack'], report
        assert report['exit_code'] == 0, report
        assert not report['remaining'], report


def test_worker_startup_without_inherited_offscreen(cst_executable, monkeypatch):
    monkeypatch.delenv('QT_QPA_PLATFORM', raising=False)
    reports = run_comparison(cst_executable)
    assert len(reports) == 2, reports
    for report in reports:
        assert report['ready'] and report['standard_stop'], report
        assert report['stop_ack'] and report['exit_code'] == 0, report
        assert not report['remaining'], report
