# Python/VBA现行运行协议

2026-11-03按runtime_protocol.py、ManagedCSTWorker、生产VB模板及close_receipt.py核对。Task/Completion/ACK/Stop为v1，生产新会话收尾回执为v2；不是只有三种消息/五个阶段的初始切片。原始完整切片与延期项见[归档](archive/20261103-semantic-review/minimal-python-vba-protocol.md)，架构提案不能替代本页或codec。

## 字节与身份

任务采用CST_TASK_V1，完成CST_COMPLETION_V1，确认CST_ACK_V1；键和值分行，严格枚举/字段/数量/UUID和编码，由codec及[test/data/runtime_protocol_v1](../test/data/runtime_protocol_v1/task.txt)等golden定义，不按key=value架构示例解析。值中的CR/LF等非法文本拒绝；表达式与literal类型分别保留，不扁平化CST参数。

生产Managed会话串行使用protocol/current.task、current.completion、current.ack和任务级accepted凭据；FileProtocol类的inbox/completed/ack目录是低层契约工具路径，不把它说成生产current槽的文件布局。每个Worker独占session目录；任务/session匹配，原子发布与身份核验缺一不可。

## 任务、接收和采用

1. Python准备任务上下文和原子Task；VBA校验，采集本任务实际修改项的原表达式，在写入前记录撤销意图。
2. VBA参数→Rebuild→Solver→结果检查→必需后处理→快照→Completion。Start=1或退出0单独不足；失败Completion不等同空区间。
3. Python核对Completion/后处理/快照，先持久保存received及RunStore事件，再发布ACK。失败Completion或必需结果读取失败也可在保存失败记录后ACK；ACK是消费/清理授权，不是成功票据。
4. VBA写任务级accepted后清理current文件，发布ready:<task>或retiring:<task>；Python同时核对身份、accepted及清理事实。坏ACK阻断，不循环解释坏内容或重入求解。
5. 算法确认后写检查点及采用屏障；received/acknowledged不是algorithm_adopted。恢复对账只补已确认元数据，不为补标记重算Solver。

ACK待定触发ManagedAcknowledgmentPending并停止派发，保留结果/回执，不普通盲重试。任务成功但可选纯Python分析未完成仍有独立pending状态，不能复用为完整分析结果。

## 停止和关闭

StopRequest/StopAck绑定session。安全点检查不抢占阻塞Solver/Rebuild/单个后处理。合法停止或失败收尾按模型状态：仅必要时恢复本任务已尝试修改的表达式并删除新增参数；Solver已返回成功后保留结果，不为清理而Rebuild。

收尾依次恢复/保存、独立Backup、close.receipt v2，合法停止请求才发布StopAck，然后返回批执行器。生产CSTPMW_CloseSession不调用Quit关闭自己正在运行的宏页；Python另核对实际进程退出。正常快照token为worker-input.cst.closed.cst，恢复为worker-input.cst.recovered.cst；详见[回执v2](close-receipt-v2.md)。

任务、模型、进程和采用独立判断。退出0/严格恢复4可按证据确认标准关闭；退出1不能改判标准成功，HOM仅显式严格失败退役后新建基准Worker。未知/活跃身份、损坏回执或待采用成功结果继续阻断。旧空间按静态声明处理，不热替换活跃宏，不因缺v2声明/回执自动降级。

## API与等待

FileProtocol.submit(Task)、wait_completion(Task, timeout)、acknowledge(Completion)、request_stop(session_id)、read_stop_ack(session_id)是实际低层方法，不是历史submit()->task_id或wait(task_id)占位接口。生产Managed使用自己的current槽及无固定总时限完成等待；启动/ACK120秒，stop共享600秒。低层契约工具的显式timeout不定义生产总求解期限。

[任务级撤销](task-parameter-undo.md)、[ACK契约](managed-ack-state-contract.md)、[采用补写](checkpoint-adoption-l5.md)、[收尾证据](session-closure-l1.md)说明不同责任。源码/假对端和真实L5证据分别记录；本页不累加历史测试数字，也不把部分L5通过当全部指令级中断验收。
