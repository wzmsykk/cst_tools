# CST Python / VBA 现代跨语言 ABI 设计

状态：修订提案，优先于旧 Runtime Protocol 中冲突的线格式示例  
日期：2026-09-16  
对应实现：`csttool.runtime_protocol`

## 1. 参考模型与取舍

本设计提取成熟跨语言 ABI/RPC 的共同原则，而不强迫 VBA 实现复杂技术栈：

| 成熟模型 | 采用的原则 | CST/VBA 中的实现 |
|---|---|---|
| C ABI / FFI | 边界窄、数据所有权明确 | VBA 只负责 CST 内状态变化；Python 拥有调度和结果模型 |
| Protobuf / gRPC | 版本化 Envelope、稳定字段、兼容演进 | `CST_TASK_V1`、`CST_COMPLETION_V1`、`CST_ACK_V1` |
| 消息队列 | 唯一消息 ID、原子发布、幂等消费 | UUID task ID、`.tmp` 原子替换、不可复用 attempt |
| Transactional Outbox | 数据完成后才发布状态 | 关闭并校验结果后才发布 Completion |
| 两阶段交接 | 生产完成与消费完成分离 | Completion 后等待 Ack，避免 Warm 结果覆盖 |
| Content-addressed artifact | 内容摘要绑定身份 | 规范化参数 SHA-256、结果 size/SHA-256 |
| Capability negotiation | 先声明能力再调用 | Profile + Build Manifest，不在任务中传函数名 |

不采用：VBA 内解析 JSON/Protobuf、每任务动态编译 VBA、通用远程对象、任意函数名调用、在消息中传绝对输出路径。

## 2. 两层 ABI

必须分离：

1. **Semantic ABI**：不可变 Task、Completion、Ack、ResultAsset、ErrorDisposition；
2. **Wire Codec**：v1 是 VBA 易实现的 UTF-8 行协议。

业务代码只依赖 Semantic ABI。将来改用 COM、命名管道或 sidecar，只替换 Codec/Transport，不改变 Manager、Provider、错误策略和任务身份。

## 3. 兼容规则

- 魔数中的主版本不认识时必须拒绝。
- 同一主版本中，必需字段缺失必须拒绝。
- 同一主版本允许忽略未知字段，应用扩展仅使用 `x-` 前缀。
- 已发布字段的含义、单位和默认值不得静默改变。
- 破坏性变化增加主版本；新增可选字段不增加主版本。
- 编码器输出确定性顺序；解码器不依赖字段顺序。
- 重复字段、重复参数名、重复结果 ID 一律拒绝。

## 4. 线格式修订

旧草案用重复的 `param.name` 键，成熟协议实现中容易产生歧义。v1 正式格式改为稳定索引：

```text
CST_TASK_V1
task_id=task-018f
worker_id=0
worker_instance_id=instance-a1
profile_id=wtc@1
project_scope=root
build_id=sha256:...
parameter_hash=sha256:...
attempt=1
parameter_count=2
param.0.name=Rx
param.0.kind=literal
param.0.value=90.0
param.1.name=L
param.1.kind=expression
param.1.value=2%20%2A%20Rx
```

所有字符串按 UTF-8 percent-encoding。换行只分隔记录，值中的空格、`=`、非 ASCII 字符不会破坏结构。

Completion 的结果也使用索引：

```text
CST_COMPLETION_V1
task_id=task-018f
worker_id=0
worker_instance_id=instance-a1
parameter_hash=sha256:...
status=success
phase=publish
retryable=false
restart_worker=false
result_count=1
result.0.id=frequency
result.0.provider=native
result.0.relative_path=run/Result/Frequency.rd0
result.0.codec=rd0-scalar-v1
result.0.unit=MHz
result.0.size=8
result.0.sha256=sha256:...
```

## 5. 参数 ABI

运行时参数只有：

- `name`：必须存在于指定 ProjectScope；
- `kind=literal|expression`：明确写入意图；
- `value`：写入 CST 的内容。

不传 `fixed`，因为它是旧优化配置推断而不是 CST 参数语义。不传 `evaluated_value`，因为它是 Rebuild 后的观测结果。规范化参数哈希覆盖 scope，以及按名称排序后的 name/kind/value，所以 Python 字典顺序不会改变任务身份。

## 6. 结果 ABI

Completion 返回的是 ResultAsset Manifest，而不是无类型字典：

- 稳定 result ID；
- provider：`native`、`python-derived` 或 `runtime-vba`；
- 任务目录内相对路径；
- versioned Codec；
- 明确单位；
- 文件大小和 SHA-256。

Python 在 Ack 前验证身份、路径 containment、大小、摘要、Codec 和单位。缺文件或 `None` 不是成功结果。

## 7. 错误 ABI

错误对象同时表达事实和处置：

- `phase`：validate/apply/rebuild/solve/flush/extension/publish；
- `error_code`：稳定机器码；
- `error_message`：仅用于诊断；
- `retryable`：是否允许新的 attempt；
- `restart_worker`：是否必须产生新的 Worker 世代。

Python 绝不解析错误字符串决定重试。每次重试使用新 task ID，保留 parent task ID 和递增 attempt。

## 8. 已实现的功能安全网

`csttool.runtime_protocol` 已实现但尚未接入生产 Worker：

- frozen dataclass Task/Completion/Ack/ResultAsset；
- literal/expression 参数模型；
- 确定性、与参数顺序无关的 SHA-256；
- UTF-8 percent-encoded Task/Completion/Ack Codec；
- 必需字段、重复字段、ID、摘要和相对路径校验；
- `.tmp` 同目录原子发布且拒绝覆盖；
- Completion 与原 Task/Worker 世代绑定；
- 结果文件 containment、大小和 SHA-256 校验。

对应单元测试覆盖 round-trip、表达式转义、篡改检测、顺序无关哈希、失败约束、路径逃逸、Ack 和禁止覆盖。

## 9. 下一功能切片

按以下顺序实现，避免同时改 Python 和 VBA 多层：

1. VBA v1 decoder/encoder 与 percent-decoder，使用离线 golden vectors 测试；
2. Python `ProtocolWorkerAdapter`，但连接 fake Worker；
3. Worker ready/capability handshake 和 Worker 世代；
4. 最小 VBA Runtime：apply、Rebuild、Solve、Completion、Ack；
5. 一个 default 工程和一个 `.rd0` 标量的真实 CST Contract Test；
6. Warm/Cold 数值、时延和结果稳定性比较；
7. TM020/WTC Provider 迁移；
8. 只为无法替代的能力实现 Runtime VBA Extension；
9. 最后启用多 Worker 和有界重试。

在第 5 步通过前，不替换现有生产 Worker；旧协议作为明确的 legacy backend 保留。新旧协议不能混用同一 Worker 目录。

## 10. 验收条件

- Python/VBA 使用同一组 golden vectors，逐字节得到相同消息和参数哈希。
- 任意半文件、重复字段、错误哈希、旧 Worker 世代和路径逃逸均被拒绝。
- Completion 发布前所有结果已关闭且摘要可验证。
- Worker 未收到匹配 Ack 时不进入下一任务。
- 新增 native result 不修改 Task Protocol 或 VBA Runtime。
- 修改 Extension 内部算法且契约不变时不修改 Python Manager。
