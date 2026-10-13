from test.field_artifacts_test import artifact
from test.support.validate_field_failure_recovery import diagnose_saved_faults
from csttool.result_reconciliation import file_hash


def test_real_files_are_rejected_then_recovered_without_changing_reference(tmp_path):
    reference = artifact(tmp_path)
    before = file_hash(reference.path)
    cases = diagnose_saved_faults(reference, tmp_path / 'faults')
    assert [case['fault'] for case in cases] == [
        'missing-file', 'hash-change', 'missing-dataset', 'wrong-coordinates']
    expected = ['FileNotFoundError', 'hash changed', 'KeyError', 'coordinates do not match']
    for case, reason in zip(cases, expected):
        assert reason in case['failure']['reason']
        assert case['recovered_status'] == 'complete'
    assert file_hash(reference.path) == before
