# Runner生命周期事实的展示边界

2026-10-24源码审计：旧LocalExecution.session_safety直接使用get_recovery_sessions，导致标准关闭但Completion待对账也显示unknown。
现共用evaluate_closure，物理退出和项目恢复独立；不改变采用和恢复门禁。
Python异常包装会隐藏首因，现通过结构化原因链与源码位置传递，清理异常另存。
最新任务的结果receipt阶段仅为持久登记观测，不能把ACK或algorithm_adopted文字当产物重新核验。
以上为源码/离线发现，不是新增CST实测行为；真实WinWrap和CST仍需L5。
实现、兼容和验收入口见[说明](../docs/runner-lifecycle-l4.md)。
