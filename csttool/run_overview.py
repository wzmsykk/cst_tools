"""Readable run names and lightweight summaries; identities stay in metadata."""
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import re
import tempfile
import os
from threading import RLock

from .configuration import write_json_atomic


def write_text_atomic(path, text):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _safe(value):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(value)).strip(' .')[:60] or '运行'


def _cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')


def _status(value):
    labels = {'INITIALIZED':'已初始化','PREPARED':'已准备','RUNNING':'运行中',
              'STOPPING':'正在收尾','STOPPED':'已结束','INTERRUPTED':'已中断',
              'FAILED':'失败','RECOVERY_REQUIRED':'需要恢复'}
    return f'{labels[value]}（{value}）' if value in labels else str(value)


def _metadata(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    return value if isinstance(value, dict) else {}


def rebuild_log_index(project):
    """Index old directories without moving them or inventing missing metadata."""
    root = Path(project) / 'logs'
    root.mkdir(parents=True, exist_ok=True)
    lines = ['# 运行日志总览', '', '旧目录保持原路径；未记录的信息显示为未知。', '',
             '| 时间 | 用途 | 状态 | 首个错误 | 目录 / 摘要 |', '|---|---|---|---|---|']
    for directory in sorted(root.iterdir(), key=lambda p:p.name, reverse=True):
        if not directory.is_dir():
            continue
        metadata = directory / 'run.json'
        try:
            data = _metadata(metadata) if metadata.exists() else {}
        except (ValueError, OSError):
            data = {'status':'元数据损坏或不可读'}
        summary = directory / 'summary.md'
        # New active runs write their own summary; never race their creation.
        if metadata.is_file() and 'purpose' not in data and not summary.exists():
            write_text_atomic(summary, '\n'.join([
                '# 旧运行摘要', '', '此目录保持原路径；只据已有元数据提供入口，不推测结果成功。',
                f"- 工程：{data.get('project','未知')}",
                f"- 运行ID：{data.get('run_id',directory.name)}",
                f"- 创建时间：{data.get('created_utc','未知')}",
                f"- 状态：{data.get('status','未知')}",
                '- 频率范围、计算覆盖与首个错误：旧元数据未提供，需核对完整日志/检查点。',
                '', '[应用日志](application.log) · [JSONL](application.jsonl) · [元数据](run.json)',
            ])+'\n')
        target = (directory.name + '/summary.md') if summary.is_file() else directory.name + '/'
        # Use percent-encoded local relative links for spaces and non-ASCII names.
        from urllib.parse import quote
        first_error = data.get('first_error')
        first_error = first_error if isinstance(first_error, dict) else {}
        lines.append('| ' + ' | '.join(_cell(value) for value in (
            data.get('created_local', data.get('created_utc', '未知')),
            data.get('purpose','旧运行（用途未记录）'), _status(data.get('status','未知')),
            first_error.get('message','—'),
            f'[{directory.name}]({quote(target)})')) + ' |')
    write_text_atomic(root/'index.md', '\n'.join(lines)+'\n')


class RunOverview:
    def __init__(self, project, run_id, purpose='批量任务', *, resume=False, settings=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', run_id):
            raise ValueError('invalid run identity')
        self.project = Path(project).resolve()
        root = self.project/'logs'
        root.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone(timedelta(hours=8)))
        name = f"{now:%Y%m%d-%H%M%S}_{_safe(purpose)}_{'续跑' if resume else '新运行'}_{run_id[:8]}"
        legacy = root/run_id
        self.directory = legacy if legacy.is_dir() else root/name
        reuse = legacy.is_dir()
        # Preserve identity after creating a readable directory once.
        for candidate in root.glob('*/run.json'):
            try:
                if _metadata(candidate).get('run_id') == run_id:
                    self.directory = candidate.parent
                    reuse = True
                    break
            except (ValueError, OSError):
                continue
        if not reuse:
            suffix = 1
            while True:
                try:
                    self.directory.mkdir()
                    break
                except FileExistsError:
                    suffix += 1
                    self.directory = root/f'{name}_{suffix}'
        self.lock = RLock()
        manifest = self.directory/'run.json'
        self.data = _metadata(manifest) if manifest.exists() else {
            'schema_version':1, 'run_id':run_id, 'project':str(self.project),
            'created_utc':now.astimezone(timezone.utc).isoformat(), 'created_local':now.isoformat(),
            'purpose':purpose, 'resume':resume, 'status':'已建立', 'settings':settings or {},
        }
        self.data.setdefault('run_id', run_id)
        self.update()

    def update(self, **fields):
        with self.lock:
            self.data.update(fields)
            checkpoint = self.project/'save/csv/hom_scan_checkpoint.json'
            try:
                checkpoint_data = json.loads(checkpoint.read_text(encoding='utf-8'))
                self.data['coverage'] = checkpoint_data.get('coverage', {})
                self.data['mode_count'] = len(checkpoint_data.get('report', {}).get('modes', []))
                self.data['pending_count'] = len(checkpoint_data.get('pending', []))
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            self.data['updated_utc'] = datetime.now(timezone.utc).isoformat()
            write_json_atomic(self.directory/'run.json', self.data)
            error = self.data.get('first_error') or {}
            error = error if isinstance(error, dict) else {}
            coverage = self.data.get('coverage', {})
            coverage = coverage if isinstance(coverage, dict) else {}
            lines = ['# 运行摘要', '',
                f"- 用途：{self.data.get('purpose','未知')}",
                f"- 工程目录：{self.data.get('project','未知')}",
                f"- 源CST：{self.data.get('source_project','未知')}",
                f"- 准备后的CST：{self.data.get('prepared_project','未知')}",
                f"- 开始时间：{self.data.get('created_local',self.data.get('created_utc','未知'))}",
                f"- 状态：{_status(self.data.get('status','未知'))}（不以进程退出单独判定求解成功）",
                f"- 续跑：{self.data.get('resume','未知')}",
                f"- 运行ID：`{self.data['run_id']}`",
                f"- 配置：`{json.dumps(self.data.get('settings',{}),ensure_ascii=False,default=str)}`",
                f"- 连续确认计算边界：{coverage.get('confirmed_frontier','未知')} MHz",
                f"- 已完成计算窗口最高上限：{coverage.get('calculated_upper','未知')} MHz",
                f"- 已接收模式：{self.data.get('mode_count','未知')}；待处理区间：{self.data.get('pending_count','未知')}",
                '', '## 首个错误', '', error.get('message','未记录错误（不代表已经完成验收）'),
                f"- 原因：{error.get('reason','未知')}",
                f"- 记录ID：`{error.get('record_id','未知')}`；关联ID：`{error.get('error_ref','未知')}`",
                f"- 源码位置：`{error.get('source','未知')}`",
                f"- 诊断目录：`{error.get('diagnostics','未知')}`",
                f"- 恢复建议：{error.get('recovery_hint','检查完整日志')}" , '',
                f"- 任务：{error.get('job','未知')}；阶段：{error.get('phase','未知')}",
                f"- 任务ID：`{error.get('task_id','未知')}`；会话ID：`{error.get('session_id','未知')}`", '',
                '## 文件入口', '', '[应用日志](application.log) · [结构化日志](application.jsonl) · [元数据](run.json)',
                '', '任务记录见 tasks/，路径映射见各任务 artifacts.json。',
                '旧回执及原始大文件可能已清理；链接不保证产物仍存在。']
            write_text_atomic(self.directory/'summary.md', '\n'.join(lines)+'\n')
            rebuild_log_index(self.project)


class RunOverviewHandler(logging.Handler):
    def __init__(self, overview):
        super().__init__(logging.ERROR)
        self.overview = overview

    def emit(self, record):
        try:
            if not self.overview.data.get('first_error'):
                self.overview.update(first_error={
                    'message':record.getMessage()[:2000], 'reason':str(getattr(record,'reason',''))[:2000],
                    'record_id':getattr(record,'record_id',None),
                    'error_ref':getattr(record,'error_ref',None),
                    'source':f'{record.pathname}:{record.lineno}',
                    'diagnostics':str(getattr(record,'diagnostics','')),
                    'recovery_hint':str(getattr(record,'recovery_hint','检查完整日志')),
                    'job':str(getattr(record,'job','未知')), 'phase':str(getattr(record,'phase','未知')),
                    'task_id':str(getattr(record,'task_id',getattr(record,'task','未知'))),
                    'session_id':str(getattr(record,'session_id',getattr(record,'session','未知'))),
                })
        except Exception:
            self.handleError(record)
