"""Fixed-template fake peer/receipt tests, never a WinWrap interpreter or CST proof."""
from copy import deepcopy
import hashlib
import json
import re

import pytest

from csttool.application_service import ServiceError
from csttool.definition_editing import (prepare_candidate_artifacts, read_failure_context,
    validate_candidate_completion, build_candidate)
from csttool.native_definition_builder import inject_definition_ownership, WRAPPER
from csttool.settings_projection import GEOMETRY_PROFILE, PROFILE
from csttool.winwrap_checks import check_module
from csttool.winwrap_emitter import GeneratedCodeError
from test.geometry_codegen_test import spec
from test.saved_project_source_test import container
from test.support.calibrate_winwrap_gate import spec_for


def string_value(expression, variables):
    """Decode emitted literal/ChrW/concatenation only; arbitrary VB is rejected."""
    parts=re.split(r'\s+&\s+(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)',expression)
    values=[]
    for part in parts:
        part=part.strip()
        if re.fullmatch(r'"(?:[^"]|"")*"',part):values.append(part[1:-1].replace('""','"'))
        elif match:=re.fullmatch(r'ChrW\((-?\d+)\)',part):values.append(chr(int(match[1])%65536))
        elif part=='vbCrLf':values.append('\r\n')
        elif part in variables:values.append(variables[part])
        else:raise AssertionError('outside fake peer string subset: '+part)
    return ''.join(values)


def run_fake(bundle, model, fault=None, fault_index=0):
    """Observe actual emitted assignments and ordered host calls; inject a host fault.

    This deliberately implements no general control flow or native API semantics.
    Receipt handling is tested separately against the production reader below.
    """
    variables={};parameters={};descriptions={};checked=[];applied=[];events=[]
    directory=bundle['directory']
    for line in bundle['macro'].split('Failed:',1)[0].splitlines():
        stripped=line.strip()
        if match:=re.fullmatch(r'(names\(\d+\)|expressions\(\d+\)|history|message|CSTToolsCaption|CSTToolsStage) = (.*)',stripped):
            variables[match[1]]=string_value(match[2],variables)
        elif match:=re.fullmatch(r'(CSTToolsBlockIndex|CSTToolsLastApplied) = (-?\d+)',stripped):
            variables[match[1]]=int(match[2])
        event=None
        if stripped=='StoreParameters(names, expressions)':
            event='parameters'
            parameters={variables[f'names({i})']:variables[f'expressions({i})'] for i in range(len(model['parameters']))}
        elif match:=re.fullmatch(r'SetParameterDescription (".*"), message',stripped):
            event='parameter-descriptions';descriptions[string_value(match[1],variables)]=variables['message']
        elif stripped=='Set CSTToolsCheckError = MacroCheckThis(CSTToolsCheckCode)':
            event='history-check';checked.append(variables['history'])
        elif stripped.startswith('If Not AddToHistory('):
            event='history-apply'
            assert checked[-1]==variables['history']
        elif stripped.startswith('If Not Rebuild Then'):event='rebuild'
        elif stripped.startswith('SaveAs '):event='save'
        if event:
            events.append(event)
            index=variables.get('CSTToolsBlockIndex',-1)
            if event==fault and (event not in ('history-check','history-apply') or index==fault_index):
                context=['1',bundle['descriptor']['nonce'],variables['CSTToolsStage'],str(index),
                         str(variables['CSTToolsLastApplied']),variables['CSTToolsCaption']]
                (directory/'failure-context.tsv').write_text('\n'.join(context)+'\n',encoding='ascii')
                (directory/'failed.txt').write_text('controlled host fault',encoding='ascii')
                if event=='history-check':
                    statement=variables['history'].splitlines()[0]
                    (directory/'history-syntax-error.txt').write_text('1\nsyntax\n[Macro#4] '+statement,encoding='ascii')
                break
            if event=='history-apply':applied.append(variables['history'])
            if event=='save':
                rows=[dict(name=name,expr=expr,descr=descriptions[name]) for name,expr in parameters.items()]
                bundle['model_path'].write_bytes(container([('Model/Parameters.json',json.dumps(dict(parameters=rows)).encode())]))
                (directory/'completed.txt').write_text(bundle['descriptor']['nonce'],encoding='ascii')
    return dict(variables=variables,parameters=parameters,descriptions=descriptions,checked=checked,applied=applied,events=events)


