# 最小 Python / VBA 协议 TODO

设计依据：[最小 Python / VBA Runtime Protocol](./minimal-python-vba-protocol.md)

## P0：修复现有确定缺陷

- [x] 已存在 `.failure` 时立即返回 Failure。
- [x] 修复成功返回 TaskIndex 加一偏移。
- [x] `.rd0` 缺失时返回明确失败，不返回成功 `None`。
- [ ] 每个 Worker 使用独立结果目录。

## P1：最小协议

- [x] 定义 Task、Completion、Ack 三个 dataclass。
- [x] 实现键/值双行 Codec。
- [x] 实现 `.tmp -> final` 原子提交。
- [x] 增加 task UUID 和 Worker session UUID。
- [x] 保留 literal/expression 参数语义。
- [x] 只定义 `INVALID_TASK`、`REBUILD_FAILED`、`SOLVER_FAILED`、`RESULT_FLUSH_FAILED`、`INTERNAL_ERROR`。

## P2：fake Worker 安全网

- [x] 冻结 Task、成功/失败 Completion、Ack golden vectors。
- [x] 实现独立 VBA v1 Task decoder、Completion writer 和 Ack decoder。
- [x] VBA Codec 无 `Sub Main`，尚未接入生产 Worker。
- [x] 不读取 `.tmp`。
- [x] 拒绝错误 session。
- [x] Completion 必须匹配 task。
- [x] Ack 前不得读取下一任务。
- [x] failure 不进入结果读取。
- [ ] 超时后停止 Worker。

## P2.5：接入前 Gate

- [ ] 使用目标 CST 的 VBA/WWB 解释器执行 golden vectors，而不仅是静态检查。
- [ ] 把 VBA Codec 编译进一份独立测试宏，验证 ASCII 文件读写和 `Name temp As final`。
- [ ] 通过后再修改 `worker.vb`；失败时只修 Codec，不动 Worker 生命周期。

## P3：真实 CST 最小验证

- [ ] default 工程。
- [ ] 一个 literal 参数。
- [ ] 一个 expression 参数。
- [ ] 一次 Rebuild/Solve/Flush。
- [ ] 一个 `.rd0` 结果。
- [ ] Python 读取完成后 Ack。

## 明确不做

- [ ] 不做 Result Asset Manifest。
- [ ] 不做参数或结果 SHA-256。
- [ ] 不做动态 capability negotiation。
- [ ] 不做多 Transport 抽象。
- [ ] 不做通用 Operation/插件 ABI。
- [ ] 不做跨主机和断点恢复。

以上项目只有出现真实失败样例或明确需求后才能移入实施列表。
