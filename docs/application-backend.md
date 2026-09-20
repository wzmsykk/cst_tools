# CST Application Backend

## 目的

`CstApplicationBackend` 是 GUI、CLI 与 CST 执行实现之间的应用边界。它负责一次运行的配置、工程准备、算法执行和 Manager 清理，但不负责 Qt、命令行参数解析或 CST Worker 的内部调度。

依赖方向固定为：

```text
GUI / CLI
  -> Application Service / compatibility facade
  -> CstApplicationBackend
  -> ProjectConfmanager / Algorithm / CSTManager
  -> Worker / VBA / CST
```

## 公共 API

| 操作 | 方法 | 允许状态 |
|---|---|---|
| 选择项目目录 | `select_project_directory(path)` | CREATED、STOPPED、FAILED |
| 选择 CST 文件 | `select_cst_file(path)` | CREATED、STOPPED、FAILED |
| 枚举 CST 安装 | `get_cst_installations()` | 任意状态（只读） |
| 读取/切换 CST 后端 | `get_selected_cst_installation()` / `select_cst_installation(version, executable)` | 切换仅允许可配置状态 |
| 读取/更新后处理设置 | `get_postprocess_settings()` / `update_postprocess_settings(values)` | 更新仅允许可配置状态 |
| 读取/更新算法设置 | `get_algorithm_settings()` / `update_algorithm_settings(values)` | 更新仅允许可配置状态 |
| 初始化环境与运行选项 | `initialize_run(start_from_existing, safe_mode, worker_count)` | CREATED、STOPPED、FAILED |
| 准备工程、Manager 和算法 | `prepare_run()` | INITIALIZED |
| 执行算法 | `execute_run()` | PREPARED |
| 请求标准停止 | `request_stop()` | Manager 存在时有效；没有 Manager 时幂等返回 |

## 生命周期

```text
CREATED -> INITIALIZED -> PREPARED -> RUNNING -> STOPPED
    ^                                      |
    |                                      v
    +---------------- FAILED <-------------+

RUNNING -> STOPPING -> STOPPED
```

- 初始化、准备或执行异常进入 `FAILED`；初始化可以从 `FAILED` 重试。
- 算法成功或失败都通过 `finally` 请求 Manager 标准停止并清除引用。
- GUI 的停止线程和执行线程可能同时进入清理路径，因此 Manager 停止由一次性栅栏保护。
- `STOPPED` 和 `FAILED` 可以重新选择输入并启动下一次运行。
- CST 后端在初始化前冻结；运行中不能切换。选择会写入全局配置，工程预处理、Manager 与 Worker 因而使用同一个可执行文件。
- HOM `scan_manifest.json` 记录 CST 版本和可执行文件路径；恢复时后端身份不同会被视为 Manifest 漂移，避免跨版本混跑。
- 本机生产后端默认使用 1 个 Worker，避免无意中启动多个 CST 实例；用户可根据本机资源和许可证显式调高 `worker_count`。运行开始后该值被冻结。

## 异常恢复

恢复按以下顺序收口：

1. 扫描项目 `temp/worker_*/<session>`，读取协议状态、Worker 标记和 PID 存活状态；
2. 对仍存活的会话只走协议恢复：发送 Stop Request、保存已有 Completion、补 ACK、等待 StopAck，并等待 CST 进程退出；
3. 进程存活检查覆盖 CST 启动器及其后代进程；仅当整棵进程树都已明确死亡时，才将隔离的 Worker 工程标为 `abandoned-dead`，后续从最后一个原子 HOM checkpoint 重算该区间；
4. 每个已收口会话写入不可变语义的 `recovery.json`，记录标准退出或死亡放弃、任务 ID 和 Completion 状态；
5. 只有所有会话都完成收口，项目状态才持久化为 `INTERRUPTED`，允许再次准备和从 checkpoint 继续。

每个 Managed Worker 任务只有在 Completion 成功、`project.cst` 快照存在且后处理结果可读后，才把该快照返回给 Manager。Manager 将其记录为“最后确认快照”：Worker 轮换时优先从该快照建立工作副本；HOM checkpoint 同时保存相对路径、文件大小和 SHA-256。继续扫描时先校验快照未丢失、未变化，再用它重建整个 Worker 池。正在求解但没有得到 Python 确认的工程副本永远不会提升为恢复点；旧 schema 2 checkpoint 没有快照信息时仍可读取，但会明确回退到原始工程。

快照接力是 `SimulationTask.continue_from_snapshot` 的显式能力，默认关闭。标准优化/参数扫描的批量任务相互独立，Worker 轮换始终从配置的基础工程启动，不会继承前一个参数点；只有顺序相关的 HOM 窄窗口任务开启该标志，并且自动轮换只能使用同一 Worker 槽自己的确认快照，不能跨并发 Worker 借用状态。

存活但无响应、PID 无法确认、协议身份不匹配或 CST 在 StopAck 后仍未退出，均保持 `RECOVERY_REQUIRED`。普通恢复不会调用进程强杀；`emergency_terminate()` 仍是明确的最后手段。

真实故障注入曾证明只结束启动器 PID 会遗留 `CST DESIGN ENVIRONMENT_AMD64.exe`。因此显式紧急终止在 Windows 上必须针对已记录 PID 的整棵进程树；父 PID 消失但子进程仍在时不得写入 `abandoned-dead`。

## 错误类型

- `BackendLifecycleError`：调用顺序错误或资源状态冲突；
- `BackendInitializationError`：CST 环境检查或全局配置初始化失败；
- `BackendPreparationError`：工程、Manager 或算法准备失败；
- 算法和 Manager 的运行时异常保留原异常，同时执行标准清理。

## 兼容边界

历史类 `base.cst_tools_main` 仅负责：

- 旧 camelCase 方法名到新 API 的转换；
- 旧的 `False`/`0` 失败返回值；
- 命令行参数解析和进程退出码。

新代码不得导入 `cst_tools_main`，也不得在 `CstApplicationBackend` 中重新加入 CLI、Qt 或旧方法名。GUI 对旧式测试替身的兼容集中在 `_LegacyBackendAdapter`，不属于生产默认路径。

## 当前边界

P9 只现代化应用编排和生命周期，不改变 `CSTManager`、`myAlgorithm_pop`、`local_cstworker` 或 `worker.vb`。Profile/Warm 执行策略应作为后续生产候选路径接入，并先通过真实 CST Gate，再讨论替换默认 Manager。