@pytest.mark.parametrize('axis',list('xyz'))
def test_shared_macro_payload_order_and_exact_parameter_persistence(tmp_path,axis):
    model=spec();model['geometry']['features'][1]['axis']=axis
    model['parameters']['R']['description']='半径 "R" & details'
    bundle=prepare_candidate_artifacts(tmp_path/'bundle',model,'a'*32)
    observed=run_fake(bundle,model)
    assert observed['parameters']=={k:v['expression'] for k,v in model['parameters'].items()}
    assert observed['descriptions']=={k:v['description'] for k,v in model['parameters'].items()}
    assert observed['checked']==observed['applied']
    assert [s.splitlines() for s in observed['checked']]==[r['history'].splitlines() for r in bundle['program']]
    assert observed['events'].count('parameters')==1
    assert observed['events'][-2:]==['rebuild','save']
    assert observed['events'].index('parameters')<observed['events'].index('history-check')
    assert validate_candidate_completion(bundle,model,dict(exit_confirmed=True,exit_code=0)).scope=='root'
    assert not list(bundle['directory'].glob('*intent*'))
    assert not json.loads((bundle['directory']/'generation.json').read_text())['native_dispatched']
    assert all(word not in bundle['macro'] for word in ('Active3D','OpenFile','Quit','TerminateProcess'))


@pytest.mark.parametrize('phase,index', [('parameters',0),('parameter-descriptions',0),
    ('history-check',0),('history-check',1),('history-check',4),
    ('history-apply',0),('history-apply',1),('history-apply',4),('rebuild',0),('save',0)])
def test_fault_stops_later_blocks_and_retains_unpublished_facts(tmp_path,phase,index):
    model=spec();bundle=prepare_candidate_artifacts(tmp_path/'bundle',model,'b'*32)
    observed=run_fake(bundle,model,phase,index)
    context=read_failure_context(bundle['directory'],'b'*32,bundle['program'])
    assert context['phase']==phase
    assert len(observed['applied'])==(index if phase.startswith('history-') else
        len(bundle['program']) if phase in ('rebuild','save') else 0)
    assert not (bundle['directory']/'completed.txt').exists()
    with pytest.raises(ServiceError,match='GENERATED_CODE_INVALID' if phase=='history-check' else 'SETTING_UNVERIFIED'):
        validate_candidate_completion(bundle,model,dict(exit_confirmed=True,exit_code=0))
    if phase=='history-check':
        diagnostic=json.loads((bundle['directory']/'native-diagnostic.json').read_text())
        assert diagnostic['block_index']==index and diagnostic['origin']['block_index']==index


@pytest.mark.parametrize('result',[{},dict(exit_confirmed=False,exit_code=0),dict(exit_confirmed=True,exit_code=1),
    dict(exit_confirmed=True,exit_code=False),dict(exit_confirmed=True,exit_code=None)])
def test_completed_saved_parameters_do_not_replace_standard_closure(tmp_path,result):
    model=spec();bundle=prepare_candidate_artifacts(tmp_path/'bundle',model,'c'*32);run_fake(bundle,model)
    with pytest.raises(ServiceError,match='SETTING_UNVERIFIED'):validate_candidate_completion(bundle,model,result)


@pytest.mark.parametrize('mutation',['nonce','index','last','caption','phase','oversize','completed','failed-after-save'])
def test_stale_or_inconsistent_receipts_cannot_adopt_candidate(tmp_path,mutation):
    model=spec();bundle=prepare_candidate_artifacts(tmp_path/'bundle',model,'d'*32);run_fake(bundle,model)
    rows=['1','d'*32,'history-check','1','0',bundle['program'][1]['caption']]
    if mutation=='nonce':rows[1]='e'*32
    elif mutation=='index':rows[3]='999'
    elif mutation=='last':rows[4]='1'
    elif mutation=='caption':rows[5]=bundle['program'][2]['caption']
    elif mutation=='phase':rows[2]='unknown'
    elif mutation=='oversize':rows[5]='x'*8192
    elif mutation=='completed':(bundle['directory']/'completed.txt').write_text('old')
    else:(bundle['directory']/'failed.txt').write_text('failure after SaveAs')
    if mutation not in ('completed','failed-after-save'):
        (bundle['directory']/'failure-context.tsv').write_text('\n'.join(rows)+'\n')
    with pytest.raises(ServiceError,match='SETTING_UNVERIFIED'):validate_candidate_completion(bundle,model,dict(exit_confirmed=True,exit_code=0))


