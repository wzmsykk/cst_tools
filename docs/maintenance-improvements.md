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

## 后续补全

- 工程创建、预处理、修复与校验使用 `ProjectSettings`；只有 INI 加载/保存及公开 `conf` 序列化视图转换 ConfigParser。缺失配置/模型文件直接报告校验失败，不再继续计算摘要；未知任务状态明确拒绝。
- 每个会话保留 `source-input.cst` 原始输入副本，诊断清单记录其位置和大小；此副本不能代替外部场数据、依赖文件或完整结果目录。
- 记录可执行文件路径、路径推断年份、Windows 文件版本和产品版本。读取失败记录错误或空值，不把路径推断年份冒充真实文件版本。
- 每次任务发送前保存 `tasks/<task_id>/input.task` 和 `context.json`。归档内容与发送内容一致，保留表达式种类、任务/会话 ID 和任务名称；归档失败不发送，不覆盖同 ID 的归档。归档不改变 Completion → read/snapshot → Ack → next task 顺序。
- 输入和归档按 worker 会话隔离，供 AI 从日志中的会话/任务 ID 定位。副本和诊断文件占用磁盘且可能包含工程敏感内容；不自动删除，不上传外部。

## 验收边界和剩余范围

### 2026-09-30 集成失败修复与复核

- 最新分项真实复核：Worker 重复任务及标准退出 1 passed（262.05 秒，`integration-worker-event-check.xml`）；工程预处理及源工程保护 1 passed（20.51 秒，`integration-preprocess-event-check.xml`）。分项通过不代表整组 17 项通过，亦不证明间歇性启动崩溃已消除。

- 后续修复 Windows 事件采集：显式 UTF-8、稳定 `windows_events` 对象（status/events/error），无匹配事件返回成功空列表；进程失败保留退出码及 stdout/stderr 尾部，不再只保存 `CalledProcessError` 字符串。现场查询已成功读取 CST/QtitanBase1 崩溃记录；普通回归 265 passed。
- 最近一轮真实测试仍为 17 failed（59.44 秒），其中 16 项退出码 `0xc0000005`，契约测试控制器退出码 1；不存在恢复稳定运行的证据。本次修复限于可确定的采集缺陷，不修改 CST 安装、图形驱动、注册表或全局配置，不引入自动重试掩盖崩溃。

- 启动、Completion 等待及 Ack 失败会保存 `failures/<随机ID>.json`，记录 UTC 时间、阶段、worker/session/task 上下文、PID、十进制/十六进制退出码，协议状态文件和 CST 日志最后 8 KiB 及大小/修改时间；不覆盖此前报告。
- 非零退出时只读查询最近 5 分钟最多 3 条 CST Application/1000 事件，查询限时 5 秒；记录为候选事件，不自动认定来自本进程。权限不足、无事件或超时记录采集错误，不遮盖业务异常。
- Completion 等待每 30 秒输出一次 `CST_WAIT_PROGRESS`，含耗时、日志大小和超时阈值；这是存活等待证据，不是求解成功或精确仿真进度。
- 诊断失败本身记录独立事件；资源关闭失败不替换启动原始异常。报告可能包含参数、工程路径和日志内容，仅本地保存，不自动上传。

- Mesh 集成夹具增加 `GlobalSettings`，与生产配置接口保持一致。
- 测试清理在构造失败、没有进程对象时直接返回，不再以 `None.poll()` 遮盖原始异常，也不在没有归属证据时清理其他 CST 会话。
- Worker 构造启动失败时关闭日志/进度监控，记录 `WORKER_START_FAILED` 和诊断路径，保留 PID/协议文件供显式恢复，不强制结束 CST。
- 普通回归：261 passed，17 deselected。
- 单独真实 Worker 复核：`managed_cstworker_integration_test.py`，1 passed，255.60 秒；验证重复任务和标准退出，报告位于仓库根目录 `integration-worker-fix-check.xml`。
- 先前整组隔离测试为 17 failed，报告 `integration-results-isolated.xml`。Windows Application 事件 1000 显示 CST 2022.5 在 `QtitanBase1.dll` 中发生 `0xc0000005`；此为故障模块证据，并未证明触发原因或已永久修复。
- 单项复核通过不替代整组、Mesh、HOM 十模式故障恢复验收；先前残留的会话未通过强制终止清理，仍需核实归属并按标准协议恢复。

- 安装依赖、许可证、外部工程依赖、网格/场数据和动态输出仍需结合现有协议文件、快照与日志分析，不能仅凭清单重现仿真。文件版本并非完整环境清单。
- 真实 CST 的失败、恢复、无 UI 残留和安全退出仍需单独集成验收；普通 pytest 通过不代表上述验收通过。
- 历史设计文档可能保留旧文件名作为当时记录；当前实现位置以源码与事件索引为准。
- `utils` 保持不变。
