"""Frozen operator identities, with fake solver protocol only."""
import pytest
from csttool.application_service import ServiceError
from csttool.execution_contract import StopIntent
from test.single_simulation_service_test import make_service, FakeWorker


def test_frozen_context_has_line_formula_and_algorithm_hash_and_detects_tampering(tmp_path):
    app,payload,_=make_service(tmp_path)
    app.execute_simulation(payload,run_id='provenance',stop=StopIntent(),update=lambda **kw:None).run(payload)
    result=app.get_simulation_results('provenance')
    assert result['schema_version']==2
    rq=result['postprocess_definition']['r_over_q']
    assert rq['integration_line']==dict(axis='z',offset_mm=[0.,0.,0.],endpoints_mm=[[0.,0.,-60.],[0.,0.,60.]],beta=1.,range='full')
    assert rq['formula']=='abs(V)^2/(omega*W)' and rq['energy']=='QFactor.GetTotalEnergy'
    assert len(rq['algorithm']['sha256'])==64
    assert result['postprocess_definition']['generated_macro_evidence']=='unavailable'  # fake peer has no real macro
    (tmp_path/'control/runs/provenance/rq-algorithm.vb').write_text('changed')
    with pytest.raises(ServiceError,match='RESULT_INVALID'):app.get_simulation_results('provenance')


def test_tampered_frozen_context_cannot_be_reexported(tmp_path):
    app,payload,_=make_service(tmp_path)
    app.execute_simulation(payload,run_id='provenance',stop=StopIntent(),update=lambda **kw:None).run(payload)
    result=app.get_simulation_results('provenance')
    (tmp_path/'control/runs/provenance/postprocess-provenance.json').write_text('{}')
    with pytest.raises(ServiceError,match='RESULT_INVALID'):
        app.export_simulation_results('provenance',result['result_revision'],['json'])
