# CSTManager 设计文档

## 1. 目的

`CSTManager` 为需要反复调用 CST 的优化算法提供一个有边界、可恢复、可测试的本地并发执行层。

它解决的主要问题是：

- 一代优化种群包含多个可并行仿真的个体；
- 单个 CST 进程可能失败、退出或长期运行后占用过多资源；
- 每个 CST 实例必须使用隔离的工作目录；
- 算法需要稳定关联任务名称、参数和结果；
- 调度逻辑必须在没有 CST 的开发环境中接受单元测试。

## 2. 设计范围

Manager 负责：

- 固定大小 Worker 池；
- 内存任务队列；
- 批量并发执行；
- 失败重试与 Worker 重建；
- 结果排序和汇总；
- 生命周期与资源关闭。

Manager 不负责：

- 生成优化参数；
- 计算目标函数或选择下一代种群；
- 解析具体后处理物理量；
- 跨进程或跨主机调度；
- 持久化任务队列；
- 判断失败结果能否被业务接受。

这些职责分别属于优化算法、`local_cstworker`、后处理模块或未来的分布式执行层。

## 3. 组件

### 3.1 `SimulationTask`

不可变任务描述，包含参数、任务名称和重试次数。任务与执行线程、Worker 编号无关，因此可以安全放入共享队列。

### 3.2 `_QueuedTask`

为任务附加全局递增序号。该序号只用于恢复提交顺序，不暴露给 CST Worker。

### 3.3 `_WorkerSlot`

Worker 池中的固定槽位，保存：

- 稳定的 Worker ID；
- 当前 Worker 实例；
- 已成功完成的任务数；
- `ALIVE`、`RESTARTING` 或 `DEAD` 状态。

Worker 失败时替换槽位中的实例，而不是向列表不断追加新 Worker。这保证池容量始终有界。

### 3.4 `CSTManager`

持有配置、队列、槽位和线程池，并提供现代批量 API 以及旧接口兼容层。

### 3.5 `WorkerProtocol` 与 Worker 工厂

调度器只依赖两个 Worker 操作：

```python
runWithParam(resultname, params=...)
stop()
```

默认工厂创建 `local_cstworker`。测试可以注入假 Worker，从而验证调度、重试和关闭行为，而不启动外部程序。

## 4. 数据流

```text
优化算法
   │  SimulationTask
   ▼
任务队列 Queue[_QueuedTask]
   │
   ├──────────────┐
   ▼              ▼
Worker Slot 0   Worker Slot 1      固定大小
   │              │
   ▼              ▼
CST Process 0   CST Process 1
   │              │
   └──────┬───────┘
          ▼
结果队列 Queue[(sequence, result)]
          │ 按 sequence 排序
          ▼
优化算法
```

## 5. 并发模型

Manager 使用一个最大线程数等于 Worker 数量的 `ThreadPoolExecutor`。

每次 `startProcessing()`：

1. 在状态锁内从 `IDLE` 转为 `RUNNING`；
2. 为每个存活槽位提交一个队列消费循环；
3. 每个循环通过 `get_nowait()` 原子领取任务；
4. 每个槽位同一时间最多执行一个任务；
5. 主调线程等待所有消费循环结束；
6. Manager 恢复为 `IDLE`。

不使用 `qsize()` 判断后再读取，因为二者之间存在竞争窗口。队列自身提供任务领取的同步保证。

`startProcessing()` 有意保持阻塞，与现有优化算法“提交一代、等待一代、处理结果”的流程一致。

## 6. 顺序保证

并发任务的实际完成顺序不确定。Manager 在任务入队时分配序号，并将 `(sequence, result)` 放入结果队列。

`getFullResults()` 在返回前按序号排序，因此：

- 任务可以并发执行；
- 调用方得到的结果仍与提交顺序一致；
- 算法也可以继续使用 `RunName` 做显式关联。

## 7. 生命周期

Manager 状态机：

