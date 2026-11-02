from pathlib import Path
import re
import pytest
from csttool.definition_verifier import NativeDefinitionVerifier
from test.single_simulation_service_test import make_service


def peer(executable, model, directory, macro):
    assert 'EigenmodeSolver.Start' not in macro and 'AddToHistory' not in macro
    nonce=re.search(r'"nonce" & Chr\(9\) & "([a-f0-9]+)"',macro)[1]
    rows=dict(nonce=nonce,project=str(model.with_suffix('')),build='Version 2022.5 - Jun 03 2022',
              solver='HF Eigenmode',length='mm',frequency='MHz',mesh='Tetrahedral',fmin='500',fmax='1000',end='G03V1')
    (directory/'identity.tsv').write_text(''.join(k+'\t'+v+'\n' for k,v in rows.items()),encoding='ascii')
    (directory/'completed.txt').write_text(nonce)
    from csttool.saved_project_source import read_saved_source
    from csttool.settings_projection import project_saved_settings
    from csttool.definition_geometry import geometry_expectation
    geometry=geometry_expectation(project_saved_settings(read_saved_source(model,scope='root')))
    observed=dict(nonce=nonce,project=str(model.with_suffix('')),solid=geometry['solid'],exists='True',material='Vacuum',
                  volume_mm3=str(geometry['volume_mm3']))
    for key,value in geometry['bounds_mm'].items():
        observed[key+'_mm']=str(value);observed['calculation_'+key+'_mm']=str(value);observed['boundary.'+key]='electric'
    (directory/'geometry.tsv').write_text(''.join(k+'\t'+v+'\n' for k,v in observed.items()),encoding='ascii')
    return dict(exit_code=0,exit_confirmed=True)


def test_default_registration_does_not_launch(tmp_path):
    service,_,record=make_service(tmp_path,verified=False)
    assert isinstance(service.definition_verifier,NativeDefinitionVerifier)
    assert not record['ready']


def test_explicit_two_session_verification(tmp_path):
    service,payload,record=make_service(tmp_path,verified=False)
    calls=[]
    def run(*args):
        calls.append(args[1]);return peer(*args)
    service.definition_verifier=NativeDefinitionVerifier(runner=run)
    result=service.verify_definition(payload['document_id'],payload['definition_revision'])
    assert result['ready'] and len(calls)==2
    assert calls[0]!=calls[1]
    assert service.preflight(payload)['verification']['status']=='verified'


@pytest.mark.parametrize('fault',['close','nonce','frequency','expressions','error','duplicate'])
def test_failure_never_marks_ready(tmp_path,fault):
    service,payload,record=make_service(tmp_path,verified=False)
    def run(exe,model,directory,macro):
        result=peer(exe,model,directory,macro)
        p=directory/'identity.tsv'
        if fault=='close':result['exit_confirmed']=False
        if fault=='nonce':(directory/'completed.txt').write_text('stale')
        if fault=='frequency':p.write_text(p.read_text().replace('fmin\t500','fmin\t700'))
        if fault=='expressions':model.write_bytes(b'broken')
        if fault=='error':(directory/'failed.txt').write_text('save failed')
        if fault=='duplicate':p.write_text(p.read_text()+'solver\tHF Eigenmode\n')
        return result
    service.definition_verifier=NativeDefinitionVerifier(runner=run)
    with pytest.raises(ValueError):
        service.verify_definition(payload['document_id'],payload['definition_revision'])
    assert not service.inspect_definition(payload['document_id'],payload['definition_revision'])['ready']


def test_failed_reverification_revokes_prior_readiness(tmp_path):
    service,payload,_=make_service(tmp_path,verified=True)
    def fail(*args):raise ValueError('native failed')
    service.definition_verifier=fail
    with pytest.raises(ValueError):service.verify_definition(payload['document_id'],payload['definition_revision'])
    assert not service.inspect_definition(payload['document_id'],payload['definition_revision'])['ready']


def test_unconfirmed_close_blocks_next_verification(tmp_path):
    service,payload,_=make_service(tmp_path,verified=False)
    calls=[]
    def fail(*args):
        calls.append(1)
        result=peer(*args);result['exit_confirmed']=False;return result
    service.definition_verifier=NativeDefinitionVerifier(runner=fail)
    for _ in range(2):
        with pytest.raises(ValueError):service.verify_definition(payload['document_id'],payload['definition_revision'])
    assert len(calls)==1


def test_native_probe_language_directive_is_wwb_comment(tmp_path):
    from csttool.definition_verifier import render_definition_probe
    macro=render_definition_probe(tmp_path/'copy.cst',tmp_path,'a'*32)
    assert macro.startswith("'#Language ")
    assert 'EigenmodeSolver.Start' not in macro
    from test.support.validate_single_simulation import render_model
    assert render_model(tmp_path).startswith("'#Language ")
