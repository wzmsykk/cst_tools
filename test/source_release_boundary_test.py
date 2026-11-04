"""Real source ZIP/compile/offscreen-GUI acceptance; never starts CST."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from scripts import build_source_release as release

ROOT=Path(__file__).resolve().parents[1]


def test_release_selection_keeps_offline_contract_inputs_and_excludes_heavy_models():
    for name in ['docs/project-map.json','docs/project-map.schema.json','test/fixtures/feature-index-before-d1.md',
                 'test/fixtures/antlr-vb6-poc/retained-history.vb','test/support/run_cst_contract.ps1',
                 'base.py','base_WTC.py','base_tm020.py','knowledge-base/project-registry-d3-20261103.json']:
        assert release.included(name),name
    assert release.included('data/winwrap-a1-calibration.json')
    assert release.included('knowledge-base/winwrap-w23-20261103.json')
    assert release.included('csttool/geometry_codegen.py')
    for name in ['model/Pillbox.cst','test/data/Pillbox.cst','artifacts/raw.h5',
                 'knowledge-base/vendor/cst-2022-vba-help/README.md','test/__pycache__/cached.pyc']:
        assert not release.included(name),name


def test_real_source_package_boundary(tmp_path):
    archive=release.build(tmp_path/'build')
    receipt=json.loads(archive.with_name(archive.stem+'-receipt.json').read_text(encoding='utf-8'))
    assert receipt['compile_no_qt_runner']==receipt['gui_smoke']=='passed'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==receipt['sha256']
    target=tmp_path/'extracted';target.mkdir()
    with zipfile.ZipFile(archive) as stream:
        assert stream.testzip() is None
        for name in stream.namelist():
            assert (target/name).resolve().is_relative_to(target.resolve())
        stream.extractall(target)
    folder=target/archive.stem
    assert not (folder/'.git').exists()
    manifest=json.loads((folder/'release-manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest
    assert not any(p.suffix.lower() in {'.cst','.h5','.chm'} for p in folder.rglob('*'))
    before={p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
    # Packaging must preserve the actual source-bound gate, including a stale
    # refusal. Offline packaging is not permission to manufacture native proof.
    probe='''import json
from csttool.winwrap_checks import require_calibration, require_geometry_calibration
from csttool.winwrap_emitter import GeneratedCodeError
decisions={}
for name,check in [('a1',require_calibration),('geometry',lambda:require_geometry_calibration('geometry')),
                   ('geo-simulation',lambda:require_geometry_calibration('simulation'))]:
    try:check()
    except GeneratedCodeError as error:decisions[name]=dict(accepted=False,code=error.code)
    else:decisions[name]=dict(accepted=True)
print(json.dumps(decisions))
'''
    def calibration(directory):
        result=subprocess.run([sys.executable,'-B','-c',probe],cwd=directory,capture_output=True,text=True)
        assert result.returncode==0,result.stdout+result.stderr
        return json.loads(result.stdout)
    assert (folder/'data/winwrap-a1-calibration.json').read_bytes()==(ROOT/'data/winwrap-a1-calibration.json').read_bytes()
    if (ROOT/'data/geometry-calibration.json').exists():
        assert (folder/'data/geometry-calibration.json').read_bytes()==(ROOT/'data/geometry-calibration.json').read_bytes()
    assert calibration(folder)==calibration(ROOT)
    def run(*args):
        result=subprocess.run([sys.executable,'-B','scripts/project_inspect.py',*args],cwd=folder,capture_output=True,encoding='utf-8')
        return result,json.loads(result.stdout) if result.stdout.startswith('{') else None
    package,data=run('validate','--scope','package')
    assert package.returncode==0,package.stdout+package.stderr
    result=data['result']
    assert result['valid'] and result['release_integrity']['valid'] and not result['repository_complete']
    assert result['warnings']==[]
    assert set(result['omitted_references'])=={'pack.bat','GUI/createpyfromui.bat','knowledge-base/vendor/cst-2022-vba-help/README.md'}
    full,data=run('validate')
    assert full.returncode==1 and not data['result']['valid']
    for args in [('query','--feature','F138'),('inventory',),('graph','--path','scripts','--limit','2')]:
        checked,data=run(*args)
        assert checked.returncode==0,checked.stdout+checked.stderr
        assert data['input']['kind']=='source-release'
    changes,_=run('changes')
    assert changes.returncode==2
    assert before=={p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
