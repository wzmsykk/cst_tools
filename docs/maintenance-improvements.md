# 排查与功能维护改进

## 本轮实现

- 保留 `.log` 人读与 `.jsonl` 机器分析两种输出；源码位置、异常栈、事件、运行上下文用于定位。
- 每个真实 Worker 会话保存 `diagnostics.json`：输入配置（不包含回调）、Python/VBA 源码 SHA256、Git 状态、worker/session 与产物路径。指纹用来比对实现，不是源码备份，也不保证外部 CST 环境可复现。
- Python Manager → Worker 使用 `WorkerConfig`；Worker → Manager 使用 `SimulationResult`。在算法结果边界序列化为字典；独立测试工具的旧字典输入通过显式适配器转换。CST 文件协议不变。
- 后处理指标的 CST 查询名、输出 token、GUI 名称及是否使用积分线统一定义于 `postprocess_metrics.py`；保留供应商查询拼写和 `_All` 原有语义。
- 补充运行中断、执行失败、安全停止失败事件。
- `python -m csttool.log_event_index` 从 AST 输出事件索引；测试检查文档与源码事件/模块集合一致。
- 算法源文件命名改为 `algorithm.py`、`hom_scan_algorithm.py`，更新生产和测试导入，不保留旧模块别名。
- 项目状态写入与参数读取直接使用 `ProjectSettings`，移除重复解析。

## 尚未完成的范围

- `ProjectConfigManager` 的工程创建、预处理及校验仍有 ConfigParser 中转，后续应只在 INI 读写边界进行转换。本轮不是完整 Config 内部重写。
- 诊断清单尚未包含完整安装版本、工程内容备份和每次动态任务输入归档；应结合现有协议文件、快照与日志分析，不能仅凭清单重现仿真。
- 真实 CST 的失败、恢复、无 UI 残留和安全退出仍需单独集成验收；普通 pytest 通过不代表上述验收通过。
- 历史设计文档可能保留旧文件名作为当时记录；当前实现位置以源码与事件索引为准。
- `utils` 保持不变。
