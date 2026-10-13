from dataclasses import replace
from pathlib import Path
import json
import numpy as np
import pytest
from csttool.field_artifacts import (SamplingSpec,FieldArtifact,read_field,read_export_status,
                                    artifacts_from_result)
from csttool.field_diagnostics import compare_fields,run_field_diagnostic
from csttool.mode_matching import MatchPolicy
from csttool.result_reconciliation import file_hash

h5py=pytest.importorskip('h5py')


def artifact(tmp_path,name='a',mode=1,spec=None,vector=(1,0,0)):
    spec=spec or SamplingSpec((0,1,0,1,0,1),(2,2,2))
    path=tmp_path/f'{name}.h5'
    fields=np.zeros(len(spec.points()),dtype=[(axis,[('re','f4'),('im','f4')]) for axis in 'xyz'])
    positions=np.zeros(len(fields),dtype=[(axis,'f8') for axis in 'xyz'])
    for index,axis in enumerate('xyz'):
        fields[axis]['re']=np.real(vector[index]);fields[axis]['im']=np.imag(vector[index])
        positions[axis]=spec.points()[:,index]
    with h5py.File(path,'w') as stream:
        stream['E-Field']=fields;stream['Position']=positions
    return FieldArtifact(path,spec,mode,500e6,'E',file_hash(path),True)


def test_reads_verified_si_complex_field(tmp_path):
    a=artifact(tmp_path,vector=(1+2j,3,4j))
    assert np.allclose(read_field(a),[1+2j,3,4j])
    assert sum(a.sampling.weights())==pytest.approx(1)


@pytest.mark.parametrize('change',[{'support_verified':False},{'coordinates_unit':'mm'},{'mode':0}])
def test_invalid_support_units_identity(tmp_path,change):
    a=artifact(tmp_path)
    with pytest.raises(ValueError): read_field(replace(a,**change))


def test_coordinates_hash_and_truncated_hdf_rejected(tmp_path):
    a=artifact(tmp_path)
    with h5py.File(a.path,'r+') as stream:
        p=stream['Position'][...];p['x']+=0.1;stream['Position'][...]=p
    with pytest.raises(ValueError,match='hash'):read_field(a)
    with pytest.raises(ValueError,match='coordinates'):read_field(replace(a,file_sha256=file_hash(a.path)))
    a.path.write_bytes(b'truncated')
    with pytest.raises(OSError):read_field(replace(a,file_sha256=file_hash(a.path)))


def test_optional_failed_export_and_recovery(tmp_path):
    a=artifact(tmp_path)
    status=a.path.with_suffix('.status')
    status.write_text('FAILURE disk full\n')
    assert read_export_status(status,a.sampling,1,'E')['status']=='unavailable'
    status.write_text('SUCCESS\n500000000\n0\n1\nm\n')
    value=read_export_status(status,a.sampling,1,'E')
    assert value['status']=='available'
    group=artifacts_from_result(tmp_path,[{'value':value}])
    assert compare_fields(group,group,MatchPolicy(.9,.05,.99))['members']['status']=='matched'
    foreign={**value,'filename':'../foreign.h5'}
    with pytest.raises(ValueError):artifacts_from_result(tmp_path,[{'value':foreign}])


def test_sampling_mismatch_and_repeated_mode_rejected(tmp_path):
    a=artifact(tmp_path)
    b=artifact(tmp_path,'b',spec=SamplingSpec((0,2,0,1,0,1),(2,2,2)))
    with pytest.raises(ValueError,match='mismatch'):compare_fields([a],[b],MatchPolicy(.9,.05,.99))
    with pytest.raises(ValueError,match='duplicate'):compare_fields([a,a],[a,a],MatchPolicy(.9,.05,.99))


def test_diagnostic_failure_cancellation_and_resume_no_solver(tmp_path):
    a=artifact(tmp_path)
    path=tmp_path/'diagnostic.json'
    bad=replace(a,file_sha256='foreign')
    assert run_field_diagnostic([bad],[a],MatchPolicy(.9,.05,.99),path)['status']=='incomplete'
    result=run_field_diagnostic([a],[a],MatchPolicy(.9,.05,.99),path)
    assert result['status']=='complete' and result['physical_identity_confirmed'] is False
    assert json.loads(path.read_text())['status']=='complete'
    assert run_field_diagnostic([a],[a],MatchPolicy(.9,.05,.99),path,cancelled=lambda:True)['status']=='cancelled'


def test_persistence_failure_not_success(tmp_path,monkeypatch):
    a=artifact(tmp_path)
    def full(*args):raise OSError('disk full')
    monkeypatch.setattr('csttool.field_diagnostics.write_json_atomic',full)
    with pytest.raises(OSError):run_field_diagnostic([a],[a],MatchPolicy(.9,.05,.99),tmp_path/'report.json')


def test_registered_export_safe_names_and_no_parameter_update(tmp_path):
    from csttool.postprocess_cst import CstPostProcessor
    p=CstPostProcessor()
    spec=SamplingSpec((0,1,0,1,0,1),(2,2,2))
    p.configure([{'method':'ExportModeField','resultName':'../../foreign',
                  'params':{'iModeNumber':2,'sampling':spec.to_mapping()}}])
    p.set_result_directory(tmp_path)
    assert p.read_all_results()[0]['value']['status']=='unavailable'
    vb=''.join(p.render_vb())
    assert 'StoreParameter' not in vb and 'Rebuild' not in vb
    assert '.ExportCoordinatesInMeter False' in vb
    assert 'Units.GetGeometryUnitToSI' in vb
    assert 'GetListItem' in vb and '.partial.h5' in vb
    assert Path(p.getUsedFileNameList()[0]).name==p.getUsedFileNameList()[0]


def test_foreign_task_identity_rejected(tmp_path):
    a=artifact(tmp_path)
    status=a.path.with_suffix('.status');status.write_text('SUCCESS\n500000000\n0\n1\nm\n')
    value=read_export_status(status,a.sampling,1,'E')
    value['context']={'task_id':'old','session_id':'old-session'}
    with pytest.raises(ValueError,match='identity'):
        artifacts_from_result(tmp_path,[{'value':value}],expected_context={'task_id':'new'})


def test_mm_coordinates_explicit_scale_not_guessed(tmp_path):
    a=artifact(tmp_path)
    with h5py.File(a.path,'r+') as stream:
        positions=stream['Position'][...]
        for axis in 'xyz':positions[axis]*=1000
        stream['Position'][...]=positions
    a=replace(a,file_sha256=file_hash(a.path))
    with pytest.raises(ValueError):read_field(a)
    assert read_field(replace(a,raw_coordinate_scale_to_m=.001,raw_coordinate_unit='mm')).shape==(8,3)
