# GUI 停止与退出确认

更新：2026-10-15。

生产GUI已迁移独立Runner，关闭可选择仅关界面或安全停止后退出，见[本机Runner](local-runner.md)。
下文保留进程内注入Backend路径的原行为/测试记录，不表示当前生产GUI仍同进程计算。

停止按钮只在 RUNNING 生效，确认默认“否”（关闭确认框同样取消）。确认后调用
`GuiRunController.request_stop`，后台线程调用应用服务的停止接口，不在 GUI 线程等待 CST。
提示明确阻塞操作需要等待，HOM 使用“继续未完成”恢复计算覆盖，不从头覆盖结果。

关闭窗口（包括空闲时）需要确认。确认后如仍有运行、停止或恢复线程，拒绝本次关闭，
保留事件循环与日志，待 `settled` 后重新进入关闭检查。重复关闭不重复确认/停止。
恢复正在进行时等待恢复，不启动另一项停止；恢复失败则保留窗口。

标准调用链：窗口 → Controller 停止线程 → ApplicationService → Backend.request_stop
→ Manager.request_stop → Managed Worker.request_stop → VBA 步骤停止检查；
运行线程沿 Backend.execute_run 的 finally 调用标准 Worker 收尾，所有相关线程结束后才允许关窗。
GUI 不新增强杀、QThread.terminate 或固定求解总超时。

停止接口异常即标为 RECOVERY_REQUIRED，即使后端误报无需恢复或运行线程随后返回成功，
也不能覆盖该状态。处于 RECOVERY_REQUIRED 时拒绝关窗，保留日志，提示先清理残留会话。
正常关窗最后才关闭 GUI 日志及应用日志。

## 边界与 TODO

- 线程结束本身不证明真实 CST 已安全退出；实际依赖现有后端协议/StopAck/进程归属门禁。
- 阻塞的 Rebuild、Solver.Start 或单个后处理算子不能即时抢占。
- 启动阶段 Manager 尚未创建/Worker 尚未注册时，停止请求仍可能暂时无接收者；窗口继续等待，不能宣称即时取消启动。
- TODO：真实 CST 下验证启动、计算、退出失败及恢复期间关窗；本批只做离线/假 Worker 验收。
- 外部结束 Python、系统关机或崩溃不受 closeEvent 保护。

测试入口：`test/gui_main_window_test.py`、`test/gui_fake_worker_flow_test.py`、
`test/gui_vacuum_matching_fake_flow_test.py`；包括取消、默认否、标准停止/等待、重复关闭及停止失败不自动退出。

2026-10-15 验收：上述三模块及文档索引共40项通过；排除三模块后的离线回归509项通过、19项集成测试未运行（文档索引在两批重复执行）。
完整单进程回归两次在GUI模块发生原生进程退出，其中一次返回0xC0000409；未定位根因，不认定全套单进程通过。
轻量记录在 `artifacts/gui-stop-exit-full.txt` 与 `artifacts/gui-stop-exit-rest-20261015.xml`，不保证随Git迁移。
TODO：定位全套运行中Qt对象/线程生命周期或环境问题，恢复单进程全套验收；不将分批通过冒称真实CST安全关闭。
