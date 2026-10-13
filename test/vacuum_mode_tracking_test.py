from dataclasses import replace
import numpy as np
import pytest

from csttool.configuration import read_json, write_json_atomic
from csttool.field_artifacts import SamplingSpec
from csttool.mode_matching import MatchPolicy
from csttool.physical_domain import DomainSupport
from csttool.vacuum_mode_tracking import (
    VacuumTrackingDomain, TrackingSnapshot, VacuumModeTracker, select_vacuum_modes,
    load_tracking_snapshot, track_saved_sequence,
)
from test.field_artifacts_test import artifact


def domain():
    return VacuumTrackingDomain('cavity-v1', 'PEC', 'Vacuum', True,
                                'fixture boundary', 'fixture full box', 'fixture sampling')


def snapshot(tmp_path, name, vectors, modes=None):
    spec = SamplingSpec((0,1,0,1,0,1), (2,2,2), 'specified-domain')
    fields = tuple(artifact(tmp_path, f'{name}-{i}', mode=(modes or list(range(1,len(vectors)+1)))[i],
                            spec=spec, vector=v) for i,v in enumerate(vectors))
    support = DomainSupport(spec, ('Vacuum',)*8, 'cavity-v1', 'fixture', True)
    return TrackingSnapshot(name, fields, support)


def policy():
    return MatchPolicy(.9, .05, .99, maximum_frequency_change=.01)


def test_single_mode_tracks_changed_number_and_rejects_frequency(tmp_path):
    ref = snapshot(tmp_path,'ref',[(1,0,0)])
    candidate = snapshot(tmp_path,'next',[(0,1,0),(2j,0,0)],modes=[1,7])
    result = select_vacuum_modes(ref,candidate,domain(),policy())
    assert result['status']=='matched' and result['selected_modes']==[7]
    wrong = replace(candidate,fields=tuple(replace(f,frequency_hz=600e6) for f in candidate.fields))
    assert select_vacuum_modes(ref,wrong,domain(),policy())['status']=='unconfirmed'


def test_doublet_rotation_extra_candidate_and_swap(tmp_path):
    ref = snapshot(tmp_path,'ref',[(1,0,0),(0,1,0)])
    cand = snapshot(tmp_path,'rotated',[(1,1,0),(-1,1,0),(0,0,1)],modes=[4,2,9])
    result = select_vacuum_modes(ref,cand,domain(),policy())
    assert result['status']=='matched' and result['selected_modes']==[4,2]
    assert result['group']['minimum_squared_overlap']==pytest.approx(1)
    assert not result['member_identity_confirmed']
    swapped = replace(cand,fields=cand.fields[::-1])
    assert set(select_vacuum_modes(ref,swapped,domain(),policy())['selected_modes'])=={4,2}


@pytest.mark.parametrize('vectors,reason',[
    ([(1,0,0)],'missing-candidates'),
    ([(1,0,0),(1,0,0)],'no-eligible-subspace'),
    ([(1,0,0),(0,1,0),(1,0,0)],'ambiguous-subspace'),
])
def test_group_missing_rank_and_ambiguity(tmp_path,vectors,reason):
    ref=snapshot(tmp_path,'ref',[(1,0,0),(0,1,0)])
    result=select_vacuum_modes(ref,snapshot(tmp_path,'bad',vectors),domain(),policy())
    assert result['status']=='unconfirmed' and result['reason']==reason


def test_failure_does_not_promote_reference_and_recovers(tmp_path):
    ref=snapshot(tmp_path,'ref',[(1,0,0)])
    tracker=VacuumModeTracker(ref,domain(),policy())
    bad=snapshot(tmp_path,'bad',[(0,1,0)])
    assert tracker.evaluate(bad,tmp_path/'bad.json')['status']=='unconfirmed'
    good=snapshot(tmp_path,'good',[(1j,0,0)])
    assert tracker.evaluate(good,tmp_path/'good.json')['status']=='matched'
    good.fields[0].path.unlink()
    assert tracker.evaluate(good,tmp_path/'missing.json')['status']=='unconfirmed'
    assert tracker.reference is ref
    assert read_json(tmp_path/'missing.json')['selected_modes']==[]


@pytest.mark.parametrize('change',[
    {'background':'Vacuum'}, {'interior':'Dielectric'}, {'closed':False}, {'coverage_evidence':''},
])
def test_reject_unsupported_domain(change):
    with pytest.raises(ValueError): replace(domain(),**change)


def test_reject_geometry_mask_roi_and_missing_frequency_gate(tmp_path):
    ref=snapshot(tmp_path,'ref',[(1,0,0)])
    cand=snapshot(tmp_path,'next',[(1,0,0)])
    for support in (replace(cand.support,geometry_id='changed'),
                    replace(cand.support,material_labels=('Dielectric',)*8),
                    replace(cand.support,material_labels=('excluded',)*8)):
        with pytest.raises(ValueError): select_vacuum_modes(ref,replace(cand,support=support),domain(),policy())
    roi=replace(cand.support,sampling=replace(cand.support.sampling,scope='roi-probe'))
    with pytest.raises(ValueError): select_vacuum_modes(ref,replace(cand,support=roi),domain(),policy())
    with pytest.raises(ValueError): VacuumModeTracker(ref,domain(),MatchPolicy(.9,.05,.99))


