"""O1-O8 functional history/managed-source tests; no native execution."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from csttool.history_program import partition,validate,logical_geometry
from csttool.managed_history import extract_program,verify_saved_program
from csttool.definition_editing import changed_spec
from csttool.definition_geometry import geometry_objects,verify_managed_geometry_observation
from csttool.saved_project_source import read_saved_source
from csttool.winwrap_emitter import GeneratedCodeError
from test.geometry_codegen_test import spec as geometry_spec
from test.definition_editing_test import configuration
from test.support.calibrate_winwrap_gate import spec_for
from test.saved_project_source_test import container


def simulation_spec():
    model=geometry_spec()
    model=changed_spec(dict(spec=model),dict(operation='apply_model_changes',geometry_profile='geometry-v1',changes=[
        dict(op='set_background',material='PEC',padding_mm=[0]*6),
        dict(op='set_boundaries',faces=['electric']*6,symmetry=['none']*3)]))
    return changed_spec(dict(spec=model),dict(operation='configure_simulation',**configuration()))


def saved(tmp_path,model,program=None):
    program=partition(model) if program is None else program
    text="'# MWS Version: Version 2022.5\n\n"+'\n'.join("'@ "+b['caption']+"\n'[VERSION]2022.5[/VERSION]\n"+b['history']+'\n' for b in program)
    rows=[dict(name=k,expr=v['expression'],descr=v['description']) for k,v in model['parameters'].items()]
    path=tmp_path/'definition.cst';path.write_bytes(container([('Model/3D/Model.mod',text.encode()),
        ('Model/Parameters.json',json.dumps(dict(parameters=rows)).encode())]))
    return read_saved_source(path,scope='root')


@pytest.mark.parametrize('kind',['a1','geometry','simulation'])
def test_partition_has_unique_owners_and_actual_persisted_program_roundtrip(tmp_path,kind):
    model=spec_for('z') if kind=='a1' else geometry_spec() if kind=='geometry' else simulation_spec()
    before=deepcopy(model);program=partition(model);contracts=validate(program,model)
    writes=[key for row in contracts for key in row['writes']]
    assert len(writes)==len(set(writes)) and model==before
    assert all(b['caption']!='CST Tools GEO setup' and b['caption']!='CST Tools A1 typed definition' for b in program)
    source=saved(tmp_path,model,program);report=verify_saved_program(source,model)
    assert report.status=='resolved' and not report.missing_fields and not report.publish_ready
    assert len(extract_program(source))==len(program)


@pytest.mark.parametrize('kind',['a1','simulation'])
@pytest.mark.parametrize('fault',['duplicate-setter','duplicate-owner','late-reset','split-create','missing-mode'])
def test_conflicting_or_incomplete_blocks_reject_before_execution(kind,fault):
    model=spec_for('z') if kind=='a1' else simulation_spec();program=deepcopy(list(partition(model)))
    prefix='CST Tools A1 ' if kind=='a1' else 'CST Tools SIM '
    row=next(b for b in program if b['caption']==prefix+'modes')
    if fault=='duplicate-setter':row['history']+='\n'+row['history']
    elif fault=='duplicate-owner':program.append(dict(caption=prefix+'extra',history=row['history']))
    elif fault=='late-reset':program.append(dict(caption=prefix+'reset-late',history='EigenmodeSolver.Reset'))
    elif fault=='missing-mode':program.remove(row)
    else:
        target=next(b for b in program if 'With Cylinder' in b['history'] or 'With Brick' in b['history'])
        target['history']=target['history'].rsplit(' .Create',1)[0]+'\nEnd With'
        program.append(dict(caption=prefix+'finish-create',history='Cylinder.Create'))
    with pytest.raises((GeneratedCodeError,ValueError)):validate(program,model)


def test_update_settings_keeps_one_owner_and_old_revision_unmodified():
    model=spec_for('z');before=deepcopy(model)
    for minimum in (600,700,800):
        model=deepcopy(model);model['simulation']['frequency_lower_target_mhz']=minimum
        model['simulation']['frequency_range_mhz']['min']=minimum
    program=partition(model)
    assert sum(b['caption'].endswith(' frequency') for b in program)==1
    assert '"800"' in next(b['history'] for b in program if b['caption'].endswith(' frequency'))
    assert before['simulation']['frequency_lower_target_mhz']==500


@pytest.mark.parametrize('fault',['forward','component-late','wcs-local','missing-units','dangling-tool'])
def test_explicit_dependency_and_environment_checks(fault):
    model=geometry_spec();program=deepcopy(list(partition(model)))
    if fault=='forward':program[3],program[5]=program[5],program[3]
    elif fault=='component-late':program[2],program[3]=program[3],program[2]
    elif fault=='wcs-local':program[1]['history']=program[1]['history'].replace('global','local')
    elif fault=='missing-units':program.pop(0)
    else:program.pop(4)
    with pytest.raises((GeneratedCodeError,ValueError)):validate(program,model)


@pytest.mark.parametrize('fault',['duplicate-caption','unknown-caption','body-added','constant-substitution','changed-order','extra-setting'])
def test_saved_history_never_folds_duplicate_or_unknown_blocks(tmp_path,fault):
    model=geometry_spec();program=deepcopy(list(partition(model)))
    if fault=='duplicate-caption':program.append(deepcopy(program[0]))
    elif fault=='unknown-caption':program[0]['caption']='user history'
    elif fault=='body-added':program[-1]['history']+='\nMsgBox "unexpected"'
    elif fault=='constant-substitution':program[3]['history']=program[3]['history'].replace('RestoreDoubleParameter("H")','20')
    elif fault=='changed-order':program[3],program[4]=program[4],program[3]
    else:program.append(dict(caption='CST Tools GEO override',history='WCS.ActivateWCS "local"'))
    with pytest.raises((GeneratedCodeError,ValueError)):verify_saved_program(saved(tmp_path,model,program),model)


@pytest.mark.parametrize('fault',[None,'nonce','count','material','hybrid','volume','exists'])
def test_observation_verifies_independent_native_facts(tmp_path,fault):
    from test.support.calibrate_geometry import specimen
    model=specimen();obj=geometry_objects(model)[0];path=tmp_path/'geometry.tsv';cst=tmp_path/'definition.cst'
    rows=dict(nonce='nonce',project=str(cst.with_suffix('')),count='1',end='GEO1')
    rows.update({kind+'.'+a+side:str(value) for kind in ('bounds','calculation') for a in 'xyz' for side,value in (('min',-10),('max',10))})
    rows.update({'solid.0.name':obj['native_name'],'solid.0.exists':'True','solid.0.material':'Vacuum',
                 'solid.0.hybrid':'False','solid.0.solid':'True','solid.0.volume_mm3':'8000'})
    key={'nonce':'nonce','count':'count','material':'solid.0.material','hybrid':'solid.0.hybrid',
         'volume':'solid.0.volume_mm3','exists':'solid.0.exists'}.get(fault)
    if key:rows[key]={'hybrid':'True','volume':'nan','exists':'False','count':'2'}.get(fault,'wrong')
    path.write_text('\n'.join(k+'\t'+v for k,v in rows.items()),encoding='ascii')
    if fault:
        with pytest.raises(ValueError):verify_managed_geometry_observation(path,model,cst,'nonce')
    else:assert verify_managed_geometry_observation(path,model,cst,'nonce')['status']=='verified'
