import numpy as np
import pytest
from csttool.field_artifacts import SamplingSpec
from csttool.physical_domain import DomainSupport, common_quadrature, cylinder_support, sampling_convergence


def test_volume_and_conductor_mask_are_not_field_amplitude():
    spec = SamplingSpec((-1,1,-1,1,-1,1), (64,64,8), 'specified-domain')
    support = cylinder_support(spec, 1, -1, 1)
    q = common_quadrature([support, support], ['Vacuum'])
    assert q.volume_m3 == pytest.approx(2*np.pi, rel=.005)
    assert set(q.weights_m3) == {0, spec.weights()[0]}
    assert q.scope == 'common-material-domain'


def test_changed_geometry_rejects_full_domain_label():
    spec = SamplingSpec((-1,1,-1,1,-1,1), (12,12,12), 'specified-domain')
    a, b = cylinder_support(spec, 1,-1,1), cylinder_support(spec,.8,-1,1)
    with pytest.raises(ValueError, match='support changed'):
        common_quadrature([a,b], ['Vacuum'])
    assert common_quadrature([a,b], ['Vacuum'], allow_intersection=True).scope == 'common-intersection'


def test_roi_cannot_be_called_whole_cylinder():
    with pytest.raises(ValueError, match='whole cylinder'):
        cylinder_support(SamplingSpec((-.5,.5,-.5,.5,-1,1),(2,2,2)),1,-1,1)


def test_unverified_and_unknown_materials_rejected():
    spec = SamplingSpec((0,1,0,1,0,1),(1,1,1))
    with pytest.raises(ValueError):
        DomainSupport(spec, ('',), 'model', 'query', True)
    with pytest.raises(ValueError):
        DomainSupport(spec, ('Vacuum',), 'model', 'query', False)


def test_convergence_needs_geometry_and_field_not_only_mac():
    levels = [{'counts':[n,n,n], 'volume_m3':1., 'normalized_gram_abs':[[1.,0],[0,1.]],
               'mode_l2_norms':[1.,1.]} for n in (12,24,48)]
    assert sampling_convergence(levels, tolerance=.01,expected_volume_m3=1.)['status'] == 'converged'
    levels[-1]['mode_l2_norms'] = [1.,2.]
    assert sampling_convergence(levels, tolerance=.01)['status'] == 'unconfirmed'


def test_sampling_mismatch_and_empty_selection_fail():
    a = cylinder_support(SamplingSpec((-1,1,-1,1,-1,1),(2,2,2)),1,-1,1)
    b = cylinder_support(SamplingSpec((-1,1,-1,1,-1,1),(3,3,3)),1,-1,1)
    with pytest.raises(ValueError, match='identical'):
        common_quadrature([a,b], ['Vacuum'])
    with pytest.raises(ValueError, match='empty/negative'):
        common_quadrature([a], ['not-present'])


def test_analytic_doublet_is_orthogonal_and_rotation_does_not_change_group():
    pytest.importorskip('scipy')
    from csttool.pillbox_reference import tm110_reference
    from csttool.mode_matching import weighted_overlap, compare_subspaces, MatchPolicy
    spec = SamplingSpec((-1,1,-1,1,-1,1),(32,32,8),'specified-domain')
    q = common_quadrature([cylinder_support(spec,1,-1,1)],['Vacuum'])
    reference = tm110_reference(spec.points(),1,(-1,1))
    fields = reference['fields']
    rotated = fields @ (np.array([[1.,-1.],[1.,1.]])/np.sqrt(2))
    matrices = weighted_overlap(fields,rotated,q.weights_m3)
    assert compare_subspaces(matrices,MatchPolicy(.9,.05,.99))['status']=='matched'
    assert abs(matrices.reference[0,1]) < 1e-10
    assert reference['frequency_hz'] == pytest.approx(182823916.3,rel=1e-6)


def test_native_bridge_and_mask_hash(tmp_path):
    from csttool.geometry_support import render_material_support, load_material_support
    from csttool.result_reconciliation import file_hash
    spec=SamplingSpec((0,1,0,1,0,1),(1,1,1))
    path=tmp_path/'support.tsv'
    source=render_material_support(spec,path,shape_names=('component:vacuum',))
    assert 'Solid.IsPointInsideShape' in source and 'Solid.GetMaterialNameForShape' in source
    assert 'EigenmodeSolver.Start' not in source and 'Rebuild' not in source
    assert 'Ambiguous overlapping materials' in source and '.partial' in source
    path.write_text('Vacuum\n')
    digest=file_hash(path)
    assert load_material_support(spec,path,expected_sha256=digest,geometry_id='geometry').verified
    path.write_text('changed\n')
    with pytest.raises(ValueError,match='artifact changed'):
        load_material_support(spec,path,expected_sha256=digest,geometry_id='geometry')


def test_support_input_is_copied_and_reserved_exclusion_not_integrated():
    spec=SamplingSpec((0,1,0,1,0,1),(1,1,1))
    labels=['Vacuum']
    support=DomainSupport(spec,labels,'geometry','native-query',True)
    labels[0]='PEC'
    assert support.material_labels==('Vacuum',)
    with pytest.raises(ValueError,match='selection required'):
        common_quadrature([support],['excluded'])


def test_field_diagnostic_uses_explicit_quadrature(tmp_path):
    from test.field_artifacts_test import artifact
    from csttool.field_diagnostics import run_field_diagnostic
    from csttool.mode_matching import MatchPolicy
    field=artifact(tmp_path)
    support=DomainSupport(field.sampling,tuple(['Vacuum']*8),'geometry','native-query',True)
    q=common_quadrature([support],['Vacuum'])
    result=run_field_diagnostic([field],[field],MatchPolicy(.9,.05,.99),tmp_path/'report.json',quadrature=q)
    assert result['status']=='complete' and result['quadrature']['weight_unit']=='m^3'
    assert result['scope']=='common-material-domain'
    assert not result['physical_identity_confirmed']


def test_cross_mesh_probe_is_invariant_to_doublet_numbering():
    from test.support.validate_pillbox_cross_mesh import compare_pair
    reference=np.zeros((2,3,2),dtype=complex)
    reference[0,0,0]=1
    reference[1,0,1]=1
    rotation=np.array([[1,-1],[1,1]])/np.sqrt(2)
    result=compare_pair(reference,reference@rotation,[1,1],'common-material-domain')
    assert result['swap_invariant']
    assert result['subspace']['status']=='matched'
    assert result['subspace']['minimum_squared_overlap']==pytest.approx(1)
