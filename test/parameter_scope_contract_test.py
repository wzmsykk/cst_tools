from pathlib import Path

import pytest

from test.support.diagnose_parameter_shutdown import validate_linked_values


def test_linked_expression_and_values(tmp_path):
    path=tmp_path/'linked.tsv'
    path.write_text('before\t(Leq-Gap)/2\t55\tconcaveL\t55\nchanged\t(Leq-Gap)/2\t60\tconcaveL\t60\nrestored\t(Leq-Gap)/2\t55\tconcaveL\t55\n')
    assert validate_linked_values(path)['values']==[55,60,55]
    path.write_text(path.read_text().replace('60\tconcaveL\t60','60\tconcaveL\t55'))
    with pytest.raises(ValueError,match='stale'):
        validate_linked_values(path)


def test_expression_cannot_be_flattened(tmp_path):
    path=tmp_path/'linked.tsv'
    path.write_text('before\t(Leq-Gap)/2\t55\tconcaveL\t55\nchanged\t60\t60\tconcaveL\t60\nrestored\t(Leq-Gap)/2\t55\tconcaveL\t55\n')
    with pytest.raises(ValueError,match='expression changed'):
        validate_linked_values(path)


def test_managed_worker_requires_loaded_project_context():
    macro=Path('data/runtime_managed_worker_v1_main.vb').read_text()
    assert '\n    OpenFile ' not in macro
    assert 'requestedModes = RestoreDoubleParameter("nmodes")' in macro
