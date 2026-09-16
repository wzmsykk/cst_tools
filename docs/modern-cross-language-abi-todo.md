# 现代跨语言 ABI 实施 TODO

设计依据：[CST Python / VBA 现代跨语言 ABI 设计](./modern-cross-language-abi-design.md)

## 已完成

- [x] Semantic ABI 与 Wire Codec 分层。
- [x] Python Task/Completion/Ack/ResultAsset 不可变模型。
- [x] literal/expression 参数语义。
- [x] 参数规范化 SHA-256。
- [x] UTF-8 percent-encoded v1 Codec。
- [x] 同目录临时文件原子发布并拒绝覆盖。
- [x] Completion 身份绑定。
- [x] ResultAsset 路径、大小和 SHA-256 校验。
- [x] Python 单元测试安全网。

## ABI 冻结前

- [ ] 冻结 v1 字段表、最大长度和允许字符。
- [ ] 冻结未知字段和 `x-` 扩展规则。
- [ ] 冻结错误码、phase 与 retry/restart 映射。
- [ ] 冻结 Worker ready/capability handshake。
- [ ] 生成 Python golden vectors。
- [ ] 用独立 VB parser 验证 golden vectors。

## Worker Adapter

- [ ] 实现独立 `ProtocolWorkerAdapter`，不改 Manager 公共 API。
- [ ] 以 task ID 建目录，job name 只作元数据。
- [ ] 实现 submit、poll completion、validate、ack。
- [ ] 实现 timeout、stop 和 Worker generation 更换。
- [ ] fake Worker 覆盖半文件、进程退出、重复完成和 ack 超时。

## VBA Runtime

- [ ] 实现严格行解析和 percent-decoding。
- [ ] 实现 Worker instance/capability ready 文件。
- [ ] 任务从 inbox 原子 claim 到 active。
- [ ] 分阶段 apply/rebuild/solve/flush/publish。
- [ ] 统一捕获 VBA/CST 错误并写 failure Completion。
- [ ] Completion 前关闭全部输出。
- [ ] 等待 Ack 后清理并继续。
- [ ] Operation 不得写任务级状态或推进任务。

## 真实 CST Gate

- [ ] default 单 Worker、单 `.rd0` 标量。
- [ ] literal 与 expression 各一个参数。
- [ ] 验证 Rebuild 后表达式求值。
- [ ] Warm/Cold 数值和时延对照。
- [ ] Solver 返回与结果可读之间的刷新策略。
- [ ] 强制退出、超时和恢复。
- [ ] 通过后再迁移 TM020/WTC。

## 旧协议缺陷修复

- [ ] 已存在 `.failure` 时必须立即返回 Failure。
- [ ] 修复成功结果 TaskIndex 加一偏移。
- [ ] 缺失原生结果不得返回成功 `None`。
- [ ] 同名 job 不得共享结果目录。
- [ ] legacy backend 与 v1 backend 使用完全隔离目录。
