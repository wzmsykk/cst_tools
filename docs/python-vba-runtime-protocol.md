# CST Python / VBA Runtime Protocol

状态：设计草案，作为下一阶段实现基线  
协议版本：`CST_TASK_V1` / `CST_COMPLETION_V1`  
日期：2026-09-16

## 1. 决策摘要

Python 与 VBA 不应形成覆盖所有能力的通用 RPC。两者之间只保留一个很窄的 **Warm CST Worker 控制协议**：Python 原子提交参数快照和求解请求；VBA 在已打开的 CST 工程中应用参数、Rebuild、求解并确保结果落盘；VBA 发布不可变完成记录；Python 按 `native -> python-derived -> runtime-vba` 解析结果；Python 完成读取后 acknowledge，Worker 才接受下一任务。

参数发现、`.cst` 静态信息读取、结果解析、优化算法和批量调度属于 Python。运行时 VBA 只负责必须处于 CST 进程内的状态变更和 API 调用。

## 2. 当前协议审计

当前实现以 `<index>.txt` 提交任务，以 `<index>.success/.failure` 表示完成，存在以下确定问题：

- Python 直接写最终文件；固定等待 `0.1 s` 不能避免 VBA 读到半文件。
- 递增 index 没有全局 task ID、Worker 世代、参数哈希和 attempt。
- 任务没有协议版本、字段完整性、参数数量和编码约束。
- job name 直接用作结果目录名，没有路径安全和唯一性规则。
- success 不含结果清单、单位、大小或摘要，不能证明结果属于本任务。
- 没有 acknowledge；下一轮 Warm 求解可能在 Python 读完前覆盖原生结果。
- 失败只覆盖 Rebuild；Solver、后处理、输出写入和 VBA 异常没有统一模型。
- 已存在 failure 的 Python 分支只记录日志，仍可能进入成功读取路径。
- 成功返回前先递增 taskIndex，对外编号存在一位偏移。
- `Direct_PPS_0D` 缺文件返回 `None`，可能被误当作成功。
- 多 Worker 共用顶层 resultDir，同名 job 和旧结果可能碰撞。

因此协议必须冻结“提交、完成、消费确认”三个边界，不能只给旧文本增加字段。

## 3. 职责边界

### Python

- 从指定 `ProjectScope` 读取 `.cst` 参数和工程能力；区分 `expr` 与 `evaluated_value`。
- 校验任务，生成 task ID，计算规范化参数哈希，原子提交。
- 管理 Worker、超时、取消、重试和重建。
- 验证 Completion Manifest，并按 Provider 读取结果。
- 校验结果身份、单位、完整性和数值，完成后写 acknowledge。

### VBA Worker Runtime

- 打开一次 prepared 工程并报告 ready。
- 严格校验一个已提交任务，应用参数、Rebuild、运行 Solver。
- 等待求解真正完成，执行所需的刷新或保存。
- 调用预编译的可选 Extension，关闭输出后发布 Completion。
- 等待匹配的 acknowledge，再处理下一任务。
- 在安全点响应停止请求。

### VBA Extension

只完成无法由原生结果或 Python 重建的 CST 内部 API 计算，只写声明输出，通过固定 ABI 返回结果。禁止改参数、Rebuild、启动 Solver、写任务级标志或退出 CST。

## 4. 不进入运行时协议

- 参数发现：读取 `.cst::Model/Parameters.json`。
- Profile、Result Template inventory：由 `cst_project` 层读取。
- `.rd0` 和稳定文本结果解析：由 Python Provider 完成。
- Pipeline/Operation 配置：启动前编译进 Build Manifest。
- 任意 VBA 源码：任务不得携带或执行新代码。

这样新增原生物理量通常只改 Profile/Provider，不改运行时协议。

## 5. Worker 隔离和身份

每个 Worker 使用独占目录：

```text
worker_<worker_id>/
  worker-manifest.txt
  ready.txt
  inbox/
  active/
  completed/
  ack/
  control/
  logs/
```

Worker 每次启动生成随机 `worker_instance_id`。Python 将它写入任务，重启后的 Worker 拒绝旧世代任务。任务目录只使用不可复用 UUID；显示用 job name 不参与路径拼接。

## 6. Task Envelope

控制信封使用 UTF-8、逐行 `key=value`，不要求 VBA 解析 JSON：

```text
CST_TASK_V1
task_id=018f...
worker_id=0
worker_instance_id=...
profile_id=wtc@1
project_scope=root
build_id=sha256:...
parameter_hash=sha256:...
parameter_count=2
deadline_utc=2026-09-16T08:00:00Z
param.name=Rx
param.kind=literal
param.value=90.0
param.name=L
param.kind=expression
param.value=2*Rx
```

规则：

- `literal` 是字面量覆盖；`expression` 是有意写入 CST 表达式。
- 未列参数保持 prepared project 当前表达式；协议不传旧 `fixed` 字段。
- `parameter_hash` 覆盖 scope、规范化参数名、kind 和 value，且与输入顺序无关。
- v1 不提交 `evaluated_value`，它是 Rebuild 后的观测值。
- Python 必须校验名称来自工程参数清单、名称唯一、值非空和长度上限。

提交顺序是写 `inbox/<task_id>.task.tmp`、flush/close、原子 rename 为 `.task`。VBA 只观察 `.task`，再原子移动到 `active/` 取得所有权。

## 7. 生命周期

