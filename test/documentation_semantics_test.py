"""Selected semantic regressions, not a proof of every natural-language claim."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

from scripts import project_inspect as inspect

ROOT=Path(__file__).resolve().parents[1]


def text(name):return (ROOT/'docs'/name).read_text(encoding='utf-8')


def test_current_entries_do_not_stack_old_stage_updates():
    status=text('current-status.md');todo=text('minimal-python-vba-todo.md')
    assert not re.search(r'^## (?:2026-|本批|最新收口|当前桌面|当前真正下一步)',status,re.M)
    assert todo.count('## 近期工作顺序')==1
    assert 'archive/20261103-semantic-review/' in status and 'archive/20261103-semantic-review/' in todo
    assert '\nww\n' not in todo


def test_manager_document_defaults_and_worker_protocol_match_source():
    tree=ast.parse((ROOT/'csttool/cstmanager.py').read_text(encoding='utf-8'))
    manager=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CSTManager')
    init=next(n for n in manager.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    positional=dict(zip([a.arg for a in init.args.args][-len(init.args.defaults):],init.args.defaults))
    keyword=dict(zip([a.arg for a in init.args.kwonlyargs],init.args.kw_defaults))
    assert ast.literal_eval(positional['maxTask'])==2
    assert ast.literal_eval(keyword['max_jobs_per_worker'])==6
    api=text('cstmanager-api.md');design=text('cstmanager-design.md')
    assert 'max_jobs_per_worker=6' in api and '构造器默认2' in api
    assert 'GlobalSettings' in api and 'ProjectSettings' in api and 'get_postprocess_settings' in api
    assert 'run_task' in design and '新的worker ID' in api
    # Actual example calls, unlike negative historical references in prose.
    examples='\n'.join(re.findall(r'```python\n(.*?)```',api,re.S))
    assert 'runWithParam(' not in examples and 'getCurrPPSList(' not in examples


def test_protocol_and_timeout_operational_statements_are_current():
    source=ast.parse((ROOT/'csttool/managed_cstworker.py').read_text(encoding='utf-8'))
    worker=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='ManagedCSTWorker')
    values={target.id:ast.literal_eval(n.value) for n in worker.body if isinstance(n,ast.Assign)
            for target in n.targets if isinstance(target,ast.Name) and isinstance(n.value,ast.Constant)}
    assert values['START_TIMEOUT']==120 and values['STOP_TIMEOUT']==600
    protocol=text('minimal-python-vba-protocol.md')
    assert '失败' in protocol and 'ACK是消费/清理授权' in protocol
    assert '生产CSTPMW_CloseSession不调用Quit' in protocol
    assert '生产Managed生成器显式声明v2' in text('close-receipt-v2.md')
    assert '全局Solver调用预算时抛IncompleteScanError' in text('hom-scan-algorithm.md')
    assert 'HOM_SCAN_COMPLETED_WITH_GAPS' in text('hom-scan-algorithm.md')
    assert '30秒等待记录为DEBUG' in text('current-status.md') or '30秒等待记录为DEBUG' in text('application-backend.md')


def test_registry_exposes_each_document_review_and_source_limits():
    catalog=inspect.load(ROOT)
    for document in catalog['documents']:
        review=document['review']
        assert re.fullmatch(r'[0-9a-f]{7,40}', review['baseline'])
        assert review['scope'] and review['limitations']
        for source in review['checked_sources']:
            assert (ROOT/source['path']).is_file(),source
    q=inspect.query(ROOT,catalog,feature='F138',analysis=([],[]))
    assert any(row.get('review') for row in q['required_reading'])


def normalize_links(body,parent):
    def replace(match):
        target=match[2]
        if re.match(r'^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|#|/)',target):return match[0]
        path,sep,anchor=target.partition('#')
        return '['+match[1]+']('+str((parent/path).resolve())+sep+anchor+')'
    return re.sub(r'\[([^]]+)\]\(([^)]+)\)',replace,body).replace('\r\n','\n')


def test_archived_prose_is_preserved_including_old_pending_and_evidence():
    report=json.loads((ROOT/'knowledge-base/documentation-semantic-review-20261103.json').read_text(encoding='utf-8'))
    for item in report['archives']:
        original=subprocess.check_output(['git','-C',str(ROOT),'show','2705935:'+item['source']])
        assert hashlib.sha256(original).hexdigest()==item['original_git_blob_sha256']
        archive=(ROOT/item['archive']).read_text(encoding='utf-8')
        start=re.search(r'^# ',archive,re.M).start()
        assert normalize_links(archive[start:],(ROOT/item['archive']).parent)==normalize_links(original.decode('utf-8'),(ROOT/item['source']).parent)


def test_followup_current_pages_have_concrete_review_and_no_pending_classification():
    catalog=inspect.load(ROOT)
    report=json.loads((ROOT/'knowledge-base/documentation-semantic-review-20261103.json').read_text(encoding='utf-8'))
    documents={d['path']:d for d in catalog['documents']}
    assert len(report['followup']['documents'])==22
    for path in report['followup']['documents']:
        review=documents[path]['review']
        assert review['checked_sources'] and review['status']!='applicability-only-reviewed'
    assert not [d['path'] for d in catalog['documents'] if d['review']['status']=='applicability-only-reviewed']


def test_capture_and_diagnostic_docs_do_not_hide_current_integration():
    module=ast.parse((ROOT/'csttool/diagnostic_bundle.py').read_text(encoding='utf-8'))
    export=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='export_failure_bundle')
    args={a.arg for a in export.args.kwonlyargs}
    assert {'cancel_check','progress'}<=args
    doc=text('failure-diagnostic-export.md')
    assert 'cancel_check=None' in doc and 'progress=None' in doc
    assert '公共single-simulation服务接入仍待实施' not in text('native-execution-capture.md')
    assert 'execution_config' in text('native-execution-capture.md')


def test_w0_core_calibration_is_distinct_from_production_codegen_gate():
    for name in ('winwrap-w0-contract.md','winwrap-codegen-safety-plan.md'):
        doc=text(name)
        assert '14' in doc and 'W1' in doc and 'W3' in doc
        assert '核心宿主校准未完成' not in doc
        assert 'MacroCheckThis真实宿主校准待验' not in doc
        assert 'ByRef' in doc and '未完成' in doc


def test_document_review_fingerprints_match_reviewed_markdown():
    for document in inspect.load(ROOT)['documents']:
        path=ROOT/document['path']
        if path.is_file():
            assert hashlib.sha256(path.read_bytes()).hexdigest()==document['review']['content_sha256_at_review'], document['path']
