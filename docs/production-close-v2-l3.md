# L3：生产宏状态、失败退役与v2收尾发布

后续L5真实验收与修订见[串行记录](close-v2-l5-acceptance.md)：活动工程Save后会变化，正常收尾新增独立.closed.cst快照；以下L3无真实验收为当时状态。

日期：2026-10-24。状态：生产生成链和Python配套已实现，离线/假对端验收；**没有启动真实CST或WinWrap编译运行**。新创建的Managed会话生成v2收尾宏；旧会话仍按原静态声明读取，不修改活跃工程/宏。Task/Completion/ACK/Stop wire仍为v1。源模板文件名中的v1指任务协议历史入口，不表示收尾仍v1。

本轮用户要求接入生产宏，故从L2的“只提供库、不启用新生成器”进入新会话生成v2；这不是发布到现场或追认L5已通过。不可热替换旧Runner、覆盖用户工程或依据本轮离线结果认定现场退出1安全。

## 1. 采集的事实

- 初始task_outcome=not-started，model_state=prepared；接收有效Task后记录activeTaskId，写参数即标dirty。
- Solver返回1与实际模式查询分别处理。`solverReturnedSuccess`只表示Start确实返回1，**不证明模式可用**；任务成功仍需模式查询、必需后处理、非空快照及后续Python接收门禁。
- 失败、取消、成功分别写入v2 task_outcome；失败Completion仍是v1 failure，不能将其ACK变成success。
- committed仅表示模型快照已形成，或收尾Save及文件非空检查已完成；不表示仿真有效、后处理齐全或HOM采用。
- 正向回执填最后完成阶段、固定快照路径、文件大小；CloseFailed填稳定错误码及最后完成阶段，保留原始Err.Number/Description。失败阶段不会假装完成。
- Python `collect_close_evidence`共用于正常stop和发现/恢复，读取v2实际task/model事实，即使退出码1被拒绝也不抹掉恢复保存声明；接收/采用仍由原received和扫描检查点判断，不由close.receipt决定。

## 2. 失败退役与ACK

VBA `CSTPMW_PublishFailure`标记workerRetiring。ACK流程仍先校验身份、写accepted凭据，再逐项清理任务/Completion/ACK；全部清理成功后才发布`retiring:<task_id>`，而不是READY。主循环处于retiring时只等待停止，不消费后续task。

成功清理则发布`ready:<task_id>`；启动无任务仍使用裸ready。Python `_wait_task_ack`要求当前任务的ready/retiring标记、匹配accepted凭据和三个临时协议文件均已清理，旧ready或只有accepted文件均不足。

Python `ManagedCSTWorker.retiring`阻止直接重复run_task；消费者必需结果读取失败或ACK异常也退役。Manager既有Failure分支会先标准drain，再按原重试/快照规则建新会话；不让新任务复用坏模型，不提升Failure的快照。

纯Python可选分析的incomplete不会撤销主求解成功；若分析接收记录本身无法持久化而抛AcknowledgmentPending，则保留结果、阻止复用，不用重算Solver修复记录。

## 3. 保护求解后的数据

- Start=0且任务已改参数：停止时恢复最后良好原表达式、删除新增任务参数、Rebuild、恢复快照、Save，仍保留失败Task状态。
- Start=1之后（包括模式查询异常/无模式的失败），以及已有可用模式后必需后处理、Backup、参数检查点写入失败：保守保留当前工作副本和结果，不为“清理状态”恢复旧参数或Rebuild。该保护不意味着接受求解为成功。
- 求解后安全点取消可额外Backup interrupted-project.cst，检查非空；不把未完成后处理的中断任务标成成功，也不推进覆盖。
- 成功任务的参数检查点继续捕获原表达式；失败后保存的工作副本/恢复副本不替代Manager最后确认成功快照。HOM最高已计算上界不变成连续确认前沿。

## 4. 实际CloseSession时序

1. 校验StopRequest；无请求的自主收尾用worker-failure来源，不伪造请求。
2. 只在确需恢复且无上述求解后保护时恢复参数→Rebuild→隔离恢复Backup，逐步记录last_completed_phase。
3. Save返回且工作文件非空；恢复路径仍写原recovery-saved凭据，保留退出4原有门禁。
4. 填写并实际调用`CSTC2_WriteCloseReceipt`原子发布v2正向回执。
5. **只有合法StopRequest且回执成功后**写StopAck，再返回批执行器。不调用Quit、不重复Save或重跑Solver。

