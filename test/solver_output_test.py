from csttool.solver_output import parse_solver_output


def test_extract_settings_pass_modes_refinement_and_success():
    parsed = parse_solver_output('''Number of threads used: 10.
Eigenmode solver settings:
  Mesh: Tetrahedral
  Desired accuracy: 1e-06
  Number of modes: 1
Estimation frequency: 400 MHz
Pass 1:
    1 503.512 MHz 1.195e-07
Marked 259 of 1891 for refinement.
Pass 2:
    1 503.6801 MHz 6.479e-08
Desired accuracy limit reached, mesh adaptation stopped.
Eigenmode solver successful
''')
    assert parsed['settings']['threads'] == 10
    assert parsed['settings']['Number of modes'] == '1'
    assert len(parsed['passes']) == 2
    assert parsed['passes'][1]['modes'][0]['frequency'] == 503.6801
    assert parsed['refinement'][0]['total'] == 1891
    assert parsed['solver_success_observed'] is True


def test_incomplete_or_unknown_output_is_not_success():
    parsed = parse_solver_output('Unknown stage\nPass 1:\n1 503.')
    assert parsed['passes'][0]['modes'] == []
    assert not parsed['solver_success_observed']
