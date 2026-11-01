"""Durable identity of an owned CST launcher, never a bare PID capability."""
import json
import math
import os
from pathlib import Path

import psutil
from .configuration import write_json_atomic


def capture_process_identity(root, pid, executable, project):
    process = psutil.Process(pid)
    created = process.create_time()
    actual = process.exe()
    if os.path.normcase(os.path.realpath(actual)) != os.path.normcase(os.path.realpath(executable)):
        raise ValueError('launcher executable identity mismatch')
    write_json_atomic(Path(root) / 'process-identity.json', {
        'schema_version': 1, 'session_id': Path(root).name, 'pid': pid,
        'create_time': created, 'executable': actual,
        'project': str(Path(project).resolve())})


def observe_process_identity(root, pid):
    """Return (state, reason): matched/absent/reused/unknown.

    A reused PID belongs to someone else. Missing old identity is never matched.
    """
    root = Path(root)
    try:
        value = json.loads((root / 'process-identity.json').read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or value.get('schema_version') != 1 or value.get('session_id') != root.name
                or type(pid) is not int or value.get('pid') != pid
                or not isinstance(value.get('create_time'), (float, int))
                or not math.isfinite(value['create_time'])
                or not isinstance(value.get('executable'), str)
                or Path(value['project']).resolve() != (root / 'worker-input.cst').resolve()):
            return 'unknown', '进程身份记录无效或工程归属不匹配'
    except FileNotFoundError:
        return 'unknown', '旧会话缺少进程身份记录，不能按裸PID等待'
    except (OSError, ValueError, TypeError, KeyError):
        return 'unknown', '进程身份记录无法读取或无效'
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - value['create_time']) > 0.001:
            return 'reused', 'PID已复用，当前进程不属于本会话'
        if os.path.normcase(os.path.realpath(process.exe())) != os.path.normcase(os.path.realpath(value['executable'])):
            return 'unknown', '进程可执行文件身份不匹配'
        return 'matched', '已核实PID、创建时间、程序和工程归属'
    except psutil.NoSuchProcess:
        return 'absent', '原启动进程已退出；仍须核实子进程和收尾证据'
    except (psutil.AccessDenied, OSError):
        return 'unknown', '无权限读取进程身份'