@pytest.mark.parametrize('mutation',['expression','description','extra','duplicate','missing'])
def test_saved_parameter_table_is_checked_exactly(tmp_path,mutation):
    model=spec();bundle=prepare_candidate_artifacts(tmp_path/'bundle',model,'e'*32);run_fake(bundle,model)
    rows=[dict(name=k,expr=v['expression'],descr=v['description']) for k,v in model['parameters'].items()]
    if mutation=='expression':rows[1]['expr']='20'
    elif mutation=='description':rows[0]['descr']='changed'
    elif mutation=='extra':rows.append(dict(name='extra',expr='1',descr=''))
    elif mutation=='duplicate':rows[1]=deepcopy(rows[0])
    else:rows.pop()
    bundle['model_path'].write_bytes(container([('Model/Parameters.json',json.dumps(dict(parameters=rows)).encode())]))
    with pytest.raises(ServiceError,match='SETTING_UNVERIFIED'):validate_candidate_completion(bundle,model,dict(exit_confirmed=True,exit_code=0))


@pytest.mark.parametrize('geometry',[True,False])
def test_owned_injection_binds_actual_macro_and_absolute_source_map(tmp_path,geometry):
    model=spec() if geometry else spec_for('z')
    bundle=prepare_candidate_artifacts(tmp_path/'bundle',model,'f'*32)
    macro,mapping=inject_definition_ownership(bundle['macro'],bundle['directory'],'0'*32,
        profile=GEOMETRY_PROFILE if geometry else PROFILE,mapping=bundle['mapping'])
    assert macro.index('CSTToolsStage = "ownership"')<macro.index('    CSTToolsBindNewProject\n')<macro.index('StoreParameters(names, expressions)')
    assert mapping['hashes']['final_outer']==hashlib.sha256(macro.encode('ascii')).hexdigest()
    before=bundle['macro'].splitlines();after=macro.splitlines()
    for original,shifted in zip(mapping['outer'],mapping['final_outer']):
        assert before[original['line_start']-1:original['line_end']]==after[shifted['line_start']-1:shifted['line_end']]
    with pytest.raises((ValueError,GeneratedCodeError)):
        inject_definition_ownership(macro,bundle['directory'],'0'*32,profile=bundle['descriptor']['profile'],mapping=mapping)
    bad=deepcopy(bundle['mapping']);bad['hashes']['outer']='wrong'
    with pytest.raises(ValueError,match='source map'):
        inject_definition_ownership(bundle['macro'],bundle['directory'],'0'*32,profile=bundle['descriptor']['profile'],mapping=bad)
    # Held-object cleanup is still in the existing wrapper, never emitted into history.
    assert '$project.Quit()' in WRAPPER and '$studio.Quit()' in WRAPPER


@pytest.mark.parametrize('mutation',['missing-check','missing-guard','duplicate-caption','early-save','late-parameters'])
def test_independent_outer_checker_rejects_broken_phase_contract(tmp_path,mutation):
    bundle=prepare_candidate_artifacts(tmp_path/'bundle',spec(),'1'*32);macro=bundle['macro']
    if mutation=='missing-check':macro=macro.replace('Set CSTToolsCheckError = MacroCheckThis(CSTToolsCheckCode)','Set CSTToolsCheckError = Nothing',1)
    elif mutation=='missing-guard':macro=macro.replace('If Not CSTToolsCheckError Is Nothing Then','If True Then',1)
    elif mutation=='duplicate-caption':macro=macro.replace(bundle['program'][1]['caption'],'CST Tools GEO setup')
    else:
        pattern=r'^    SaveAs .*\n' if mutation=='early-save' else r'^    StoreParameters\(names, expressions\)\n'
        line=re.search(pattern,macro,re.M)[0];macro=macro.replace(line,'',1)
        anchor='    StoreParameters(names, expressions)\n' if mutation=='early-save' else '    If Not Rebuild Then '
        macro=macro.replace(anchor,line+anchor,1)
    with pytest.raises(GeneratedCodeError):check_module(macro,profile=GEOMETRY_PROFILE)


