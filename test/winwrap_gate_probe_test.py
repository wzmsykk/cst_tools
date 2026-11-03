"""Calibration-tool shape tests, not native acceptance evidence."""
import pytest
from csttool.winwrap_checks import check_module,check_history
from csttool.winwrap_emitter import GeneratedCodeError
from test.support.calibrate_winwrap_gate import compile_cases,spec_for,require_closed


def test_native_corpus_keeps_real_counterexample_and_observational_quote_case(tmp_path):
    rows=compile_cases(tmp_path)
    assert len(rows)==23 and len({name for name,_,_ in rows})==23
    assert next(e for n,_,e in rows if n=='zrange-original') is False
    observed=next(code for n,code,e in rows if n=='outer-unclosed-quote-observed' and e is None)
    with pytest.raises(GeneratedCodeError):check_module(observed)
    for name,code,expected in rows:
        if name.startswith('outer-') and expected is True:check_module(code)
        if name.startswith('history-'):check_history('\n'.join(code.splitlines()[3:-1]))
    assert spec_for('x')['parameters']['L']['expression']=='(R^2)/R + R'
    assert spec_for('x')['parameters']['R']['description'].strip()==spec_for('x')['parameters']['R']['description']


@pytest.mark.parametrize('closed,code',[(False,0),(True,1),(False,None)])
def test_unknown_or_nonstandard_close_blocks_next_serial_case(closed,code):
    with pytest.raises(RuntimeError):require_closed(dict(exit_confirmed=closed,exit_code=code))
