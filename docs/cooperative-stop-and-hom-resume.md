# Worker协作停止与HOM计算覆盖续跑

2026-10-14。恢复依据为已确认计算覆盖，不是找到的最高模式频率；确认无模式的窗口也推进覆盖。

## 停止路径

Manager.request_stop先停止派发，再对已注册Worker调用非阻塞request_stop，发布原有session-bound stop.request；不等run_task锁，不直接结束CST进程。未实现该方法的假Worker仍沿用旧标准收尾。发布失败保留异常，标准stop仍须确认StopAck和进程退出。

Managed VBA在Main启动时检查停止文件，在参数更新前及每项之间、重建前后、求解前后、后处理条目之间和写快照前检查；有效停止请求引发协作中断。render_vb(cooperative_stop=True)只供Managed使用，其他宏默认不引用Managed钩子。停止身份校验沿用原协议；不新建ABI或取消服务。

正在阻塞的Rebuild、EigenmodeSolver.Start或单个复杂后处理算子不能被这些检查点抢占；要等调用返回。此批没有未经验证地调用Solver停止API，也不强杀。Manager尚未注册的启动中Worker不能立即收到广播；VBA启动前已经存在的有效stop.request可在Main直接退出，GUI创建/加载期间的即时取消仍需进一步联调，不宣称任何时刻即时响应。

停止后仍走保存/StopAck/批返回。已有任务但未形成完成标记时，发布INTERNAL_ERROR且消息前缀STOP_REQUESTED，保留任务、完成文件供原有确认/恢复流程。无需新增协议错误码，但调用者应结合Manager停止状态区分普通内部错误。

若Solver成功且存在模式，停止检查会先捕获当前表达式、禁止回滚覆盖这次求解结果，并Backup为当前任务目录interrupted-project.cst；Trace记录interrupted-solve。此副本只是求解保留证据，不代表后处理或结果接收成功。旧确认快照不覆盖。若中断发生在未成功求解阶段，沿用最后良好参数恢复，不将半完成结果冒称可用。

Ack等待阶段沿用stopped-with-completion保留结果逻辑。完整但尚未Ack/算法采纳的结果优先沿用已有接收记录及恢复链；本批不新增从任意VBA指令位置续执行的功能。

## 覆盖账本与防覆盖

AdaptiveHomScanner在每个区间进入求解前原子保存检查点，将当前区间放在pending首项；用户停止造成回调失败时立即ScanInterrupted，不记录为空区间、不推进、不按失败重试。成功完成当前区间后再按既有窄窗口/逐模式算法推进。

检查点追加coverage（旧schema及加载兼容）：

- confirmed_frontier：最早pending/failed区间的下界；没有缺口时为扫描终点。它反映可以安全继续的位置，包括已确认空区间，不按modes频率取最大值。
- calculated_upper：成功完成的计算窗口最大上限，用于诊断计算推进到哪里，不自动用于跳过未确认窗口或尚待枚举的范围。

实际续跑使用原有completed/empty/failed/pending账本及确认快照，不用单个最高频率替代账本。单模式计算窗口完成不意味着窗口中后续所有模式已经枚举，既有模式之后的窄窗口推进仍保持；该区别不改变“最高模式频率不能代表计算覆盖”的原则。

已有checkpoint或scan_manifest而未选择继续时，应用准备阶段（创建Manager之前）及算法入口均拒绝从头运行；即使检查点丢失也不根据已有manifest静默重算覆盖。检查点丢失应恢复账本或新建目录，不凭结果频率猜空区间。需要重算请用新项目目录。继续加载原策略、工程身份/快照哈希、已有结果和待处理区间；失败缺口仍补算，不因后面有较远结果跳过。尚未完成的当前求解区间可能需重新求解，但绝不从扫描起点重放已确认区间；CST求解器内部进度续算未实现。

## 验收与TODO

离线验证启动/步骤钩子、后处理生成开关、停止发布不取任务锁、空窗口推进、求解中停止保留pending、缺口限制frontier、拒绝从头覆盖及既有恢复测试。宏字符串检查不是真实CST退出证明。

本批最终离线537 passed、19 integration deselected，包含文档与事件索引门禁。轻量报告artifacts/cooperative-stop-resume-20261014.xml不保证随Git迁移；本轮模型/pytest临时目录已清理，真实CST中断/保留/正常退出未执行。

TODO：串行副本实测启动、参数、重建后、Solver返回后、后处理条目、Backup/Ack停止；核对interrupted-project.cst及同名结果目录、StopAck、正常进程退出；GUI加载期间即时取消、保留求解后的仅后处理恢复自动化仍待做。不得删除活跃工作副本或原工程，不把离线测试宣称真实中断验收。
