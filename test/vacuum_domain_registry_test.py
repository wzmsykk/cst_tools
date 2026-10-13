from pathlib import Path
import pytest

from csttool.configuration import write_json_atomic
from csttool.field_artifacts import SamplingSpec
from csttool.geometry_support import load_material_support
from csttool.result_reconciliation import file_hash
from csttool.vacuum_domain_registry import validate_inventory, render_vacuum_preflight, load_registered_support


def inventory(tmp_path, *, background='PEC', boundary='electric', material='Vacuum', ports='0'):
    path=tmp_path/'inventory.tsv'
    path.write_text(f'background\t{background}\nboundaries\t'+ '\t'.join([boundary]*6)+
        f'\nsymmetry\tnone\tnone\tnone\nports\t{ports}\nsolid\tcavity:vacuum\t{material}\t0\t1\t0\t1\t0\t1\n')
    return path


def spec(): return SamplingSpec((0,1,0,1,0,1),(2,2,2),'specified-domain')


@pytest.mark.parametrize('kwargs,reason',[
    ({'background':'Normal'},'background-not-PEC'),
    ({'boundary':'open'},'boundaries-not-six-electric'),
    ({'material':'Copper'},'non-vacuum-solid'),
    ({'ports':'1'},'ports-present-or-unknown'),
])
def test_preflight_rejects_unsupported_engineering(tmp_path,kwargs,reason):
    assert reason in validate_inventory(inventory(tmp_path,**kwargs),spec())[1]


def test_preflight_requires_full_coverage_and_read_only_documented_queries(tmp_path):
    path=inventory(tmp_path)
    assert not validate_inventory(path,spec())[1]
    clipped=SamplingSpec((.1,.9,0,1,0,1),(2,2,2),'specified-domain')
    assert 'sampling-box-does-not-cover-solid' in validate_inventory(path,clipped)[1]
    source=render_vacuum_preflight(path)
    for method in ('Material.GetTypeOfBackgroundMaterial','Solid.IsSolidShape',
                   'Solid.GetLooseBoundingBoxOfShape','Port.StartPortNumberIteration'):
        assert method in source
    assert 'Rebuild' not in source and 'Solver.Start' not in source


def registration(tmp_path):
    inv=inventory(tmp_path)
    mask=tmp_path/'support.tsv'
    mask.write_text('Vacuum\n'*8)
    support=load_material_support(spec(),mask,expected_sha256=file_hash(mask),geometry_id='geometry')
    data={'status':'registered','source_sha256':'source','sampling_id':spec().identity,
          'geometry_id':'geometry','source_unchanged':True,'inventory_sha256':file_hash(inv),
          'support_file':'support.tsv','support_sha256':file_hash(mask),'support_id':support.identity}
    path=tmp_path/'domain-registration.json'
    write_json_atomic(path,data)
    return path


def test_registry_binds_source_sampling_and_masks(tmp_path):
    path=registration(tmp_path)
    args={'source_sha256':'source','sampling':spec(),'geometry_id':'geometry'}
    assert load_registered_support(path,**args).verified
    with pytest.raises(ValueError): load_registered_support(path,**{**args,'source_sha256':'other'})
    (tmp_path/'support.tsv').write_text('excluded\n'*8)
    with pytest.raises(ValueError,match='changed'): load_registered_support(path,**args)


def test_registry_rechecks_inventory(tmp_path):
    path=registration(tmp_path)
    inventory(tmp_path,boundary='open')
    with pytest.raises(ValueError,match='inventory changed'):
        load_registered_support(path,source_sha256='source',sampling=spec(),geometry_id='geometry')


def test_rejected_preflight_never_exports_fields(tmp_path,monkeypatch):
    from csttool.vacuum_domain_registry import export_registered_vacuum_fields
    monkeypatch.setattr('csttool.vacuum_domain_registry.register_vacuum_domain',
        lambda *args,**kwargs: {'status':'rejected','rejection_reasons':['background-not-PEC']})
    def forbidden(*args,**kwargs): raise AssertionError('must not export rejected project')
    monkeypatch.setattr('csttool.saved_field_export.export_saved_fields',forbidden)
    settings=[{'method':'ExportModeField','params':{'field_kind':'E','sampling':spec().to_mapping()}}]
    with pytest.raises(ValueError,match='preflight rejected'):
        export_registered_vacuum_fields('cst.exe','source.cst',tmp_path/'export',settings,geometry_id='geometry')
