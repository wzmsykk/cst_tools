# Managed Worker 确认状态契约

本契约保留现有文件协议及串行 Worker，不引入消息队列。它更新之前的“一秒等待停止请求”补丁，后者不再作为当前设计。

## 状态与责任

| 状态 | Python | VBA | 可否新求解 |
| --- | --- | --- | --- |
| READY | 可以提交任务 | 校验任务后执行 | 是 |
| EXECUTING | 观察、等待 Completion | 求解、后处理、Backup | 否 |
| COMPLETED | 校验并读取结果 | 保留任务、Completion、快照，等待 Ack | 否 |
| RECEIVED | 原子保存 received/<task_id>.json，再发布 Ack | 校验 Ack | 否 |
| ACK_ACCEPTED | 等待 ready | 原子保存 current.ack.<task_id>.accepted，再清理通信文件 | 否 |
| ACK_BLOCKED | 保存诊断、暂停 Manager，不自动重算 | 保留状态，继续接受停止请求，不重复解析坏 Ack | 否 |
| READY | 标记接收记录 acknowledged，返回结果 | 清理完成后发布 ready | 是 |
| CLOSING | 等待 Stop Ack 与进程退出 | 验证 Stop Request，Save→Stop Ack→Quit | 否 |

received 记录保存任务、会话、参数、接收结果、快照和接收状态；Python未能持久化时不发布 Ack。VBA接受回执使用现有Ack格式与身份校验，按 task_id 独立命名，不随 current 文件清理删除。三次删除不是事务，但回执已先保存；删除错误进入 ACK_BLOCKED，不能重新解释残留 current.task 为新任务。

## 中断与错误规则

- Open 的三次有限重试只处理低层打开故障，总等待约0.2秒；不是状态转移或根因修复。格式、身份或读操作错误不重试。
- 重复发布相同任务/会话的 Ack 是幂等操作；发现已有不同身份或畸形Ack，立即拒绝而不覆盖。恢复入口也校验已存在Ack。
- Ack或清理失败不自行 Save/Quit，也不再十分钟超时退出；进入阻塞状态，等待独立停止请求。这不是无界重试，坏Ack不在等待循环中被反复打开。
- Python以 ManagedAcknowledgmentPending 报告确认未闭合；Manager请求暂停，抑制该任务自动重试和Worker重建重算。HOM检查点仍只含此前确认模式。
- 阻塞后停止保留协议残留、接收记录和快照。Save/Quit错误由独立处理器记录，不回到求解，不覆盖已有Completion。
- 结果接收记录 acknowledged 不代表 HOM 检查点已经接纳。控制器阶段2现提供显式会话恢复后的结果核对：匹配工程/后处理/CST后端指纹及参数，校验快照摘要，随后通过原有HOM指标校验；检查点保存后才标记 algorithm_adopted。旧记录缺少指纹时不自动接纳。详见 controller-plan-implementation.md。
- 已退出但缺停止确认与仍运行需要恢复是不同情况，不凭退出码0声称完整成功。

## 验证

测试覆盖Ack幂等及异身份拒绝、成功/失败接收记录、确认异常阻止Manager重试、VBA源码契约中的确认回执先于清理和阻塞状态不重入求解、Save→Stop Ack→Quit顺序。此轮普通测试344 passed / 19 deselected；真实WinWrap执行、进程中断及文件占用故障注入未执行。不得将源码契约检查当作CST端到端验收。
