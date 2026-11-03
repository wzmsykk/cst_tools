"""Offline D2 contracts: fixtures are parsed, never imported or executed."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from scripts import project_inspect as inspect

ROOT = Path(__file__).resolve().parents[1]


def write_manifest(root,paths):
    files={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(paths)}
    value=dict(schema_version=1,files=files,base_commit='fixture',
               content_sha256=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest())
    (root/'release-manifest.json').write_text(json.dumps(value),encoding='utf-8')
    return value


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'a.py').write_text("raise RuntimeError('must not import')\ndef same(): pass\n", encoding='utf-8')
    (tmp_path / 'b.py').write_text('from a import same\nsame()\ndef same(): pass\nobj.connect(callback)\ngetattr(obj, name)()\n', encoding='utf-8')
    (tmp_path / 'broken.py').write_text('def (', encoding='utf-8')
    (tmp_path / 'docs/api.md').write_text('# API\n', encoding='utf-8')
    c = dict(schema_version=1, baseline=dict(commit='fixture', tracked_files=3,evidence_scope='test only'),
             domains=[dict(id='docs',purpose='documentation',patterns=['docs/**'],lifecycle_owner='authors')],
             features=[dict(id='F1',purpose='test function',sources=[dict(path='a.py',label='a',symbols=['same'])],
                            tests=[],docs=[dict(path='docs/api.md',label='api')],provenance='fixture')],
             documents=[],tools=[],relations=[],source_fingerprints={})
    (tmp_path / inspect.CATALOG).write_text(json.dumps(c),encoding='utf-8')
    write_manifest(tmp_path,['a.py','b.py','broken.py','docs/api.md',inspect.CATALOG])
    return tmp_path,c


def cli(root,*args):
    return subprocess.run([sys.executable,'-B',str(ROOT/'scripts/project_inspect.py'),'--root',str(root),*args],capture_output=True,text=True,encoding='utf-8')


def snapshot(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('value',['../outside','C:/outside','C:outside','/outside',r'a\b','','.'])
def test_path_escape_rejected(workspace,value):
    root,_=workspace
    with pytest.raises(ValueError):inspect.safe_path(root,value)


def test_symbol_ambiguity_unmapped_and_consumers(workspace):
    root,c=workspace
    q=inspect.query(root,c,symbol='same')
    assert q['ambiguous_symbol']
    assert {d['path'] for d in q['symbol_declarations']}=={'a.py','b.py'}
    assert any(p['path']=='broken.py' for p in q['analysis_problems'])
    q=inspect.query(root,c,path='a.py',delete=True)
    assert any(r['source']=='b.py' for r in q['consumer_candidates'])
    assert q['deletion']['safe_to_delete'] is False
    assert not q['verification_plan']['execution_permitted']
    q=inspect.query(root,c,path='b.py')
    assert q['unmapped_input'] and q['path_availability']['b.py']
    assert q['outgoing_candidates']


def test_static_callbacks_are_not_delivery_proof(workspace):
    root,_=workspace
    rows,problems=inspect.source_relations(root,['a.py','b.py','broken.py'])
    callbacks=[r for r in rows if r.get('registration_not_delivery')]
    assert callbacks[0]['callback_expression']=='callback'
    assert callbacks[0]['unknown']
    assert all(r['runtime_proven'] is False for r in rows if r['type']=='call-site-candidate')
    assert problems[0]['path']=='broken.py'


def test_inventory_denominator_unknown_and_recursive_domain(workspace):
    root,c=workspace
    result=inspect.inventory(root,c,paths=['a.py','docs/deep/file.md','utils/x.py','knowledge-base/vendor/a.md','model/x.cst'])
    assert result['denominator']==5
    assert result['explicitly_mapped']==1 and result['unmapped']==4
    assert result['files'][1]['domain']=='docs'
    assert result['files'][2]['category']=='preserved-utils'
    assert result['files'][3]['category']=='vendor'
    assert all(r['migration']['old_path']==r['migration']['target_path'] for r in result['files'])


@pytest.mark.parametrize('args,code',[(('query','--feature','F1'),0),(('query','--path','b.py'),2),
    (('query','--question','test'),0),(('delete','a.py'),0),(('tools',),0),(('inventory',),0),
    (('graph','--path','b.py','--limit','1'),0),(('changes',),2),(('graph','--limit','-1'),2)])
def test_cli_read_only_and_exit_status(workspace,args,code):
    root,_=workspace
    before=snapshot(root)
    result=cli(root,*args)
    assert result.returncode==code,result.stderr+result.stdout
    assert snapshot(root)==before
    if code==0:
        output=json.loads(result.stdout)
        assert output['input']['kind']=='source-release'
        if args[0]=='graph':assert output['result']['truncated']


def test_render_requires_explicit_write(workspace):
    root,c=workspace
    result=cli(root,'render')
    assert result.returncode==0 and result.stdout==inspect.render(c)
    assert not (root/'docs/feature-index.md').exists()
    assert cli(root,'render','--write').returncode==0
    assert (root/'docs/feature-index.md').read_text(encoding='utf-8')==inspect.render(c)


def test_changes_includes_staged_unstaged_deleted_and_untracked(workspace):
    root,_=workspace
    def git(*args):return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True)
    git('init');git('add','.');git('-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-m','baseline')
    (root/'a.py').write_text('def same(): return 1\n',encoding='utf-8');git('add','a.py')
    (root/'b.py').unlink()
    (root/'new.py').write_text('# untracked\n',encoding='utf-8')
    result=cli(root,'changes')
    assert result.returncode==0,result.stderr
    output=json.loads(result.stdout)['result']
    assert set(output['changed_paths'])=={'a.py','b.py','new.py'}
    assert output['execution_permitted'] is False
    deleted=next(r for r in output['impacts'] if r['path']=='b.py')
    assert deleted['path_availability']['b.py'] is False


def test_release_root_does_not_use_parent_git(workspace):
    root,_=workspace
    subprocess.run(['git','-C',str(root),'init'],check=True,capture_output=True)
    child=root/'extracted';child.mkdir()
    (child/'only.txt').write_text('fixture',encoding='utf-8')
    write_manifest(child,['only.txt'])
    assert inspect.scope(child)==['only.txt','release-manifest.json']


def test_unregistered_vba_symbol_is_locatable(workspace):
    root,c=workspace
    (root/'macro.vb').write_text('Sub Example()\nEnd Sub\n',encoding='utf-8')
    manifest=json.loads((root/'release-manifest.json').read_text(encoding='utf-8'))
    write_manifest(root,[*manifest['files'],'macro.vb'])
    result=inspect.query(root,c,symbol='Example')
    assert result['unmapped_input']
    assert result['symbol_declarations'][0]['path']=='macro.vb'


def test_graph_missing_path_is_not_empty_success(workspace):
    root,_=workspace
    result=cli(root,'graph','--path','absent.py')
    assert result.returncode==2
    assert json.loads(result.stdout)['result']['unmapped_input']
