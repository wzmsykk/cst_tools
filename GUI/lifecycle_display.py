"""Plain-text diagnostics for both legacy and v2 Runner snapshots."""


def lifecycle_lines(status):
    facts = status.get('lifecycle')
    if not isinstance(facts, dict):
        facts = {}
    lines = [f"收尾事实：{facts.get('session_count', '未知')} 个会话；仅观测，不自动恢复或采用结果",
             f"观测时间：{facts.get('observed_at', '尚未采集，不能据此确认退出')}"
             + ('（上次后台的历史观测）' if facts.get('historical') else '')]
    if facts.get('preprocessor_recovery_required'):
        lines.append('预处理进程：尚未确认退出')
    if facts.get('omitted_sessions'):
        lines.append(f"另有 {facts['omitted_sessions']} 个会话未展开；安全汇总仍包含全部会话，待恢复优先显示")
    for item in facts.get('sessions', []):
        lines.extend([
            f"Worker {item['worker_id']} / 会话 {item['session_id']}",
            f"  进程：{item['process_state']}；退出码：{item['exit_code'] if item['exit_code'] is not None else '未观测'} ({item['exit_classification']})",
            f"  任务：{item['task_outcome']}；模型：{item['model_state']}",
            f"  标准收尾：{'已确认' if item['standard_closed'] else '未确认'}；处置：{item['disposition']}",
            f"  待处理证据：{', '.join(item['missing_evidence']) or '无'}",
            f"  Python结果登记：{item.get('result_observation', {}).get('state', 'unknown')}（非产物重新核验）",
            f"  结果登记详情：{item.get('result_observation', {})}",
            f"  工作区：{item['workspace']}",
            f"  VBA回执：{item['receipt_path']}",
            f"  Python退出观测：{item['evidence_path']}",
        ])
    for key in ('error_diagnostic', 'cleanup_diagnostic'):
        diagnostic = status.get(key) or {}
        for cause in diagnostic.get('chain', []):
            lines.append(f"异常 [{diagnostic.get('phase')}] {cause['type']}: {cause['message']}")
            for location in cause.get('locations', []):
                lines.append(f"  {location['path']}:{location['line']} ({location['function']})")
    if facts.get('diagnostic'):
        lines.append(f"事实采集失败：{facts['diagnostic']}")
    return lines


def runner_error_text(status):
    message = status.get('error')
    chain = (status.get('error_diagnostic') or {}).get('chain', [])
    if message and chain:
        cause = chain[-1]
        message += f"\n原因：{cause['type']}: {cause['message']}"
        locations = cause.get('locations', [])
        if locations:
            loc = locations[-1]
            message += f"\n源码：{loc['path']}:{loc['line']} ({loc['function']})"
    return message