```text
              startProcessing
       ┌────────────────────────┐
       │                        ▼
     IDLE ◄────────────────── RUNNING
       │       batch done
       │
       │ stop / context exit
       ▼
   STOPPING ─────────────────► CLOSED
```

规则：

- `IDLE` 可以提交和执行任务；
- `RUNNING` 不允许再次启动批次；
- `STOPPING` 和 `CLOSED` 拒绝新任务；
- `stop()` 幂等；
- 关闭后的 Manager 不可重新启动，应创建新实例。

Worker 槽位状态机：

```text
ALIVE ── failure/job limit ──► RESTARTING ── success ──► ALIVE
                                  │
                                  └── create failure ──► DEAD
```

## 8. 失败和重试

一次任务尝试可能：

- 返回 `TaskStatus == "Success"`；
- 返回 `TaskStatus == "Failure"`；
- 抛出 Python 异常。

Python 异常会被记录并转换成失败结果，使批量执行不会因为一个 Worker 异常而丢失任务结果。

失败后的处理顺序：

1. 记录失败和当前尝试次数；
2. 关闭当前 Worker；
3. 使用相同 Worker ID 和目录配置重新创建 Worker；
4. 如果还有重试次数，在新 Worker 上重新运行任务；
5. 重试耗尽则返回最终失败结果。

这里选择“失败后重建”而不是复用进程，因为 CST 失败可能意味着进程或内部工程状态已经不可相信。

## 9. 周期性 Worker 回收

每个槽位记录成功完成的任务数。达到 `max_jobs_per_worker` 后，在执行下一项任务之前重建 Worker。

这是一种针对外部 CST 进程长期运行内存增长的防御措施。计数只统计成功任务；失败会立即触发重建并重置计数。

## 10. 关闭策略

`stop()`：

1. 将 Manager 状态设为 `STOPPING`；
2. 使用独立的临时线程池并行调用所有 Worker 的 `stop()`；
3. 单个 Worker 停止失败只记录异常，不阻止其他 Worker 清理；
4. 关闭主线程池；
5. 清空任务队列和结果队列；
6. 清除槽位并转为 `CLOSED`。

上下文管理器把异常路径也纳入关闭流程：

```python
with CSTManager(...) as manager:
    manager.run_batch(tasks)
```

## 11. 兼容策略

当前算法仍使用历史队列接口，因此重构采用“新内核、旧外壳”策略：

- 正式类名为 `CSTManager`，保留 `manager` 别名；
- 推荐 `SimulationTask`、`run_batch()` 和 `execute()`；
- 保留 `addTask()`、`startProcessing()` 和结果读取接口；
- 对已知旧三参数 `addTask` 形式进行兼容，但发出弃用警告；
- `synchronize()` 暂时保留为兼容操作。

待所有算法迁移到新 API 后，可以在一个主版本升级中删除弃用接口。

## 12. 可测试性

Worker 工厂是显式依赖注入点。并发单元测试使用假 Worker 验证：

- 最大并行度；
- 提交顺序；
- 失败后重建和重试；
- 周期性回收；
- 结果读取；
- 关闭和非法状态。

真实 CST 测试使用 `integration` 标记，不进入默认测试套件。

## 13. 当前限制与后续方向

当前限制：

- 仅支持单 Python 进程内的本地线程调度；
- 任务和结果只保存在内存；
- 没有公开的单任务取消或 Future API；
- 没有 Manager 级任务超时，依赖 Worker 自身超时；
- 批次执行是阻塞式；
- 真实 CST 关闭速度受外部进程响应时间影响；
- 默认测试不能代替真实 CST 集成验收。

建议的后续演进顺序：

1. 将所有算法迁移到 `SimulationTask` 和 `run_batch()`；
2. 为成功和失败结果建立正式数据类，逐步替代字典；
3. 为 Worker 增加明确的启动、健康检查、超时和强制终止协议；
4. 增加任务取消与进度事件；
5. 如确有跨机器需求，再引入持久化队列或分布式执行后端。
