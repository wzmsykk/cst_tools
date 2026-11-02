"""Probe verdict tests; no COM activation, licence checks or CST execution."""
import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).parent / 'support/validate_winwrap_noui.py'
spec = importlib.util.spec_from_file_location('validate_winwrap_noui', SOURCE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def complete_report():
    return dict(child_normal_exit=True, new_cst=[], child=dict(
        initialized=True, shutdown=0, disconnect=True, body_marker_absent=True,
        cases=[dict(name=name, expectation=expected, accepted=expected != 'must-reject')
               for name, _, expected in probe.cases(Path('marker'))]))


def test_expired_initialization_and_zero_exit_do_not_imply_syntax_pass():
    report = dict(child_normal_exit=True, new_cst=[], child=dict(
        initialized=False, shutdown=0, disconnect=True, cases=[]))
    verdict = probe.evaluate_report(report)
    assert verdict['object_close_confirmed']
    assert verdict['syntax_checks'] == 0
    assert not verdict['initialized']
    assert not verdict['calibration_complete']


@pytest.mark.parametrize('fault', ['shutdown', 'disconnect', 'exit', 'marker', 'missing-case', 'wrong-verdict', 'new-cst'])
def test_incomplete_or_unsafe_facts_prevent_complete_calibration(fault):
    report = complete_report()
    assert probe.evaluate_report(report)['calibration_complete']
    if fault == 'shutdown': report['child']['shutdown'] = -1
    if fault == 'disconnect': report['child']['disconnect'] = False
    if fault == 'exit': report['child_normal_exit'] = False
    if fault == 'marker': report['child']['body_marker_absent'] = False
    if fault == 'missing-case': report['child']['cases'].pop()
    if fault == 'wrong-verdict': report['child']['cases'][0]['accepted'] = False
    if fault == 'new-cst': report['new_cst'] = [dict(pid=1)]
    assert not probe.evaluate_report(report)['calibration_complete']
