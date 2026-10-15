"""Build a source snapshot, including explicit working-tree identity, without committing."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def included(name):
    path = Path(name)
    if path.parts[0] in {'csttool', 'GUI', 'algs', 'utils', 'test', 'scripts'}:
        return path.suffix in {'.py', '.ui', '.csv'} and '__pycache__' not in path.parts
    if path.parts[0] in {'data', 'template'}:
        return path.suffix in {'.py', '.vb', '.bas', '.json', '.def', '.txt', '.ini'}
    if path.parts[0] == 'docs':
        return path.suffix == '.md'
    if path.parts[0] == 'knowledge-base':
        return len(path.parts) == 2 and path.suffix == '.md'
    return name in {'gui_app.py', 'install_compat.py', 'pyproject.toml', 'AGENTS.md',
                    'win.bat', 'config/default.ini', 'config/project.example.ini'}


def build(destination):
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    paths = subprocess.check_output(['git', 'ls-files', '-c', '-o', '--exclude-standard'], cwd=ROOT,
                                    text=True).splitlines()
    files = {path: (ROOT / path).read_bytes() for path in sorted(set(paths))
             if included(path) and (ROOT / path).is_file()}
    project = tomllib.loads(files['pyproject.toml'].decode())['project']
    dependencies = project['dependencies'] + project['optional-dependencies']['field-analysis']
    files['requirements.txt'] = ('\n'.join(dependencies) + '\n').encode()
    files['README.md'] = '''# CST Tools 源码发布版

依赖Windows、Python 3.10+和本机CST/许可证；不内置环境、模型、厂商帮助或验收artifacts。
在解压目录安装依赖并启动，不能假定客户端和Runner有相同的其他盘符路径。

```powershell
python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
.\\.venv\\Scripts\\python.exe gui_app.py
```

生产GUI使用独立本机Runner。选择项目后连接/启动Runner；仅关闭界面可保留后台计算。
安全停止会等待标准收尾，不强杀CST；状态未知不代表停止成功。多窗口控制权可能需等待10秒释放。
使用 docs/local-runner.md 查看CLI、恢复与限制；实际阶段证据见 docs/execution-platform-implementation-plan.md。

不启动CST的检查：python gui_app.py --smoke-test；python -m csttool.runner --help。
测试源码随包提供，但不包含CST夹具，不能声称解压包全部集成测试可直接运行。
发布烟雾检查不代表目标机器真实CST、桌面交互或远程/分布式验收。
完整身份和文件校验见 release-manifest.json；working标记表示包含尚未提交源码快照。
'''.encode('utf-8')
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in sorted(files.items())}
    content_id = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    date = datetime.now().strftime('%Y%m%d')
    name = f"cst-tools-{project['version']}-source-{commit[:7]}-working-{content_id[:8]}-{date}"
    manifest = {'schema_version': 1, 'base_commit': commit, 'working_tree_snapshot': True,
                'content_sha256': content_id, 'files': hashes}
    files['release-manifest.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / (name + '.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
        for path, data in sorted(files.items()):
            stream.writestr(name + '/' + path, data)
    with zipfile.ZipFile(archive) as stream:
        assert stream.testzip() is None
        for path, expected in hashes.items():
            assert hashlib.sha256(stream.read(name + '/' + path)).hexdigest() == expected
        with tempfile.TemporaryDirectory(prefix='source-check-', dir=destination) as temporary:
            stream.extractall(temporary)
            folder = Path(temporary) / name
            subprocess.run([sys.executable, '-c',
                "import pathlib; [compile(p.read_text(encoding='utf-8-sig'),str(p),'exec') for p in pathlib.Path('.').rglob('*.py')]; import csttool.runner; import sys; assert 'PyQt5' not in sys.modules"],
                cwd=folder, check=True, capture_output=True)
            subprocess.run([sys.executable, 'gui_app.py', '--smoke-test'], cwd=folder,
                env=dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1'),
                check=True, timeout=45, capture_output=True)
    receipt = {'archive': str(archive.resolve()), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
               'bytes': archive.stat().st_size, 'files': len(files), 'content_sha256': content_id,
               'zip_and_hashes': 'passed', 'compile_no_qt_runner': 'passed', 'gui_smoke': 'passed'}
    (destination / (name + '-receipt.json')).write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=ROOT / 'dist')
    build(parser.parse_args().destination)
