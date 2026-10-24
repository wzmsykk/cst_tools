# Start=0、恢复保存与退出1：证据边界

2026-10-20用户提供会话49ab9d3a的生命周期及应用日志：求解约52分钟后Start=0；失败Completion ACK清理；之后恢复203项参数表达式、Rebuild True、Save返回、batch-return；Python检测退出码1。另一个98f0264b会话不能与其拼接时间线。

确认：求解失败和VBA恢复保存路径发生；源码当前拒绝退出1。未确认：StopAck/恢复快照/恢复凭据的实际内容及CST最终批返回异常原因。用户给的是诊断文件定位事件而非诊断JSON本体，不得声称这些产物已核验。用户现场文件未复制进Git。

源码审计另发现正常stop与显式恢复核验条件不同；构造ManagedSessionRecord(marker=stopped, has_stop_ack=True)的只读探针在process_alive为True/None时仍返回needs_recovery=False。这是独立控制层缺口，不证明本次现场由它引起。

更新后的协议范围、拟定收尾回执、故障矩阵及L1–L5待办见[协议设计](../docs/python-vba-lifecycle-protocol-v2-plan.md)。本轮仅文档修订；不改退出码白名单，不把Save日志等同于安全退出，也不把失败任务当作确认频段。