恢复/重建/Backup/Save/凭据/回执发布失败走独立CloseFailed：尽力发布failed回执、记录原错误，无正向StopAck；已存在的正向回执不被失败帧覆盖。自己的恢复凭据文件句柄尽力关闭，失败不触发Solver或UI操作。

Python等候中的缺回执标记为close-receipt-pending：进程活着时在原STOP_TIMEOUT预算内等待，不提前判格式损坏；已退出但仍缺回执则阻断恢复，不能降级v1。真正损坏/串身份仍立即报错。

显式恢复校验已存在StopRequest身份；发现匹配的本会话进程已退出时可结束StopAck等待，随后仍用共同证据判定标准关闭/放弃/阻断。这不是补写StopAck或忽略退出码；进程状态变未知则阻断，避免等候已死对端不可能再发出的消息。

有效failed回执与损坏回执分开：前者进程已确认死亡、结果对账后可以显式abandoned-dead，绝不是标准关闭；后者保持阻断，保留原始文件。无请求自主收尾可以用匹配的正向v2回执＋产物＋实际退出0确认关闭，不要求事后伪造StopAck；v1仍要求StopAck。退出1不接受，退出4仍需原匹配恢复凭据。

## 5. 最后接收任务与待提交任务

`last_task_id`是执行端最后接收的任务，不是Python最后写出的task-context。停止可能发生在task-context落盘后、VBA读Task之前。

- 与当前context一致：正常校验。
- none＋not-started/unknown：只允许当前待提交任务没有accepted凭据；不制造其Completion或结果。
- 旧任务UUID：要求该UUID的本session accepted凭据匹配，且当前待提交任务尚无accepted凭据；禁止用旧帧掩盖已确认的后续任务。
- 无上述依据的不同ID仍拒绝；公开`read_close_receipt(expected_task_id=...)`的严格等值API不变。

因此标准关闭与“某个待提交任务未执行/仍待对账”可以并存，不将待提交窗口的Task当作已算频段。完整Runner/GUI结果采用传播仍属L4。

## 6. 实现、测试和待验收

- [生产模板](../data/runtime_managed_worker_v1_main.vb)：Main、CSTPMW_PublishFailure、CSTPMW_CloseSession、CSTPMW_CheckStop。
- [Worker](../csttool/managed_cstworker.py)：_build_macro、_wait_task_ack、retiring、run_task；新空间显式v2并拼接两个库，task-context保存期望版本。
- [证据层](../csttool/session_closure.py)：collect_close_evidence/read_stop_evidence，model/task实际事实及pending/declared-failed区别。
- [恢复](../csttool/project_session_recovery.py)：退出后再次核对，缺失/损坏v2不得写abandoned来绕过门禁。
- [L3专项](../test/production_close_v2_test.py)：真实Python Worker配显式假VBA对端；正常/求解失败/后处理失败、Save与回执故障、ACK身份和清理、未接收任务停止、旧任务凭据、生成生产宏、无请求关闭、未采用失败快照及原字段字节保持。

假对端只实现协议，不解释VBA、不算电磁场；源码契约检查只证明分支/顺序存在。实际FileLen大文件、Save无返回值的持久性、批执行器是否再次改写工程、真实场数据/表达式保持、Start返回1但无结果及退出1来源，均须L5副本验收，不能靠离线测试追认。

保留未执行的生产宏样本artifacts/close-v2-l3-production-20261024，含静态声明、Model.run、宏及SHA-256；它使用测试PPS配置且没有有效输入模型，不能用于实际仿真。并不代表编译/运行成功。

L4仍需完善完整Runner/GUI事实与诊断展示；L5仍需真实WinWrap编译和串行CST故障矩阵。未验收前不将本轮源码当作已在现场稳定工作的发布版。报告及生成宏在artifacts，不保证随Git迁移；pytest临时副本结束后清理、可再生成。

最终离线713 passed、21 integration deselected（142.87s），主窗口独立34 passed；最终假对端/恢复/文档专项22 passed（5.74s，含重叠）。报告artifacts/close-l3-{offline,window,focused}-20261024.xml。逐阶段错误是构造的失败帧及源码契约检查，不是CST真实恢复分支执行证据。

测试过程中假对端一次因缺少窗口配置属性失败（已补齐不运行窗口的夹具），另一次受限专项出现PermissionError，增加测试端原异常追踪；未确认权限策略或共享时序根因。提升权限专项及全量通过，不为绕过问题给生产加盲重试，也不声称平台偶发已消除。
