# L1：统一会话关闭证据核验

日期：2026-10-24。对应[生命周期协议L1–L5](python-vba-lifecycle-protocol-v2-plan.md)。本轮实现L1，Task/Completion/Ack/Stop v1与VBA宏不变；L2–L5仍待做，不接受退出1、不启用close.receipt v2。

后续同日L2增补：[v2 codec/静态门禁](close-receipt-v2.md)已实施并接入声明v2目录的附加阻断；上段是L1完成时范围。生产宏仍v1，L3–L5继续pending，不把v2回执代替退出4旧凭据。

## 已实现

- `session_closure.CloseEvidence`、`ClosureAssessment`和`evaluate_closure`是无副作用的判定内核，正常停止与会话发现/显式恢复共用。分别输出进程状态、退出码分类、模型恢复保存声明、任务/接收状态及缺失证据。L1没有从日志反推任务成功；尚无可核验来源时相应维度保持unknown。模型restored-saved指既有v1恢复凭据与非空快照，未增加CST结构/表达式重读验收。
- 标准关闭仍要求有效本session StopAck、已确认进程树退出及原始退出码0；退出4额外要求匹配恢复凭据/非空恢复快照。退出1、其他非零和未知退出码均不作为标准关闭。
- 会话发现不再按stopped标记或StopAck文件存在就排除：解析并验证回执身份，活跃/未知进程始终保留恢复要求。协议目录存在而worker.state缺失也被发现，覆盖启动中断。
- 进程观测为True/False/None。访问拒绝、缺PID、进程快照失败均不能变成False。Windows父进程结束仍检查可枚举的后代；修正快照句柄类型，保留枚举异常为unknown。PID复用可能保守阻断，不据此操作其他实例；L1不是新的完整进程身份追踪服务，也不声称能追溯已脱离可枚举父链的任意后代。
- stop结束时写`close-verification.json`，保存Python实际观察的退出事实与StopAck等证据摘要，供重启后核对。它是Python观测记录，不是VBA收尾回执；匹配session/PID及证据摘要后才能重用退出码。原退出4恢复快照也计算摘要，其他正常停止不散列全部结果目录。
- 统一停止分支后取消WORKER_ALREADY_EXITED事件；已退出和等待后退出均经相同证据核验、成功统一记录WORKER_STOPPED。失败事件增加process_state/model_state/missing_evidence，不改变任务原结果。
- 显式恢复先对账Completion，再关闭/核验。正常协议等待和随后退出等待共用一个timeout_per_session总预算，不再各耗用一个完整预算。求解本身仍无固定总时限；本改动不改变已有运行中停止的安全点限制。
- 父控制器已丢失原始进程退出码时，StopAck＋已死只足以显式记为abandoned-dead，不能凭空补退出0。已确认结果与扫描检查点不清空，不提升恢复副本、不确认失败区间。未知进程不能如此放弃。

## 兼容、错误和恢复

1. 已部署旧宏继续使用v1；不更新活跃会话，不要求已有空间具备v2字段。
2. 历史关闭只有stopped/StopAck而无PID或可信退出记录时，将重新显示需要恢复。缺PID无法自动证明退出，应人工核实归属；不能删除标志或修改READY来绕过。
3. 历史标准恢复记录缺退出证据时可在进程确已死后显式降为abandoned-dead。保留旧`recovery.json`，补充`recovery-l1.json`；发现和结果查找优先补充记录。不会把“放弃副本”包装成标准关闭。
4. malformed/跨session StopAck与损坏Completion拒绝自动恢复，保留原文件。进程已死也不伪造匹配回执；需先检查原始诊断。回执存在本身不是身份凭证。
5. 正常stop拒绝时仍写退出观测/缺失项并记录WORKER_STOP_FAILED；模型恢复保存声明不会被退出码1抹掉，但不能据此解除标准关闭门禁。
6. 没有新增强杀、求解重放、结果删除或覆盖推进；独立CST不在控制范围。原参数表达式恢复逻辑本轮未改。

## 实现与测试入口

- [证据核验器](../csttool/session_closure.py)：evaluate_closure/read_stop_evidence/read_recorded_exit。
- [Worker](../csttool/managed_cstworker.py)：stop/_shutdown_assessment；保留退出4专门告警。
- [发现与恢复](../csttool/project_session_recovery.py)：ManagedSessionRecord.closure、needs_recovery、discover_managed_sessions、recover_project_sessions。
- [结果查找](../csttool/result_reconciliation.py)：find_received_result优先读取补充恢复处置，仍校验原任务结果快照，不采用恢复副本。
- [L1矩阵](../test/session_closure_test.py)：活跃/未知/已死×退出码0/1/4/未知、回执缺失/损坏/串session、历史记录保留、丢失标记、父退出/子存活或未知及正常stop/发现一致性。
- [恢复回归](../test/project_session_recovery_test.py)、[Worker回归](../test/managed_cstworker_test.py)、[退出4](../test/failed_rebuild_stop_test.py)、[ACK契约](../test/ack_shutdown_contract_test.py)。

## 剩余门禁

L2：close.receipt v2及版本门禁；L3：失败ACK后retiring、求解后结果保护；L4：任务/模型/接收全链字段采集与GUI诊断；L5：真实CST串行副本逐项验证（包括退出1来源）。尚未证明现场会话49ab9d3a安全关闭或其Start=0根因，也没有重写那份现场数据。

本轮提升权限离线639 passed、21 integration deselected（136.91s）；主窗口独立34 passed，分组673项。受限回归此前一次事件索引未同步失败、一次结果目录rename WinError5，均不计通过；索引同步后同套提升权限回归通过，不为绕过权限问题更改命名逻辑。报告artifacts/lifecycle-l1-{offline,window}-20261024.xml不保证随Git迁移，临时目录结束后清理、可再生成。无真实CST验收不能将L2–L5勾选完成。

最终证据/文档专项40 passed（1.38s），含补充共用期限测试；与上述分组有重叠、不重复加总。报告artifacts/lifecycle-l1-focused-20261024.xml。
