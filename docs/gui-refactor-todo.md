# GUI维护与剩余工作

2026-11-03。旧GUI P0–P9及Manager迁移过程、旧按钮/模式设计完整保存在[历史快照](archive/20261103-semantic-review/gui-refactor-todo.md)；旧runWithParam/队列接口、安全模式等条目不作为当前API。

生产GUI使用RunnerBackend草稿与RunnerController异步连接，进程内GuiRunController保留给明确注入路径。主工作台显示HOM结果，细节区显示生命周期/事件；日志清空功能已移除，自动滚动可切换，恢复读取持久历史。关闭界面与停止任务/退出后台有独立选择和证据，未知状态不冒充关闭。

当前待办统一在[现行TODO](minimal-python-vba-todo.md)，本页不维护第二份阶段勾选：更广真实退出/恢复/多窗口故障、显示性能及视觉、后台隔离策略扩展与新增MCP桌面门禁依各自专题验收。

实现/测试查[功能索引](feature-index.md)，操作与错误见[Runner](local-runner.md)、[退出清理](gui-exit-resource-cleanup.md)、[日志](gui-structured-log.md)。历史已打包、假Worker和offscreen截图都不能当当前真实桌面全流程已验。