```text
Python: CREATED -> SUBMITTED -> ACCEPTED -> COMPLETED -> CONSUMED -> ACKED
VBA:    READY -> VALIDATING -> REBUILDING -> SOLVING -> FLUSHING
              -> EXTENDING -> PUBLISHING -> WAITING_ACK
```

一个 Worker 同时最多一个 active task，严格执行：

```text
apply -> rebuild -> solve -> wait complete -> flush/save
-> optional extensions -> close outputs -> publish completion
-> Python read/snapshot -> acknowledge -> next task
```

`Solver.Start` 返回不等于结果已可读。Profile 必须声明目标 CST 版本的完成检测和刷新策略。

## 8. Completion Manifest

成功和失败使用同一种文件，先写临时文件再原子发布：

```text
CST_COMPLETION_V1
task_id=018f...
worker_id=0
worker_instance_id=...
status=success
phase=publish
parameter_hash=sha256:...
rebuild_ok=true
solver_ok=true
result_count=1
result.id=frequency
result.provider=native
result.relative_path=run/Result/Frequency.rd0
result.codec=rd0-scalar-v1
result.unit=MHz
result.size=18
result.sha256=...
```

失败至少包含：

```text
status=failure
phase=rebuild
error_code=PARAMETER_REBUILD_FAILED
error_message=...
retryable=false
restart_worker=true
```

Completion 发布前必须关闭所有声明输出。Python 验证 task、Worker 世代、参数哈希、相对路径、大小、摘要和 Codec；任一不符均为 `PROTOCOL_ERROR`，不返回部分成功。

## 9. Provider 与结果所有权

结果按顺序解析：

1. `NativeResultProvider`：`.rd0`、稳定 ASCII/CSV 或已验证原生输出；
2. `PythonDerivedProvider`：单位换算、组合和派生计算；
3. `RuntimeVbaProvider`：必须调用 CST 内部场 API 的残余结果。

Completion 可登记原生资产位置，但 VBA 不必把每个原生值重抄为自定义文本。Profile 在启动前声明 Result Template 和结果树能力，缺失能力应尽早失败。

## 10. Acknowledge

Python 完成校验和快照后原子发布：

```text
CST_ACK_V1
task_id=018f...
worker_instance_id=...
parameter_hash=sha256:...
status=consumed
```

Worker 只有看到匹配 ack 才能继续。ack 超时时保持结果不变并报告 `WAITING_ACK`。Warm 目录中的原生结果可在 ack 后被覆盖，因此 Python 必须在 ack 前读完或快照。

## 11. 错误、重试和重建

| 类别 | 示例 | 自动重试 | 重建 Worker |
|---|---|---:|---:|
| 请求错误 | 参数不存在、表达式非法 | 否 | 否 |
| 模型错误 | Rebuild 失败 | 默认否 | Profile 决定 |
| 求解瞬态错误 | Solver 超时、许可证瞬断 | 有界 | 通常是 |
| 结果错误 | 结果树缺失、单位不符 | 默认否 | 视能力探测 |
| 协议错误 | 哈希不符、文件截断、世代不符 | 否 | 是 |
| 进程错误 | CST 退出、VBA 未处理异常 | 有界 | 是 |

Manager 只能重试同一不可变 `SimulationTask`。每个 attempt 使用新 task ID，并记录 `parent_task_id` 和 attempt；绝不复用旧完成文件。

## 12. 终止和取消

- `stop.request`：Worker 在安全点完成或失败后退出。
- `cancel/<task_id>.request`：只有 Profile 证明 Solver 可安全中断才支持；否则 Python 重建 Worker。
- 强制结束 CST 后当前任务统一为 `CST_PROCESS_EXITED`，不能推断结果有效。
- Worker 停止不重置或复用 task ID。

## 13. 编码、数值和安全

- UTF-8 无 BOM；读取兼容 CRLF/LF。
- 数字使用 invariant culture：`.` 小数点，无千位分隔。
- 时间使用 UTC ISO 8601。
- 只允许任务目录内相对路径；拒绝绝对路径和 `..`。
- job name 只作元数据。
- 任务不得携带 VBA、命令行、CST 方法名或任意输出路径。
- 错误消息中的换行和控制字符必须编码或写入独立日志。

## 14. 版本必须分离

- `generator_abi`：Python 编译器与 VB Operation 入口；
- `task_protocol`：运行中的任务控制；
- `operation_version`：某项 Extension 的输入输出语义；
- `result_codec`：结果文件解析语义；
- `profile_version`：工程准备状态和 CST 能力。

修改 Extension 内部算法而契约不变时，不修改 Python 调度层。

## 15. 迁移路线

1. 为旧协议建立已知缺陷回归样例。
2. 先实现 Python Task/Completion/Ack 模型、Codec 和原子文件操作。
3. 用 fake Worker 验证截断、崩溃、重复、超时、旧世代和同名 job。
4. 实现只含参数、Rebuild、Solver、Completion 的最小 VBA Runtime。
5. 用 default 工程完成单 Worker 纵向测试。
6. 接入一个 `.rd0` NativeResultProvider，验证 Warm/Cold 一致性。
7. 迁移 TM020、WTC，确定 residual VBA Extension 清单。
8. 再启用多 Worker、有界重试和取消。
9. 旧协议作为显式 legacy backend 保留至少一个发布周期。

## 16. 第一实现切片

只实现一个 Worker、一个 scope、literal/expression 参数、Eigenmode solve、一个 `.rd0` 标量、无 Runtime VBA postprocess、Task/Completion/Ack fake-worker 测试和 default 真实 CST Contract Test。先证明身份、时序和结果所有权，再决定 Operation ABI 的实际范围。
