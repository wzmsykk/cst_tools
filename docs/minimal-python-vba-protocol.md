# 最小 Python / VBA Runtime Protocol

状态：推荐实施方案；取代“第一阶段完整 ABI”思路  
日期：2026-09-16

## 1. 只解决当前真实问题

当前协议真正必须解决的只有：

1. VBA 不能读取尚未写完的任务；
2. Python 必须知道完成信号属于哪个任务；
3. Completion 必须晚于 Solver 完成和结果刷新；
4. Python 读完 Warm 结果前，Worker 不能开始下一任务；
5. 失败不能被当成成功继续读取。

第一阶段不建设通用 RPC、通用 Result Manifest、插件系统、能力协商或多 Transport。协议只服务当前本机、单 CST 进程、单 Worker 串行任务。

## 2. 最小消息

每个 Worker 使用独立目录，并在启动时生成一个 `session_id`。只定义三种消息。

### Task

```text
CST_TASK_V1
task_id
8f30...
session_id
3b17...
parameter_count
2
param.0.name
Rx
param.0.kind
literal
param.0.value
90.0
param.1.name
L
param.1.kind
expression
param.1.value
2*Rx
```

采用“键一行、值一行”，避免实现 percent-decoder；v1 禁止名称和值包含 CR/LF。Task 先写 `.tmp`，关闭后原子改名为 `.task`。

### Completion

```text
CST_COMPLETION_V1
task_id
8f30...
session_id
3b17...
status
success
```

失败时增加：

```text
error_code
REBUILD_FAILED
error_message
...
```

Completion 不列举每个结果。结果位置、Codec 和单位仍由现有 PPS/Profile 配置决定；Python 在读取时负责检查存在性和格式。

### Ack

```text
CST_ACK_V1
task_id
8f30...
session_id
3b17...
```

Worker 看到匹配 Ack 后才处理下一 Task。

## 3. 保留与延期

### 现在保留

- `task_id`：防止旧 flag 和同名任务混淆；
- `session_id`：防止 Worker 重启后消费旧任务；
- `literal/expression`：这是 CST 参数的真实语义差异；
- `.tmp -> final` 原子发布；
- Completion/Ack 顺序；
- 少量稳定错误码；
- 单 Worker 独占目录。

### 延期到有证据需要时

- 参数 SHA-256：UUID、独占目录和不可复用文件已足够；
- 每个结果的 SHA-256、size 和资产清单；
- `build_id`、Profile ID 每任务重复传输；
- deadline、attempt、parent task 写入 VBA 协议；这些由 Python Manager 管理；
- `x-` 扩展字段和通用未知字段机制；
- 通用 Provider 协商；先沿用静态 PPS/Profile；
- COM、Named Pipe、sidecar 等多 Transport；
- 通用 Operation 插件 ABI；仅在确有残余 VBA 后处理时设计；
- 分布式、跨主机、断点恢复和 exactly-once。

## 4. 最小状态机

```text
Python: write task -> wait completion -> read results -> write ack
VBA:    wait task -> apply -> rebuild -> solve -> flush
        -> write completion -> wait ack -> next
```

只有五个 VBA 阶段：`apply`、`rebuild`、`solve`、`flush`、`publish`。错误只需报告失败阶段和错误码。

## 5. Python API

第一阶段只需要：

```python
submit(task) -> task_id
wait(task_id, timeout) -> Completion
acknowledge(task_id) -> None
```

不创建通用 Message Bus、Transport 抽象层或依赖注入框架。文件操作可以放在一个 `FileProtocol` 类中；确认出现第二种 Transport 后再抽象接口。

## 6. 结果读取

暂不让 VBA 枚举结果。Python 根据当前 Project Profile 获取期望结果：

```text
Completion success
-> NativeResultProvider 读取已知 .rd0
-> PythonDerivedProvider 计算可派生值
-> 必要时读取固定 VBA Extension 输出
-> 全部成功后 Ack
```

任何必需结果缺失或解析失败，Python 不发送成功 Ack，而是把任务判为结果失败并重建或停止 Worker。首版可以停止 Worker，不必设计复杂恢复。

## 7. 实施切片

1. 修复旧 Worker 的 failure 分支和 TaskIndex 偏移。
2. 实现最小 Task/Completion/Ack Codec 与原子文件操作。
3. 使用 fake Worker 测半文件、旧 session、failure、Ack 前不得推进。
4. 用 default 工程运行一个 literal 参数、一个 expression 参数和一个 `.rd0` 结果。
5. 通过后再决定是否迁移 TM020/WTC。

完成第 4 步之前，不开发 Result Manifest、Operation Manifest 或通用 Extension ABI。

## 8. 增量触发条件

只有满足以下条件才扩展协议：

- 实际发生过结果目录污染，才增加结果摘要；
- 同一 Worker 必须支持多个动态 Profile，才增加 capability handshake；
- 确认存在无法直读的后处理，才实现 Extension ABI；
- 出现第二种传输方式，才抽象 Transport；
- 需要跨进程恢复，才增加持久化 attempt/parent task。

每项扩展必须附带失败样例或真实需求，禁止为假设场景预留框架。
