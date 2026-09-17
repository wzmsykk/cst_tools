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
