"""B3 offline semantic/fault tests; never a live database query or CST acceptance."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from csttool.execution_snapshot import (
    BUILD, PROFILE_ID, ExecutionBinding, ExecutionConfig, ExecutionExpectation,
    expectation_from_projection, read_snapshot_record, validate_execution_snapshot,
    verify_execution_artifact,
)

ROOT = Path(__file__).parents[1]
CASES = [case for case in json.loads((ROOT/'test/fixtures/cst_settings_verifier_v06/cases.json').read_text(encoding='utf-8'))['cases']
         if case['group']=='execution']
BASE = CASES[0]['input']


def expectation(data=None):
    data = BASE if data is None else data
    return ExecutionExpectation(ExecutionBinding(**data['requested_binding']),
                                ExecutionConfig(**data['expected_execution_config']),
                                '2026-10-28T07:59:00+00:00', '2026-10-28T08:01:00+00:00',
                                data['result_success'], data.get('expected_target_expr'))


@pytest.mark.parametrize('case', CASES, ids=lambda case:case['id'])
def test_all_v06_execution_oracles_use_registered_profile(case):
    # The normative casebook is not a production registry. Do not accept its maps
    # or float-format object as executable caller-supplied calibration rules.
    data, expected = case['input'], case['expected']
    report = validate_execution_snapshot(expectation(data), data['execution_snapshot'])
    public_status = {'execution-match':'execution-snapshot-match',
                     'execution-mismatch':'execution-snapshot-mismatch'}.get(expected['status'],expected['status'])
    assert report.status == public_status
    assert set(expected['reasons']) <= set(report.reasons)
    for key,value in expected['fields'].items():
        assert report.fields[key] == value
    if report.status in ('unsupported','stale','unresolved','malformed'):
        assert not report.fields
    assert report.publish_ready is False and report.live_value is None
    assert not report.database_verified  # Semantic binding equality is not a file hash check.
    assert report.profile_id == PROFILE_ID


@pytest.mark.parametrize('key,new', [
    ('project_id','another-project'), ('attempt_id','another-attempt'),
    ('definition_revision','new-revision'), ('database_sha256','b'*64),
    ('cst_build','other-build'), ('scope','SP/FME'),
])
def test_all_binding_dimensions_reject_even_equal_numeric_values(key,new):
    snapshot = deepcopy(BASE['execution_snapshot'])
    snapshot['binding'][key] = new
    report = validate_execution_snapshot(expectation(),snapshot)
    assert report.status == 'stale' and report.reasons == ('execution-binding-mismatch',)
    assert not report.fields


@pytest.mark.parametrize('missing', list(BASE['requested_binding']))
def test_missing_binding_is_never_inferred(missing):
    snapshot = deepcopy(BASE['execution_snapshot'])
    del snapshot['binding'][missing]
    assert validate_execution_snapshot(expectation(),snapshot).reasons == ('execution-binding-missing',)


@pytest.mark.parametrize('key', list(BASE['execution_snapshot']['values']))
def test_missing_database_values_do_not_default(key):
    snapshot = deepcopy(BASE['execution_snapshot'])
    snapshot['values'][key] = ''
    report = validate_execution_snapshot(expectation(),snapshot)
    assert report.status == 'unresolved' and not report.fields


@pytest.mark.parametrize('key,value,reason', [
    ('MeshType','2','unknown-mesh-enum'), ('SolverTypeTet','0','unknown-method-enum'),
    ('FrequencyTargetActive','1','invalid-native-boolean'),
    ('AdaptionActiveTet','false','invalid-native-boolean'),
    ('Modes','2','mode-count-profile-unverified'), ('Modes','0','mode-count-profile-unverified'),
    ('Modes','True','mode-count-profile-unverified'),
    ('FrequencyTargetValue','NaN','invalid-native-number'),
    ('FrequencyTargetValue','Infinity','invalid-native-number'),
    ('FrequencyTargetValue','480,0','invalid-native-number'),
    ('FrequencyTargetValue',' 480','invalid-native-number'),
    ('FrequencyTargetValue','1e9999','invalid-native-number'),
    ('FrequencyTargetValue','-1','native-number-format-invalid'),
    ('FrequencyTargetValue','493.827156','native-number-format-invalid'),
])
def test_unknown_enums_and_bad_native_text_are_not_guessed(key,value,reason):
    snapshot = deepcopy(BASE['execution_snapshot'])
    snapshot['values'][key] = value
    report = validate_execution_snapshot(expectation(),snapshot)
    assert report.reasons == (reason,) and not report.fields


@pytest.mark.parametrize('stamp,status,reason', [
    ('2026-10-28T08:00:00','malformed','invalid-observation-time'),
    ('not-a-time','malformed','invalid-observation-time'),
    ('2026-10-28T07:58:59+00:00','stale','observation-outside-attempt'),
    ('2026-10-28T08:01:01+00:00','stale','observation-outside-attempt'),
])
def test_timestamp_requires_bound_attempt_window(stamp,status,reason):
    snapshot = deepcopy(BASE['execution_snapshot']); snapshot['observed_at'] = stamp
    report = validate_execution_snapshot(expectation(),snapshot)
    assert report.status == status and report.reasons == (reason,)


@pytest.mark.parametrize('phase', ['pre-solver','after-save','after-rebuild','post-attempt-old'])
def test_save_or_rebuild_cannot_relabel_observation_as_current(phase):
    snapshot = deepcopy(BASE['execution_snapshot']); snapshot['phase'] = phase
    assert validate_execution_snapshot(expectation(),snapshot).reasons == ('execution-phase-unverified',)


@pytest.mark.parametrize('expected_value,raw,match', [
    ('480.0001','480',True), ('480.4','480',False),
    ('493.827156','493.827',True), ('493.827156','493.828',False),
    ('0','0',True), ('0.00000000123456789','1.23457e-09',True),
    ('123456789','1.23457e+08',True), ('999999.9','1e+06',True),
])
def test_g6_rounding_not_tolerance_based_on_printed_decimal_places(expected_value,raw,match):
    expected = expectation()
    expected = replace(expected,config=replace(expected.config,target_value=expected_value))
    snapshot = deepcopy(BASE['execution_snapshot']); snapshot['values']['FrequencyTargetValue'] = raw
    report = validate_execution_snapshot(expected,snapshot)
    assert report.status == ('execution-snapshot-match' if match else 'execution-snapshot-mismatch')
    assert report.comparisons['target_value']['matches'] is match
    assert report.raw_values['FrequencyTargetValue'] == raw
    assert report.comparisons['target_value']['expected'] == expected_value


def test_failed_solver_has_independent_matching_config_and_disabled_target_is_not_bound():
    expected = expectation()
    expected = replace(expected,config=replace(expected.config,target_enabled=False))
    snapshot = deepcopy(BASE['execution_snapshot']); snapshot['values']['FrequencyTargetActive'] = 'False'
    report = validate_execution_snapshot(expected,snapshot)
    assert report.status == 'execution-snapshot-match' and report.fields['result_success'] is False
    assert report.fields['execution.effective_lower_bound_mhz'] is None
    with pytest.raises(TypeError):
        report.raw_values['Modes'] = '3'
    snapshot['values']['Modes'] = '4'
    assert report.raw_values['Modes'] == '1'
    assert validate_execution_snapshot(replace(expected,result_success=None),
                                       BASE['execution_snapshot']).fields['result_success'] is None


def test_non_target_differences_are_compared_and_reported_separately():
    snapshot = deepcopy(BASE['execution_snapshot'])
    snapshot['values'].update(SolverTypeTet='2', AdaptionActiveTet='True', FrequencyTargetActive='False')
    report = validate_execution_snapshot(expectation(),snapshot)
    assert report.status == 'execution-snapshot-mismatch'
    assert set(report.reasons) == {'method-mismatch','adaptation-enabled-mismatch','target-enabled-mismatch'}
    assert report.comparisons['method']['source_key'] == 'objdata\\EigenmodeParameter\\SolverTypeTet'


def test_unregistered_profile_context_and_caller_override_are_rejected():
    assert validate_execution_snapshot(expectation(),BASE['execution_snapshot'],profile_id='caller-map').status == 'unsupported'
    with pytest.raises(TypeError):
        validate_execution_snapshot(expectation(),BASE['execution_snapshot'],calibration_profile=BASE['calibration_profile'])
    for change in ({'cst_build':'2023'}, {'scope':'SP/FME'}):
        snapshot = deepcopy(BASE['execution_snapshot']); snapshot['binding'].update(change)
        expected = replace(expectation(),binding=ExecutionBinding(**snapshot['binding']))
        assert validate_execution_snapshot(expected,snapshot).reasons == ('calibration-context-unsupported',)
    expected = replace(expectation(),config=replace(expectation().config,requested_modes=2))
    assert validate_execution_snapshot(expected,BASE['execution_snapshot']).reasons == ('mode-count-profile-unverified',)


@pytest.mark.parametrize('build',['2022','2022.0 Release from 2021-12-01',
                                  'Version 2022.3 - Apr 01 2022','Version 2022.5 - Jun 03 2022'])
def test_2022_major_policy_reuses_rules_without_merging_attempt_build_identity(build):
    snapshot=deepcopy(BASE['execution_snapshot']);snapshot['binding']['cst_build']=build
    expected=replace(expectation(),binding=replace(expectation().binding,cst_build=build))
    assert validate_execution_snapshot(expected,snapshot).status=='execution-snapshot-match'
    if build!=expectation().binding.cst_build:
        assert validate_execution_snapshot(expectation(),snapshot).status=='stale'


@pytest.mark.parametrize('raw', [
    b'{', b'[]', b'{"values":{},"values":{}}', b'{"v":NaN}', b'{"v":1e9999}', b'\xff',
])
def test_strict_json_reader(tmp_path,raw):
    path = tmp_path/'snapshot.json'; path.write_bytes(raw)
    with pytest.raises(ValueError):
        read_snapshot_record(path)


def test_snapshot_record_budget_and_roundtrip(tmp_path):
    path = tmp_path/'snapshot.json'; path.write_text(json.dumps(BASE['execution_snapshot']),encoding='utf-8')
    assert validate_execution_snapshot(expectation(),read_snapshot_record(path)).status == 'execution-snapshot-match'
    with pytest.raises(ValueError,match='budget'):
        read_snapshot_record(path,max_bytes=4)


def test_snapshot_record_identity_change_is_rejected(tmp_path,monkeypatch):
    import csttool.execution_snapshot as module
    path = tmp_path/'snapshot.json'
    path.write_text(json.dumps(BASE['execution_snapshot']),encoding='utf-8')
    original, calls = module._identity, 0
    def changed(candidate):
        nonlocal calls
        values = original(candidate); calls += 1
        return values if calls == 1 else values[:-1]+(values[-1]+1,)
    monkeypatch.setattr(module,'_identity',changed)
    with pytest.raises(ValueError,match='changed-during-read'):
        read_snapshot_record(path)


@pytest.mark.parametrize('change', [
    {'values':[]}, {'values':{'SolverTypeTet':'1'}}, {'unexpected':'extra'},
    {'values':dict(BASE['execution_snapshot']['values'],Extra='1')},
    {'values':dict(BASE['execution_snapshot']['values'],Modes=1)},
])
def test_snapshot_envelope_is_not_a_generic_database_query(change):
    snapshot = deepcopy(BASE['execution_snapshot']); snapshot.update(change)
    report = validate_execution_snapshot(expectation(),snapshot)
    assert report.status in ('unresolved','malformed') and not report.fields


def test_invalid_owner_time_window_and_outcome_are_not_defaulted():
    for kwargs in ({'attempt_started_at':'2026-10-29T00:00:00Z'},
                   {'attempt_finished_at':'2026-10-28'}, {'result_success':1}):
        with pytest.raises(ValueError):
            replace(expectation(),**kwargs)


def artifact_case(tmp_path):
    path = tmp_path/'Model.db'; path.write_bytes(b'synthetic closed database bytes; not CST DB contents')
    binding = replace(expectation().binding,database_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    expected = replace(expectation(),binding=binding)
    snapshot = deepcopy(BASE['execution_snapshot']); snapshot['binding']['database_sha256'] = binding.database_sha256
    return path,expected,snapshot


def test_actual_artifact_hash_is_required_for_verified_database(tmp_path):
    path,expected,snapshot = artifact_case(tmp_path)
    report = verify_execution_artifact(expected,snapshot,database_path=path)
    assert report.status == 'execution-snapshot-match' and report.database_verified
    path.write_bytes(b'changed after Save or Rebuild')
    report = verify_execution_artifact(expected,snapshot,database_path=path)
    assert report.status == 'stale' and not report.fields and not report.database_verified


def test_artifact_missing_and_budget_failure_preserve_source(tmp_path):
    path,expected,snapshot = artifact_case(tmp_path)
    original = path.read_bytes()
    assert verify_execution_artifact(expected,snapshot,database_path=path,max_bytes=1).status == 'rejected'
    assert path.read_bytes() == original
    assert verify_execution_artifact(expected,snapshot,database_path=tmp_path/'absent.db').status == 'unresolved'


def test_artifact_mutation_between_hashes_cannot_be_adopted(tmp_path,monkeypatch):
    import csttool.execution_snapshot as module
    path,expected,snapshot = artifact_case(tmp_path)
    original = module._hash_database
    count = 0
    def mutate(path,limit):
        nonlocal count
        value = original(path,limit); count += 1
        if count == 1:
            path.write_bytes(b'mutated')
        return value
    monkeypatch.setattr(module,'_hash_database',mutate)
    report = verify_execution_artifact(expected,snapshot,database_path=path)
    assert report.status == 'stale' and not report.fields


def test_b2_expectation_factory_preserves_high_precision_expression_and_definition_digest(tmp_path):
    from csttool.saved_project_source import read_saved_source
    from csttool.settings_projection import project_saved_settings
    from test.saved_project_source_test import container
    from test.a1_history_profile_test import HISTORY,PARAMETERS
    rows = deepcopy(PARAMETERS)
    for row in rows:
        if row['name'] == 'fmin': row.update(expr='500.000000000000001',value='500.000000000000001')
    path = tmp_path/'definition.cst'
    path.write_bytes(container([('Model/3D/Model.mod',HISTORY.encode()),
                               ('Model/Parameters.json',json.dumps({'parameters':rows}).encode())]))
    source = read_saved_source(path,scope='root'); projection = project_saved_settings(source)
    expected = expectation_from_projection(expectation().binding,projection,definition_sha256=source.sha256,
                                           attempt_started_at='2026-10-28T07:59:00Z',
                                           attempt_finished_at='2026-10-28T08:01:00Z',result_success=False)
    assert expected.config.target_value == '500.000000000000001'
    assert expected.target_expression == 'fmin'
    assert expected.definition_sha256 == source.sha256
    for digest in ('b'*64,'not-a-hash'):
        with pytest.raises(ValueError):
            expectation_from_projection(expected.binding,projection,definition_sha256=digest,
                                         attempt_started_at=expected.attempt_started_at,
                                         attempt_finished_at=expected.attempt_finished_at,result_success=False)


@pytest.mark.parametrize('config', [dict(target_enabled=1),dict(adaptation_enabled='False'),
                                  dict(requested_modes=True),dict(requested_modes=0),
                                  dict(target_value='NaN'),dict(target_value='-1')])
def test_expectations_are_typed_owner_data(config):
    with pytest.raises(ValueError):
        replace(expectation().config,**config)


NATIVE = ROOT/'test/fixtures/execution_snapshot_native'
NATIVE_CASES = json.loads((NATIVE/'manifest.json').read_text(encoding='utf-8'))['cases']


@pytest.mark.parametrize('case', NATIVE_CASES, ids=lambda case:case['id'])
def test_historical_native_strings_replay_without_claiming_attempt_binding(case):
    for item in case['files']:
        raw = (NATIVE/item['fixture']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item['sha256']
    database = (NATIVE/(case['id']+'-database.tsv')).read_bytes().decode('utf-8')
    native = {}
    for line in database.splitlines():
        phase,key,value = line.split('\t',2)
        prefix = 'objdata\\EigenmodeParameter\\'
        if phase == 'post-solver' and key.startswith(prefix) and value.startswith('OK:'):
            assert key[len(prefix):] not in native
            native[key[len(prefix):]] = value[3:]
    # Expected settings are independently fixed from the calibration plan, not
    # inferred from these native values. This new binding/time window is synthetic.
    binding = replace(expectation().binding,attempt_id='offline-replay-'+case['id'],
                      database_sha256=case['historical_database_sha256'])
    expected = replace(expectation(),binding=binding,config=ExecutionConfig(**case['expected_config']),
                       result_success=case['expected_result_success'])
    snapshot = deepcopy(BASE['execution_snapshot']); snapshot['values'] = native
    snapshot['binding'].update(attempt_id=binding.attempt_id,database_sha256=binding.database_sha256)
    report = validate_execution_snapshot(expected,snapshot)
    assert report.status == 'execution-snapshot-match'
    start = (NATIVE/(case['id']+'-solver.tsv')).read_bytes().splitlines()[0].split(b'\t')[0]
    assert (start==b'1') is case['expected_result_success']
    assert report.fields['result_success'] is case['expected_result_success']
    assert not report.database_verified and not report.publish_ready
