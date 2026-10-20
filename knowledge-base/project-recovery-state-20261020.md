# 恢复标志与会话安全不是同一状态

2026-10-20现场输入：application.jsonl仅12条初始化/拒绝续跑事件；project.ini为RECOVERY_REQUIRED，Runner status为FAILED、initializing、confirmed-closed。没有本轮求解开始的证据，不能将其解释为CST计算失败。

源码核查确认：普通续跑只重置FAILED；后端异常分支和Runner仅会话检测遗漏持久恢复标志。新恢复后端未加载配置，旧顺序还可能在释放锁、打印完成后才写状态失败。这是Python控制层缺陷，不是新发现的CST API语义。

修正将项目门禁独立于进程安全，恢复配置加载/对账/持久化放在同一项目锁内。完成日志必须晚于持久写。检查点确认前沿与已计算上界分别保留，不能绕过中间未确认区间。

实现、离线测试和未完成的真实CST/现场部署边界见[恢复状态对账](../docs/project-recovery-state-reconciliation.md)。用户原日志/工程没有复制进仓库；artifacts轻量测试报告不保证随Git迁移。未声称现场数据已被修复。
