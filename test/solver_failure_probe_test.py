"""Probe classification must not promote configuration/rebuild errors to Start failures."""
import pytest
from test.support.validate_solver_failure_recovery import classify


@pytest.mark.parametrize('message,expected', [
    ('INTERNAL_ERROR: parameters failed: number=1', 'parameter-or-configuration-error'),
    ('INTERNAL_ERROR: solver-config failed: number=1', 'parameter-or-configuration-error'),
    ('REBUILD_FAILED: Rebuild returned False', 'rebuild-failure'),
    ('REBUILD_FAILED: rebuild failed: number=1', 'rebuild-failure'),
    ('SOLVER_FAILED: EigenmodeSolver.Start returned 0', 'start-return-0'),
    ('SOLVER_FAILED: solver-start failed: number=1', 'start-exception'),
    ('SOLVER_FAILED: solver-result failed: number=1', 'start-return-1-without-results'),
    ('RESULT_FLUSH_FAILED: postprocess failed', 'unclassified-failure'),
])
def test_actual_stage_classification(message, expected):
    assert classify({'TaskStatus': 'Failure', 'FailureReport': message}) == expected


def test_success_not_failure():
    assert classify({'TaskStatus': 'Success', 'FailureReport': None}) == 'success'
