"""D3 registry scope and stale-declaration guards; never execute a registered tool."""
import copy
from pathlib import Path

from scripts import project_inspect as inspect

ROOT = Path(__file__).resolve().parents[1]


def test_actual_tool_and_markdown_registry_covers_declared_scope():
    catalog = inspect.load(ROOT)
    coverage = inspect.registry_coverage(ROOT, catalog)
    assert coverage['candidate_count'] == coverage['registered_count']
    assert coverage['candidate_count'] >= 66
    for key in ('missing','outside_scope','stale_observations','problems'):
        assert coverage[key] == [], (key, coverage[key])
    assert coverage['semantic_review_complete'] is False
    paths = inspect.scope(ROOT)
    documents = {d['path']: d for d in catalog['documents']}
    assert {p for p in paths if p.endswith('.md')} <= documents.keys()
    assert documents['test/fixtures/feature-index-before-d1.md']['authority'] == 'not-current-contract'
    assert any(d['role']=='unreviewed' for d in documents.values())
    for tool in catalog['tools']:
        assert tool['effect'] and tool['authorization'] and tool['unknown'] and tool['evidence']
    assert 'kill' in next(t for t in catalog['tools'] if t['path'].endswith('validate_controller_exit_l5.py'))['effect']


def test_discovery_reads_guards_helpers_and_shell_without_import(tmp_path):
    files = {
        'entry.py': "raise RuntimeError('never execute')\nif __name__ == '__main__':\n    parser.add_argument('--known')\n",
        'library.py': 'def nothing(): pass\n',
        'test/support/eager.py': "raise RuntimeError('import also unsafe')\n",
        'scripts/broken.py': 'def (',
        'run.bat': 'echo must not run',
        'utils/unchanged.py': "if __name__ == '__main__': dangerous()\n",
        'knowledge-base/vendor/vendor.py': "if __name__ == '__main__': dangerous()\n",
    }
    for path, text in files.items():
        target=tmp_path/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
    result=inspect.tool_candidates(tmp_path,paths=list(files))
    by_path={r['path']:r for r in result['candidates']}
    assert set(by_path)=={'entry.py','test/support/eager.py','scripts/broken.py','run.bat'}
    assert by_path['entry.py']['observed_arguments']==['--known']
    assert by_path['test/support/eager.py']['entry_kind']=='support-module'
    assert by_path['scripts/broken.py']['entry_kind']=='unparsed-support'
    assert result['problems'][0]['path']=='scripts/broken.py'


def test_registry_detects_new_removed_and_changed_entry(tmp_path,monkeypatch):
    (tmp_path/'entry.py').write_text("if __name__ == '__main__': parser.add_argument('--new')\n",encoding='utf-8')
    monkeypatch.setattr(inspect,'scope',lambda root:['entry.py'])
    assert inspect.registry_coverage(tmp_path,{'tools':[]})['missing']==['entry.py']
    catalog={'tools':[dict(path='entry.py',entry_kind='python-main',main_guard=True,observed_arguments=['--old'])]}
    assert inspect.registry_coverage(tmp_path,catalog)['stale_observations']==['entry.py']
    catalog['tools'][0]['path']='removed.py'
    assert inspect.registry_coverage(tmp_path,catalog)['outside_scope']==['removed.py']


def test_manual_relationships_include_lifecycle_evidence_and_unknowns():
    catalog=inspect.load(ROOT)
    assert len(catalog['relations'])>=18
    for relation in catalog['relations']:
        assert all(relation[key] for key in ('trigger','lifecycle','cleanup','evidence','unknown'))
        for locator in [relation['source'],*relation['targets'],*relation['consumers']]:
            assert locator['path'] in catalog['source_fingerprints']
    gui=next(r for r in catalog['relations'] if r['id']=='R001')
    assert any(t.get('symbol')=='RunnerController' for t in gui['targets'])
    window=next(r for r in catalog['relations'] if r['id']=='R016')
    assert window['type']=='registration' and window['unknown']


def test_consumer_is_queryable_and_stale_consumer_is_invalid():
    catalog=inspect.load(ROOT)
    result=inspect.query(ROOT,catalog,path='gui_app.py',analysis=([],[]))
    assert 'R001' in {r['id'] for r in result['registered_relations']}
    tool=inspect.query(ROOT,catalog,path='pack.bat',analysis=([],[]))
    assert tool['unmapped_input'] and tool['registered_tools'][0]['path']=='pack.bat'
    assert tool['registered_tools'][0]['unknown']
    broken=copy.deepcopy(catalog)
    broken['relations'][0]['consumers'][0]['symbol']='missing_consumer'
    result=inspect.validate(ROOT,broken)
    assert not result['valid']
    assert any(e.get('kind')=='relation' for e in result['errors'])


def test_duplicate_tool_relation_and_missing_scope_are_rejected():
    catalog=copy.deepcopy(inspect.load(ROOT))
    catalog['tools'].append(copy.deepcopy(catalog['tools'][0]))
    catalog['relations'].append(copy.deepcopy(catalog['relations'][0]))
    catalog['tools']=[t for t in catalog['tools'] if t['path']!='pack.bat']
    catalog['documents']=[d for d in catalog['documents'] if d['path']!='docs/README.md']
    result=inspect.validate(ROOT,catalog)
    kinds={e.get('kind') for e in result['errors']}
    assert {'duplicate-tools','duplicate-relation-id','tool-registry-incomplete','document-registry-incomplete'} <= kinds
