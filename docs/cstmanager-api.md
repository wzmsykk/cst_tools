# CSTManager API 与使用指南

状态：当前生产调度接口。Manager 只接受显式 Worker 工厂，不再提供旧 Worker 回退或队列式兼容 API。

`CSTManager` 是优化算法与本地 CST 进程之间的批量任务调度器。它管理固定数量的 CST Worker，负责并发执行、失败重试、Worker 回收和结果汇总。

## 导入

新代码应使用正式类名和结构化任务：

```python
from csttool.cstmanager import CSTManager, SimulationTask
from csttool.managed_cstworker import ManagedCSTWorker
```

## 创建 Manager

```python
manager = CSTManager(
    gconfm=global_config_manager,
    pconfm=project_config_manager,
    params=project_parameters,
    logger=logger,
    maxTask=2,
    worker_factory=ManagedCSTWorker.create,
    max_jobs_per_worker=10,
)
```

构造参数：

| 参数 | 含义 |
|---|---|
| `gconfm` | 全局配置管理器，必须提供 `conf` |
| `pconfm` | 工程配置管理器，必须提供 `conf`、`currProjectDir` 和 `getCurrPPSList()` |
| `params` | CST 工程参数定义列表 |
| `logger` | 可选的标准 `logging.Logger` |
| `maxTask` | Worker 数量，也是最大并行任务数，默认为 2 |
| `worker_factory` | 必需的 Worker 工厂；生产后端使用 `ManagedCSTWorker.create` |
| `max_jobs_per_worker` | 单个 Worker 在强制重启前允许完成的任务数，默认为 10 |

`maxTask` 和 `max_jobs_per_worker` 必须至少为 1。

创建 Manager 会立即通过显式工厂创建相应数量的 Worker。

## SimulationTask

```python
task = SimulationTask(
    params={"radius": 100.0, "length": 250.0},
    job_name="GEN_0_1",
    retry_count=1,
)
```

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `params` | `Mapping[str, Any]` | 本次仿真的参数名和值 |
| `job_name` | `str` | 非空任务名称，也用于结果目录与结果关联 |
| `retry_count` | `int` | 失败后的额外重试次数，默认为 0 |

任务对象不可变。`retry_count=1` 表示最多执行两次。

## 推荐用法

### 批量执行

```python
tasks = [
    SimulationTask({"radius": 90.0}, "GEN_0_1"),
    SimulationTask({"radius": 95.0}, "GEN_0_2"),
    SimulationTask({"radius": 100.0}, "GEN_0_3", retry_count=1),
]

with CSTManager(
    gconfm, pconfm, params,
    maxTask=2,
    worker_factory=ManagedCSTWorker.create,
) as manager:
    results = manager.run_batch(tasks)
```

`run_batch()` 会：

1. 将所有任务加入队列；
2. 使用 Worker 池并发执行；
3. 阻塞到本批任务结束；
4. 按提交顺序返回结果。

任务完成顺序可以不同，但返回列表顺序是确定的。

### 执行单个任务

```python
with CSTManager(
    gconfm, pconfm, params,
    worker_factory=ManagedCSTWorker.create,
) as manager:
    result = manager.execute(
        SimulationTask(
            params={"radius": 100.0},
            job_name="single-run",
            retry_count=1,
        )
    )
```

### 显式关闭

```python
manager = CSTManager(
    gconfm, pconfm, params,
    worker_factory=ManagedCSTWorker.create,
)
try:
    results = manager.run_batch(tasks)
finally:
    manager.stop()
```

优先使用 `with`。`stop()` 可以重复调用，第二次调用不会重复关闭资源。

## 结果格式

Manager 保留 Worker 返回的字典，不改变成功结果内容。当前 CST Worker 的典型成功结果为：

```python
{
    "WorkerID": "0",
    "TaskIndex": 1,
    "TaskStatus": "Success",
    "RunName": "GEN_0_1",
    "RunParameters": {"radius": 100.0},
    "PostProcessResult": [...],
}
```

典型失败结果为：

```python
{
    "TaskStatus": "Failure",
    "FailureReport": "CST Env Stopped.",
    "RunName": "GEN_0_1",
    "RunParameters": {"radius": 100.0},
    "PostProcessResult": None,
}
```

如果 Worker 抛出 Python 异常，Manager 会将其转换成同类失败字典，其中 `FailureReport` 包含异常类型和消息。

调用方至少应检查：

```python
if result["TaskStatus"] == "Success":
    consume(result["PostProcessResult"])
else:
    report_failure(result.get("FailureReport", "unknown failure"))
```

## 重试和 Worker 回收

- 任务失败时，当前 Worker 会被关闭并原位重建。
- 如果仍有重试次数，任务会在新 Worker 上再次运行。
- 重试耗尽后，最终失败结果仍会返回给调用方。
- Worker 成功完成 `max_jobs_per_worker` 个任务后，会在领取下一个任务前重建，以减轻 CST 长时间运行造成的内存泄漏。

## 状态与异常

可通过 `manager.state` 读取状态：

```python
from csttool.cstmanager import ManagerState

assert manager.state is ManagerState.IDLE
```

状态包括：

- `IDLE`：可接收或执行任务；
- `RUNNING`：正在执行批次；
- `STOPPING`：正在释放资源；
- `CLOSED`：已经关闭，不能再提交任务。

配置无效、重复执行批次、关闭后提交任务或没有可用 Worker 时会抛出异常。CST 任务自身失败通常作为结果字典返回，而不是从 `run_batch()` 抛出。

## 测试

默认测试不启动 CST：

```powershell
python -m pytest
```

在已经正确配置 CST 的机器上运行集成测试：

```powershell
python -m pytest -m integration -o addopts=""
```

## 使用约束

- Manager 和 Worker 均为本地进程内对象，任务队列不会持久化。
- `run_batch()` 是阻塞式批处理接口，不是后台服务。
- 建议先完成一批任务，再提交下一批；不要依赖批次执行过程中追加任务的时序。
- Manager 层尚未提供单任务取消或独立超时；实际仿真超时目前由 CST Worker 控制。
- 默认测试使用假 Worker。发布前仍需在真实 CST 环境执行集成验收。
