from pathlib import Path
import pytest
from csttool.definition_geometry import verify_geometry_observation,render_geometry_observer
from csttool.saved_project_source import read_saved_source
from csttool.settings_projection import project_saved_settings
from test.single_simulation_service_test import make_service
from test.definition_verifier_test import peer


@pytest.mark.parametrize('fault',[None,'variant-bool','false','material','volume','bounds','boundary','nonce'])
def test_native_shape_evidence_is_not_inferred_from_history(tmp_path,fault):
    app,payload,record=make_service(tmp_path)
    model=app._directory(payload['document_id'],payload['definition_revision'])/'definition.cst'
    projection=project_saved_settings(read_saved_source(model,scope='root'))
    nonce='a'*32
    peer(None,model,tmp_path,'"nonce" & Chr(9) & "'+nonce+'"')
    path=tmp_path/'geometry.tsv';text=path.read_text()
    if fault=='variant-bool':text=text.replace('exists\tTrue','exists\t-1')
    if fault=='false':text=text.replace('exists\tTrue','exists\t0')
    if fault=='material':text=text.replace('material\tVacuum','material\tPEC')
    if fault=='volume':text=text.replace('volume_mm3\t','volume_mm3\t9')
    if fault=='bounds':text=text.replace('xmin_mm\t-100','xmin_mm\t-101')
    if fault=='boundary':text=text.replace('boundary.xmin\telectric','boundary.xmin\tmagnetic')
    if fault=='nonce':text=text.replace(nonce,'b'*32)
    path.write_text(text)
    if fault not in (None,'variant-bool'):
        with pytest.raises(ValueError):verify_geometry_observation(path,projection,model,nonce)
    else:
        result=verify_geometry_observation(path,projection,model,nonce)
        assert result['status']=='verified' and result['material']=='Vacuum'
    macro=render_geometry_observer(projection,tmp_path,nonce)
    assert 'GetLooseBoundingBoxOfShape' not in macro
    assert 'Solid.GetVolume(' in macro and 'Boundary.GetStructureBox' in macro