def descriptor(tmp_path,snap):
    from csttool.result_reconciliation import file_hash
    support_file=tmp_path/f'{snap.snapshot_id}.tsv'
    support_file.write_text('\n'.join(snap.support.material_labels)+'\n')
    fields=[]
    for f in snap.fields:
        fields.append({'value':{'kind':'field-artifact','status':'available','field_kind':'E',
            'filename':f.path.name,'mode':f.mode,'frequency_hz':f.frequency_hz,'sha256':f.file_sha256,
            'support_verified':True,'coordinates_unit':'m','raw_coordinate_scale_to_m':1,
            'raw_coordinate_unit':'m','sampling':f.sampling.to_mapping()}})
    result_file=tmp_path/f'{snap.snapshot_id}.json'
    write_json_atomic(result_file,{'ResultDirectory':str(tmp_path),'FieldArtifacts':fields})
    return {'snapshot_id':snap.snapshot_id,'result_file':result_file.name,
            'support_file':support_file.name,'support_sha256':file_hash(support_file)}


def test_saved_sequence_recovers_without_solver(tmp_path):
    from dataclasses import asdict
    ref=descriptor(tmp_path,snapshot(tmp_path,'ref',[(1,0,0)]))
    good=descriptor(tmp_path,snapshot(tmp_path,'good',[(1,0,0)]))
    bad={**good,'snapshot_id':'missing','result_file':'absent.json'}
    request=tmp_path/'request.json'
    write_json_atomic(request,{'domain':asdict(domain()),'policy':asdict(policy()),
                              'reference':ref,'candidates':[bad,good]})
    decisions=track_saved_sequence(request,tmp_path/'reports')
    assert [d['status'] for d in decisions]==['unconfirmed','matched']
    assert read_json(tmp_path/'reports/summary.json')['solver_replayed'] is False
    assert load_tracking_snapshot(good,domain(),base=tmp_path).snapshot_id=='good'


def test_persistence_failure_propagates(tmp_path,monkeypatch):
    snap=snapshot(tmp_path,'ref',[(1,0,0)])
    def full(*args): raise OSError('disk full')
    monkeypatch.setattr('csttool.vacuum_mode_tracking.write_json_atomic',full)
    with pytest.raises(OSError): VacuumModeTracker(snap,domain(),policy()).evaluate(snap,tmp_path/'report.json')


def test_invalid_anchor_is_rejected_before_sequence(tmp_path):
    ref=snapshot(tmp_path,'ref',[(1,0,0),(1,0,0)])
    with pytest.raises(ValueError,match='rank-deficient'): VacuumModeTracker(ref,domain(),policy())
    single=snapshot(tmp_path,'single',[(1,0,0)])
    single.fields[0].path.unlink()
    with pytest.raises(FileNotFoundError): VacuumModeTracker(single,domain(),policy())


def test_cli_success_and_unconfirmed_exit_codes(tmp_path):
    from dataclasses import asdict
    from pathlib import Path
    import subprocess
    import sys
    desc=descriptor(tmp_path,snapshot(tmp_path,'ref',[(1,0,0)]))
    candidate=descriptor(tmp_path,snapshot(tmp_path,'candidate',[(1j,0,0)]))
    request=tmp_path/'request.json'
    payload={'domain':asdict(domain()),'policy':asdict(policy()),'reference':desc,'candidates':[candidate]}
    write_json_atomic(request,payload)
    command=[sys.executable,'-m','csttool.vacuum_mode_tracking','--request',str(request),
             '--output',str(tmp_path/'reports')]
    assert subprocess.run(command,cwd=Path(__file__).parents[1],capture_output=True,timeout=20).returncode==0
    payload['candidates'][0]['result_file']='missing.json'
    write_json_atomic(request,payload)
    assert subprocess.run(command,cwd=Path(__file__).parents[1],capture_output=True,timeout=20).returncode==2
    assert read_json(tmp_path/'reports/summary.json')['status']=='unconfirmed'


def test_small_mesh_acceptance_wrapper_replays_only_fields(tmp_path):
    from test.support.validate_pillbox_cross_mesh import validate_tracker
    import shutil
    for cell in (8,10):
        fields=tmp_path/f'mesh-{cell}/fields'
        fields.mkdir(parents=True)
        snap=snapshot(fields,f'cell-{cell}',[(1,0,0),(0,1,0)])
        desc=descriptor(fields,snap)
        shutil.copy2(fields/desc['result_file'],fields/'export-result.json')
        support=tmp_path/f'mesh-{cell}/support'
        support.mkdir()
        shutil.copy2(fields/desc['support_file'],support/'support.tsv')
    write_json_atomic(tmp_path/'report.json',{'meshes':[{'cell':8},{'cell':10}],'gate_passed':True})
    validate_tracker(tmp_path)
    report=read_json(tmp_path/'report.json')['tracker_acceptance']
    assert report['gate_passed'] and report['solver_replayed_for_recovery'] is False
    assert not list(tmp_path.rglob('*.quarantined'))
