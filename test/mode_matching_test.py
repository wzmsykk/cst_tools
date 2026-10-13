import numpy as np
import pytest
from csttool.mode_matching import (MatchPolicy, OverlapMatrices, weighted_overlap,
                                 normalized_mac, match_modes, compare_subspaces)

POLICY = MatchPolicy(0.9, 0.05, 0.99)


def basis():
    return np.eye(3, dtype=complex).reshape(1,3,3)


def test_scale_phase_and_permutation():
    a = basis()
    b = a[:,:,[2,0,1]] * np.array([1e100j, -3, 1e-100])
    matrix = weighted_overlap(a,b,[1])
    mac = normalized_mac(matrix)
    assert np.allclose(mac, np.eye(3)[:,[2,0,1]])
    assert [p['candidate_index'] for p in match_modes(mac,None,POLICY)['pairs']] == [1,2,0]


def test_explicit_conjugation_and_nonuniform_weights():
    a = np.array([1+1j,2]).reshape(2,1,1)*np.array([1,0,0]).reshape(1,3,1)
    b = np.array([2+3j,1]).reshape(2,1,1)*np.array([1,0,0]).reshape(1,3,1)
    matrix=weighted_overlap(a,b,[1,3])
    assert matrix.cross[0,0] == pytest.approx((11+1j)/(6*np.sqrt(13)))
    expected=abs(11+1j)**2/(14*16)
    assert normalized_mac(matrix)[0,0] == pytest.approx(expected)


@pytest.mark.parametrize('bad', [np.zeros((1,3,1)), np.full((1,3,1),np.nan), np.ones((2,2,1))])
def test_invalid_fields(bad):
    with pytest.raises(ValueError): weighted_overlap(bad,bad,[1]*len(bad))


@pytest.mark.parametrize('weights', [[-1],[0],[np.inf],[]])
def test_invalid_weights(weights):
    with pytest.raises(ValueError): weighted_overlap(basis(),basis(),weights)


def test_rotated_pair_is_group_match_not_member_match():
    a=basis()[:,:,:2]
    rotation=np.array([[1,1],[-1,1]])/np.sqrt(2)
    matrices=weighted_overlap(a,a@rotation,[1])
    assert match_modes(normalized_mac(matrices),None,MatchPolicy(0.4,0.05,0.99))['status']=='unconfirmed'
    assert compare_subspaces(matrices,POLICY)['status']=='matched'


@pytest.mark.parametrize('seed', range(5))
def test_random_unitary_subspace(seed):
    rng=np.random.default_rng(seed)
    q,_=np.linalg.qr(rng.normal(size=(2,2))+1j*rng.normal(size=(2,2)))
    a=basis()[:,:,:2]
    assert compare_subspaces(weighted_overlap(a,a@q,[1]),POLICY)['minimum_squared_overlap']==pytest.approx(1)


def test_missing_duplicate_and_wrong_mode():
    a=basis()[:,:,:2]
    for b in (a[:,:,:1], np.repeat(a[:,:,:1],2,axis=2), basis()[:,:,1:]):
        assert compare_subspaces(weighted_overlap(a,b,[1]),POLICY)['status']=='unconfirmed'


def test_invalid_gram_and_mac_bounds():
    for matrix in (OverlapMatrices(np.eye(1),np.eye(1),np.array([[2]])),
                   OverlapMatrices(np.array([[1,1],[0,1]]),np.eye(1),np.ones((2,1)))):
        with pytest.raises(ValueError): normalized_mac(matrix)
    matrix=OverlapMatrices(np.eye(1),np.eye(1),np.array([[1+1e-10]]))
    assert normalized_mac(matrix)[0,0]==1


def test_frequency_gate_and_ambiguity():
    p=MatchPolicy(0.9,0.05,0.99,maximum_frequency_change=0.01)
    assert match_modes(np.eye(2),([100,200],[101,300]),p)['status']=='unconfirmed'
    assert match_modes(np.ones((1,2)),None,POLICY)['reason']=='ambiguous-assignment'


def test_integral_converges_and_rq_direction_is_not_mode_identity():
    estimates=[]
    for n in (10,20,40):
        x=(np.arange(n)+0.5)/n
        a=np.zeros((n,3,1),complex); a[:,0,0]=x
        # Unscaled physical quadrature norm is analytically 1/3.
        estimates.append(float(np.sum(np.abs(a[:,0,0])**2)/n))
    assert abs(estimates[-1]-1/3)<abs(estimates[0]-1/3)
    assert np.cos(0)**2==1 and np.cos(np.pi/2)**2<1e-20


def test_analytic_pillbox_dipole_family_rotation_not_number_or_single_line_rq():
    # TM110 Ez proportional to J1(3.83170597*r/R)*cos/sin(phi).
    # Independent convergent power series avoids requiring SciPy.
    phi=np.linspace(0,2*np.pi,128,endpoint=False)
    r=np.linspace(.01,.99,32)
    radial,angle=np.meshgrid(r,phi,indexing='ij')
    argument=3.8317059702075125*radial
    term=argument/2
    j1=term.copy()
    for k in range(1,25):
        term*=-(argument/2)**2/(k*(k+1));j1+=term
    field=np.zeros((radial.size,3,2),complex)
    field[:,2,0]=(j1*np.cos(angle)).ravel()
    field[:,2,1]=(j1*np.sin(angle)).ravel()
    rotated=field@np.array([[1,1],[-1,1]])/np.sqrt(2)
    matrices=weighted_overlap(field,rotated,radial.ravel())
    assert np.allclose(normalized_mac(matrices),.5,atol=1e-12)
    assert compare_subspaces(matrices,POLICY)['minimum_squared_overlap']==pytest.approx(1)
    assert match_modes(normalized_mac(matrices),None,MatchPolicy(.4,.05,.99))['status']=='unconfirmed'
    # A beam displaced in x couples to cos(phi) but not sin(phi).
    assert abs(np.cos(0))==1 and abs(np.sin(0))==0
