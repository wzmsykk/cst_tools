"""Offline regression of probe framing and evidence; never launches CST."""
import importlib.util
from pathlib import Path

SOURCE=Path(__file__).parent/'support/calibrate_cst_macrocheck.py'
spec=importlib.util.spec_from_file_location('calibrate_cst_macrocheck',SOURCE)
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_checked_modules_use_comment_language_directive_and_driver_is_single_entry(tmp_path):
    samples=probe.cases(tmp_path)
    assert all(code.startswith('\'#Language "WWB-COM"\n') for _,code,_ in samples)
    macro=probe.render(tmp_path,samples,'nonce')
    assert macro.count('Sub Main\n')==1
    assert macro.count('    On Error GoTo Failed\n')==1
    assert 'Set w0error = MacroCheckThis(w0source)' in macro
    assert 'Solver.Start' not in macro


def test_native_source_diagnostic_maps_line_but_does_not_invent_column():
    raw='10576\nUnexpected text.\n[*xMacroRunThis4*#5]  .Zrange ((-x)/2), x/2\n\n'
    result=probe.parse_error(raw)
    assert result['number']==10576
    assert result['wrapped_line_1based']==5
    assert result['original_statement'].startswith(' .Zrange')
    assert result['column'] is None
    unknown=probe.parse_error('10576\nUnexpected text.\nunknown source layout\n')
    assert unknown['source']=='unknown source layout'
    assert unknown['wrapped_line_1based'] is None


def test_positive_control_rejection_is_not_a_passing_calibration(tmp_path):
    sample=[('positive','Sub Main\nEnd Sub\n',True)]
    (tmp_path/'checks.tsv').write_text('positive\trejected\n',encoding='ascii')
    (tmp_path/'completed.txt').write_text('nonce',encoding='ascii')
    (tmp_path/'parameter-after.txt').write_text('2 * W0Base',encoding='ascii')
    closure=dict(exit_confirmed=True,exit_code=0)
    assert not probe.evaluate(tmp_path,sample,closure,'nonce')['acceptance_passed']


def test_quiet_binding_nonce_is_distinct_from_driver_completion_nonce(tmp_path):
    sample=[('positive','Sub Main\nEnd Sub\n',True)]
    (tmp_path/'checks.tsv').write_text('positive\taccepted\n',encoding='ascii')
    (tmp_path/'completed.txt').write_text('driver-nonce',encoding='ascii')
    (tmp_path/'parameter-after.txt').write_text('2 * W0Base',encoding='ascii')
    (tmp_path/'identity-bound.json').write_text('{"nonce":"owner-nonce"}',encoding='ascii')
    closure=dict(exit_confirmed=True,exit_code=0,quiet=dict(nonce='owner-nonce',setter_returned=True),
                 window_observation=dict(owned_foreground_events=0,errors=[],dropped_events=0))
    assert probe.evaluate(tmp_path,sample,closure,'driver-nonce')['acceptance_passed']
    closure['quiet']['nonce']='different-owner'
    assert not probe.evaluate(tmp_path,sample,closure,'driver-nonce')['acceptance_passed']