def test_geo_artifact_preparation_cannot_bypass_publication_boundary(tmp_path,monkeypatch):
    from types import SimpleNamespace
    model=spec();bundle=prepare_candidate_artifacts(tmp_path/'bundle',model,'2'*32);run_fake(bundle,model)
    def missing(target):raise GeneratedCodeError('synthetic GEO calibration absent')
    monkeypatch.setattr('csttool.definition_editing.require_geometry_calibration',missing)
    with pytest.raises(GeneratedCodeError,match='GENERATED_CODE_INVALID'):
        build_candidate(SimpleNamespace(),{},model,'operation',None,None)
    assert not list(tmp_path.rglob('*intent*'))


def test_missing_block_identity_keeps_native_error_unresolved(tmp_path):
    model=spec();bundle=prepare_candidate_artifacts(tmp_path/'bundle',model,'3'*32)
    run_fake(bundle,model,'history-check',2)
    (bundle['directory']/'failure-context.tsv').unlink()
    with pytest.raises(ServiceError,match='GENERATED_CODE_INVALID'):
        validate_candidate_completion(bundle,model,dict(exit_confirmed=False))
    diagnostic=json.loads((bundle['directory']/'native-diagnostic.json').read_text())
    assert diagnostic['origin'] is None and diagnostic['block_index'] is None


@pytest.mark.parametrize('size',[0,128])
def test_parameter_batch_empty_and_budget_boundary(tmp_path,size):
    model=spec([dict(op='ensure_component',component_id='vacuum')]) if not size else spec()
    if size:
        for index in range(size-len(model['parameters'])):
            model['parameters']['p'+str(index)]=dict(expression='R/2',description=('参数 "值" '*25).rstrip(),quantity='length')
    bundle=prepare_candidate_artifacts(tmp_path/'bundle',model,'4'*32)
    observed=run_fake(bundle,model)
    assert len(observed['parameters'])==size
    assert observed['events'].count('parameters')==bool(size)
    validate_candidate_completion(bundle,model,dict(exit_confirmed=True,exit_code=0))
    assert max(map(len,bundle['macro'].splitlines()))<=800


@pytest.mark.parametrize('phase',['ownership','batch-return'])
def test_failure_before_binding_or_after_save_is_not_success(tmp_path,phase):
    model=spec();bundle=prepare_candidate_artifacts(tmp_path/'bundle',model,'5'*32);run_fake(bundle,model)
    index=-1 if phase=='ownership' else len(bundle['program'])-1
    caption='' if index<0 else bundle['program'][index]['caption']
    (bundle['directory']/'failure-context.tsv').write_text('\n'.join(['1','5'*32,phase,str(index),str(index),caption])+'\n')
    with pytest.raises(ServiceError,match='SETTING_UNVERIFIED'):
        validate_candidate_completion(bundle,model,dict(exit_confirmed=True,exit_code=0))
    assert read_failure_context(bundle['directory'],'5'*32,bundle['program'])['phase']==phase


def test_failure_handler_writes_phase_identity_and_original_error_before_cleanup(tmp_path):
    macro=prepare_candidate_artifacts(tmp_path/'bundle',spec(),'6'*32)['macro']
    handler=macro.split('Failed:',1)[1].split('End Sub',1)[0]
    assert handler.index('message = CStr(Err.Number)')<handler.index('On Error Resume Next')
    assert re.findall(r'^    Print #f, (.*)$',handler,re.M)==[
        '"1"','"'+'6'*32+'"','CSTToolsStage','CStr(CSTToolsBlockIndex)',
        'CStr(CSTToolsLastApplied)','CSTToolsCaption','message']


def test_w3_partial_injection_still_fails_before_rebuild_with_current_template(tmp_path,monkeypatch):
    from test.support import calibrate_winwrap_gate as probe
    captured=[]
    def fake_run(exe,model,directory,macro,**kwargs):
        assert kwargs==dict(generated_profile=PROFILE)
        captured.append(macro)
        marker='controlled failure after partial history'
        assert macro.index('CSTToolsStage = "rebuild"')<macro.index(marker)<macro.index('If Not Rebuild Then')
        (directory/'partial-step.txt').write_text('controlled')
        (directory/'failed.txt').write_text(marker)
        return dict(exit_confirmed=True,exit_code=0)
    monkeypatch.setattr(probe,'run_new_definition',fake_run)
    report=probe.negative(tmp_path,'unused-CST.exe','partial')
    assert len(captured)==1 and report['expected_failure'] and report['old_state_unchanged']
