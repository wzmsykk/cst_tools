from pathlib import Path
import pytest
from csttool.configuration import write_json_atomic,read_json
from csttool.vacuum_domain_registry import validate_managed_domain_options
from test.vacuum_mode_tracking_test import snapshot,descriptor,policy
from test.managed_cstworker_test import build_worker_shell
from dataclasses import asdict


def setup_worker(tmp_path):
    worker=build_worker_shell(tmp_path)
    worker._vacuum_domain={'geometry_id':'cavity-v1','matching':{
        'reference_strategy':'first-valid','policy':asdict(policy()),'sampling_evidence':'fixture'}}
    worker._vacuum_reference_store=tmp_path/'anchor.json'
    worker.run_store=None
    return worker


def candidate(tmp_path,name,vector):
    folder=tmp_path/name;folder.mkdir()
    desc=descriptor(folder,snapshot(folder,name,[vector]))
    desc.update(result_file=str(folder/desc['result_file']),support_file=str(folder/desc['support_file']))
    write_json_atomic(folder/'vacuum-tracking-input.json',desc)
    return folder


def test_anchor_is_fixed_failure_recovers_and_recycled_worker_reuses(tmp_path):
    worker=setup_worker(tmp_path)
    first=candidate(tmp_path,'first',(1,0,0))
    assert worker._run_vacuum_matching(first)['status']=='reference-established'
    original=worker._vacuum_reference_store.read_bytes()
    bad=candidate(tmp_path,'bad',(0,1,0))
    assert worker._run_vacuum_matching(bad)['status']=='unconfirmed'
    next_worker=setup_worker(tmp_path)
    good=candidate(tmp_path,'good',(2j,0,0))
    result=next_worker._run_vacuum_matching(good)
    assert result['status']=='matched' and result['selected_modes']==[1]
    assert next_worker._vacuum_reference_store.read_bytes()==original
    assert read_json(good/'vacuum-mode-matching.json')['mac'][0][0]==pytest.approx(1)


def test_missing_descriptor_is_unconfirmed_not_solver_failure(tmp_path):
    worker=setup_worker(tmp_path)
    result=worker._run_vacuum_matching(tmp_path)
    assert result['status']=='unconfirmed' and result['solver_replayed'] is False
    assert not worker._vacuum_reference_store.exists()


def test_matching_requires_explicit_strategy_frequency_and_evidence():
    base={'geometry_id':'g','sampling':{'bounds_m':[0,1,0,1,0,1],
          'counts':[2,2,2],'scope':'specified-domain'}}
    with pytest.raises(ValueError): validate_managed_domain_options({**base,'matching':{}})
    p=asdict(policy());p['maximum_frequency_change']=None
    with pytest.raises(ValueError): validate_managed_domain_options({**base,'matching':{
        'reference_strategy':'first-valid','policy':p,'sampling_evidence':'fixture'}})


def test_external_reference_change_is_unconfirmed(tmp_path):
    from csttool.result_reconciliation import file_hash
    worker=setup_worker(tmp_path)
    first=candidate(tmp_path,'reference',(1,0,0))
    anchor=first/'vacuum-tracking-input.json'
    worker._vacuum_domain['matching'].update(reference_strategy='external',
        reference_file=str(anchor),reference_sha256=file_hash(anchor))
    good=candidate(tmp_path,'next',(1j,0,0))
    assert worker._run_vacuum_matching(good)['status']=='matched'
    anchor.write_text('{}')
    result=worker._run_vacuum_matching(good)
    assert result['status']=='unconfirmed' and 'descriptor changed' in result['reason']
