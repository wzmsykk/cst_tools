"""Independent mutation tests. Passing these is not native compilation proof."""
from copy import deepcopy
from pathlib import Path
import random
import pytest

from csttool import winwrap_checks as checks
from csttool.winwrap_emitter import GeneratedCodeError
from csttool.definition_editing import render_history, render_edit_macro
from test.support.calibrate_winwrap_calls import definition


@pytest.mark.parametrize('fault',['parentheses','quote','with','command','arity','execute'])
def test_history_mutations_rejected_independently_of_emitter(fault):
    history=render_history(definition())[0]
    line=next(s for s in history.splitlines() if s.startswith(' .Zrange '))
    mutations={
        'parentheses':history.replace(line,' .Zrange ((-RestoreDoubleParameter("L"))/2), (RestoreDoubleParameter("L")/2)'),
        'quote':history.replace('"Vacuum"','"Vacuum'),
        'with':history.replace('End With','',1),
        'command':history+'\nSolver.Start',
        'arity':history.replace(line,' .Zrange 1'),
        'execute':history+'\nExecute "arbitrary"'}
    with pytest.raises(GeneratedCodeError):checks.check_history(mutations[fault])


@pytest.mark.parametrize('fault',['duplicate','block','unknown','quote','long','continuation','module','label'])
def test_outer_mutations_rejected_before_cst(tmp_path,fault):
    macro=render_edit_macro(tmp_path,definition(),'nonce')
    mutations={'duplicate':macro.replace('    f = FreeFile','    Dim f As String\n    f = FreeFile',1),
        'block':macro.replace('    End If\n','',1),
        'unknown':macro.replace('    SaveAs ','    Kill ',1),
        'quote':macro.replace('"batch-return"','"batch-return'),
        'long':macro+'\n'+('x'*801),
        'continuation':macro.replace('    f = FreeFile','    f = _\n FreeFile',1),
        'module':macro+'\nClass Unexpected\nEnd Class',
        'label':macro.replace('Failed:','Failed:\nFailed:',1)}
    with pytest.raises(GeneratedCodeError):checks.check_module(mutations[fault])


def test_random_bounded_expression_semantics_and_all_axes_are_preserved():
    rng=random.Random(23503)
    for axis in 'xyz':
        for _ in range(12):
            spec=definition(); n=rng.randint(1,8)
            spec['cylinder']['axis']=axis
            spec['postprocess'][1]['settings']['integration_line']['axis']=axis
            spec['cylinder']['axial_range']=[f'-(L+R*{n})/2',f'(L+R*{n})/2']
            history,projection=render_history(spec)
            checks.check_history(history)
            assert projection.fields['geometry.cylinder.'+axis+'range']==(-(4+2*n)/2,(4+2*n)/2)


def test_source_map_links_native_history_error_to_input_and_outer_assignment(tmp_path):
    spec=definition();history=render_history(spec)[0];macro=render_edit_macro(tmp_path,spec,'nonce')
    from csttool.history_program import partition
    mapping=checks.execution_definition_map(spec,partition(spec),macro)
    row=next(r for r in mapping['history'] if r['method']=='Zrange')
    raw='10576\nUnexpected text.\n[*check*#'+str(row['line']+3)+'] '+row['statement']+'\n'
    diagnostic=checks.map_native_error(raw,mapping,block_index=row['block_index'])
    assert diagnostic['origin']['input_field']=='cylinder.axial_range' and diagnostic['column'] is None
    outer=next(r for r in mapping['outer'] if r['history_lines']==[row['line']] and r.get('block_index')==row['block_index'])
    assert 'history = history &' in macro.splitlines()[outer['line_start']-1]
    description=next(r for r in mapping['outer'] if r['input_field']=='parameters.R.description')
    assert 'message = ""' in macro.splitlines()[description['line_start']-1]
    assert checks.map_native_error('1\nunknown\nunknown Source',mapping)['origin'] is None


def test_gate_requires_exact_current_sources_and_never_upgrades_unknown_evidence():
    sources={'source':'a'*64}
    record=dict(profile=checks.PROFILE,accepted=True,sources=sources,axes=['x','y','z'],
                solver_start_calls=0,standard_closed=True)
    checks.check_calibration(record,sources)
    for key,value in [('accepted',False),('sources',{}),('axes',['z']),('solver_start_calls',1),('standard_closed',False)]:
        changed={**record,key:value}
        with pytest.raises(GeneratedCodeError):checks.check_calibration(changed,sources)


@pytest.mark.parametrize('description',['emoji \U0001f600',' leading','trailing ','\ud800'])
def test_unpreserved_description_forms_rejected_without_normalizing(description):
    from csttool.definition_editing import check_spec
    spec=definition();spec['parameters']['R']['description']=description
    with pytest.raises(ValueError,match='UNSUPPORTED_CAPABILITY'):check_spec(spec)


@pytest.mark.parametrize('name',['MacroCheckThis','ErrObject','CSTToolsCheckCode','CSTToolsCheckError'])
def test_new_native_checker_symbols_cannot_be_shadowed(name):
    from csttool.winwrap_emitter import validate_parameter_names
    with pytest.raises(GeneratedCodeError):validate_parameter_names([name])


def test_runtime_gate_binds_local_evidence_and_rejects_stale_or_missing_records(tmp_path,monkeypatch):
    import hashlib,json
    from csttool.configuration import write_json_atomic
    # Synthetic fixture only: never writes the repository's production stamp.
    fingerprint={'synthetic-fixture':'a'*64}
    monkeypatch.setattr(checks,'ROOT',tmp_path)
    monkeypatch.setattr(checks,'generator_fingerprint',lambda:fingerprint)
    monkeypatch.setattr(checks,'LOADED_SOURCES',fingerprint)
    path=tmp_path/'data/winwrap-a1-calibration.json';path.parent.mkdir()
    with pytest.raises(GeneratedCodeError):checks.require_calibration()
    evidence=dict(accepted=True,sources=fingerprint)
    digest=hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    record=dict(profile=checks.PROFILE,accepted=True,sources=fingerprint,axes=['x','y','z'],solver_start_calls=0,
                standard_closed=True,evidence_file='knowledge-base/winwrap-w23-20261103.json',evidence_sha256=digest)
    write_json_atomic(path,record)
    proof=tmp_path/record['evidence_file'];proof.parent.mkdir()
    write_json_atomic(proof,{'native_acceptance':evidence})
    assert checks.require_calibration()==record
    write_json_atomic(proof,{'native_acceptance':{**evidence,'accepted':False}})
    with pytest.raises(GeneratedCodeError,match='evidence'):checks.require_calibration()
    monkeypatch.setattr(checks,'LOADED_SOURCES',{})
    with pytest.raises(GeneratedCodeError,match='changed'):checks.require_calibration()
