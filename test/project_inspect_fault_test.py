"""D4 fault matrix using owned synthetic projects; no CST or native activation."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest
from scripts import project_inspect as inspect
from test.project_inspect_test import cli, write_manifest

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path):
    (tmp_path/'docs').mkdir()
    (tmp_path/'core.py').write_text('def alpha(): return 1\n',encoding='utf-8')
    (tmp_path/'docs/api.md').write_text('# Live\n',encoding='utf-8')
    (tmp_path/'docs/project-map.schema.json').write_bytes((ROOT/'docs/project-map.schema.json').read_bytes())
    catalog=dict(schema_version=1,baseline=dict(commit='fixture',tracked_files=4,evidence_scope='synthetic'),
        domains=[],features=[dict(id='F1',purpose='fixture',sources=[dict(path='core.py',label='core',symbols=['alpha'])],
        tests=[],docs=[dict(path='docs/api.md',label='api',anchor='live')],provenance='fixture')],
        documents=[],tools=[],relations=[],source_fingerprints={})
    save(tmp_path,catalog)
    return tmp_path,catalog


def save(root,catalog):
    (root/inspect.CATALOG).write_text(json.dumps(catalog),encoding='utf-8')
    (root/'docs/feature-index.md').write_text(inspect.render(catalog),encoding='utf-8')
    write_manifest(root,[p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='release-manifest.json'])


def test_stale_heading_fenced_heading_and_duplicate_slugs(project):
    root,catalog=project
    (root/'docs/api.md').write_text('# Live\n```python\n# Fake\n```\n~~~\n# Other fake\n~~~\n# Live\n',encoding='utf-8')
    assert [h['anchor'] for h in inspect.headings(root,'docs/api.md')]==['live','live-1']
    catalog['features'][0]['docs'][0]['anchor']='fake'
    save(root,catalog)
    result=inspect.validate(root,catalog,validation_scope='package')
    assert not result['valid']
    assert any('heading missing' in e.get('message','') for e in result['errors'])


def test_missing_fingerprint_does_not_silently_refresh(project):
    root,catalog=project
    catalog['source_fingerprints']['core.py']='0'*64
    save(root,catalog)
    before=(root/inspect.CATALOG).read_bytes()
    result=inspect.validate(root,catalog,validation_scope='package')
    assert result['valid'] and result['warnings'][0]['kind']=='changed-since-capture'
    assert (root/inspect.CATALOG).read_bytes()==before


@pytest.mark.parametrize('fault',['hash','missing','content-id'])
def test_release_integrity_faults_are_not_success(project,fault):
    root,catalog=project
    if fault=='hash':(root/'core.py').write_text('def alpha(): return 2\n',encoding='utf-8')
    elif fault=='missing':(root/'core.py').unlink()
    else:
        value=json.loads((root/'release-manifest.json').read_text(encoding='utf-8'));value['content_sha256']='0'*64
        (root/'release-manifest.json').write_text(json.dumps(value),encoding='utf-8')
    result=inspect.validate(root,catalog,validation_scope='package')
    assert not result['valid'] and not result['release_integrity']['valid']
    assert any(e.get('kind')=='release-integrity' for e in result['errors'])


@pytest.mark.parametrize('path',['../outside.py','C:/outside.py','dir/file:stream','release-manifest.json','./core.py'])
def test_untrusted_manifest_path_fails_before_inventory(project,path):
    root,_=project
    value=json.loads((root/'release-manifest.json').read_text(encoding='utf-8'))
    value['files'][path]='0'*64
    (root/'release-manifest.json').write_text(json.dumps(value),encoding='utf-8')
    result=cli(root,'inventory')
    assert result.returncode==1 and 'Traceback' not in result.stderr
    assert 'error' in json.loads(result.stdout)


def test_graph_zero_limit_preserves_total_and_no_results(project):
    root,catalog=project
    (root/'calls.py').write_text('import core\ncore.alpha()\n',encoding='utf-8');save(root,catalog)
    result=cli(root,'graph','--limit','0')
    value=json.loads(result.stdout)['result']
    assert result.returncode==0 and value['relations']==[] and value['total']>0 and value['truncated']


def test_directory_rename_reports_old_and_new_paths(project):
    root,_=project
    def git(*args):return subprocess.run(['git','-C',str(root),*args],capture_output=True,check=True)
    git('init');git('add','.');git('-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-m','baseline')
    (root/'source').mkdir();(root/'source/a.py').write_text('def move(): pass\n',encoding='utf-8')
    git('add','.');git('-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-m','source baseline')
    git('mv','source','moved')
    result=cli(root,'changes')
    assert result.returncode==0,result.stderr
    assert {'source/a.py','moved/a.py'} <= set(json.loads(result.stdout)['result']['changed_paths'])


def test_malformed_catalog_has_structured_error(project):
    root,_=project
    (root/inspect.CATALOG).write_text('{',encoding='utf-8')
    result=cli(root,'query','--feature','F1')
    assert result.returncode==1 and 'error' in json.loads(result.stdout) and 'Traceback' not in result.stderr


def test_package_omissions_are_explicit_and_repository_scope_still_fails(project):
    root,catalog=project
    catalog['features'][0]['tests']=[dict(path='test/not-shipped.cst',label='omitted fixture')]
    save(root,catalog)
    partial=inspect.validate(root,catalog,validation_scope='package')
    assert partial['valid'] and partial['omitted_references']==['test/not-shipped.cst']
    assert partial['repository_complete'] is False and partial['release_integrity']['valid']
    assert not inspect.validate(root,catalog)['valid']


def test_resolved_escape_is_rejected_including_render_write(project,monkeypatch):
    root,_=project
    original=Path.resolve
    external=root.parent/'outside-index.md'
    def redirect(path,*args,**kwargs):
        return external if path==root/'docs/feature-index.md' else original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',redirect)
    with pytest.raises(ValueError,match='escapes'):inspect.safe_path(root,'docs/feature-index.md')
    # Render's write path must use the same guard. No OS symlink privileges required.
    import io,sys
    monkeypatch.setattr(sys,'stdout',io.TextIOWrapper(io.BytesIO(),encoding='utf-8'))
    monkeypatch.setattr(sys,'argv',['project_inspect','--root',str(root),'render','--write'])
    with pytest.raises(ValueError,match='escapes'):inspect.main()
    assert not external.exists()


def test_package_scope_cannot_be_used_to_waive_git_checkout(project):
    root,catalog=project
    subprocess.run(['git','-C',str(root),'init'],capture_output=True,check=True)
    result=inspect.validate(root,catalog,validation_scope='package')
    assert not result['valid']
    assert any(e.get('kind')=='package-scope-requires-extracted-release' for e in result['errors'])


def test_package_only_document_is_required_in_manifest(project):
    root,catalog=project
    catalog['documents']=[dict(path='README.md',role='generated-package-guide',authority='package-only',
        provenance='fixture',availability='package-only')]
    save(root,catalog)
    result=inspect.validate(root,catalog,validation_scope='package')
    assert not result['valid']
    assert any('required package document' in e.get('message','') for e in result['errors'])


@pytest.mark.parametrize('value',[[],{'schema_version':9,'files':{}},{'schema_version':1,'files':{'core.py':'wrong'}}])
def test_invalid_manifest_shape_is_structured_error(project,value):
    root,_=project
    (root/'release-manifest.json').write_text(json.dumps(value),encoding='utf-8')
    result=cli(root,'inventory')
    assert result.returncode==1 and 'error' in json.loads(result.stdout)
    assert 'Traceback' not in result.stderr


def test_fenced_only_heading_does_not_satisfy_contract(project):
    root,catalog=project
    (root/'docs/api.md').write_text('```\n# Live\n```\n',encoding='utf-8');save(root,catalog)
    assert not inspect.validate(root,catalog,validation_scope='package')['valid']
