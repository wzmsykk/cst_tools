"""Calibration-tool shape tests, not native acceptance evidence."""
import pytest
from csttool.winwrap_checks import check_module,check_history
from csttool.winwrap_emitter import GeneratedCodeError
from test.support.calibrate_winwrap_gate import compile_cases,spec_for,require_closed,verify_rejected_prefix


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


@pytest.mark.parametrize('closed,code',[(False,0),(True,1),(False,None),(True,False),(True,'0')])
def test_unknown_or_nonstandard_close_blocks_next_serial_case(closed,code):
    with pytest.raises(RuntimeError):require_closed(dict(exit_confirmed=closed,exit_code=code))


@pytest.mark.parametrize('mutation',['none','applied-geometry','missing-prefix','changed-prefix','later-block'])
def test_native_syntax_rejection_checks_actual_atomic_saved_prefix(mutation):
    from types import SimpleNamespace
    from csttool.history_program import partition
    model=spec_for('z');program=list(partition(model))
    index=next(i for i,b in enumerate(program) if b['caption']=='CST Tools A1 geometry-cylinder')
    blocks=[dict(b) for b in program[:index]]
    if mutation=='applied-geometry':blocks.append(program[index])
    if mutation=='missing-prefix':blocks.pop()
    if mutation=='changed-prefix':blocks[0]['history']=blocks[0]['history'].replace('"mm"','"m"')
    if mutation=='later-block':blocks.append(program[-1])
    source=SimpleNamespace(text=lambda member:'\n'.join("'@ "+b['caption']+'\n'+b['history'] for b in blocks))
    if mutation=='none':assert verify_rejected_prefix(source,model)==[b['caption'] for b in blocks]
    else:
        with pytest.raises(RuntimeError,match='pre-geometry'):verify_rejected_prefix(source,model)


@pytest.mark.parametrize('fault',[None,'macro-changed','history-changed','wrong-block'])
def test_injected_mapping_is_separate_and_bound_to_actual_artifacts(tmp_path,fault):
    import hashlib,json
    from csttool.configuration import write_json_atomic
    from csttool.history_program import partition
    from csttool.definition_editing import render_edit_macro
    from csttool.winwrap_checks import execution_definition_map
    from csttool.winwrap_emitter import assign_string,Variable
    from test.support.calibrate_winwrap_gate import injected_syntax_diagnostic
    spec=spec_for('z');program=[dict(b) for b in partition(spec)]
    index=next(i for i,b in enumerate(program) if b['caption']=='CST Tools A1 geometry-cylinder')
    original=program[index]['history'];program[index]['history']=original.replace('.Zrange ','.Zrange (',1)
    altered=program[index]['history']
    macro=render_edit_macro(tmp_path,spec,'0'*32).replace('\n'.join(assign_string(Variable('history'),original)),
                '\n'.join(assign_string(Variable('history'),altered)),1)
    mapping=execution_definition_map(spec,program,macro)
    mapping['hashes']['final_outer']=hashlib.sha256(macro.encode('ascii')).hexdigest()
    row=next(r for r in mapping['history'] if r.get('block_index')==index and r.get('method')=='Zrange')
    raw='10576\nUnexpected text.\n[module#'+str(row['line']+mapping['history_check_wrapper_lines'])+'] '+row['statement']+'\n'
    production=dict(block_index=index if fault!='wrong-block' else 0,mapping_status='unresolved',origin=None)
    write_json_atomic(tmp_path/'native-diagnostic.json',production);write_json_atomic(tmp_path/'source-map.json',mapping)
    (tmp_path/'probe.bas').write_text(macro+(' ' if fault=='macro-changed' else ''),encoding='ascii')
    (tmp_path/'history.vb').write_text(altered+(' ' if fault=='history-changed' else ''),encoding='ascii')
    (tmp_path/'history-syntax-error.txt').write_text(raw)
    if fault:
        with pytest.raises(RuntimeError,match='source artifacts'):injected_syntax_diagnostic(tmp_path)
    else:
        observed=injected_syntax_diagnostic(tmp_path)
        assert observed['origin']['input_field']=='cylinder.axial_range'
        assert observed['production_mapping_status']=='unresolved'
        assert json.loads((tmp_path/'native-diagnostic.json').read_text())==production
