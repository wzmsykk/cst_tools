"""Probe contract checks; native behavior is accepted only by its real report."""
from test.support import calibrate_winwrap_calls as probe
from csttool.definition_editing import render_edit_macro


def test_extension_keeps_original_counterexample_and_distinguishes_sample_limits(tmp_path):
    rows=probe.samples(tmp_path)
    assert len(rows)==23 and len({name for name,_,_ in rows})==23
    assert next(expected for name,_,expected in rows if name=='zrange-original') is False
    assert all(expected is None for name,_,expected in rows if name.startswith(('literal-','continuations-')))
    macro,history=probe.driver(tmp_path,rows,'nonce')
    assert macro.count('Sub Main\n')==1 and macro.count('    On Error GoTo Failed\n')==1
    assert 'Call W0Mutate(w0names, w0scalar)' in macro
    assert 'ByRef items() As String' in macro and 'ByRef scalar As Double' in macro
    assert 'Call .Zrange' in history and 'If Not Rebuild Then' in macro
    assert '.Start' not in macro and 'OpenFile' not in macro
    macro.encode('ascii')


def test_w1_acceptance_uses_current_production_renderer_and_stable_parameter_data(tmp_path):
    spec=probe.definition()
    macro=render_edit_macro(tmp_path,spec,'nonce')
    assert spec['parameters']['L']['expression']=='2 * R'
    assert 'AddToHistory' in macro and 'ChrW(' in macro
    assert 'StoreParameters(names, expressions)' in macro
