# 诊断日志事件索引

同一次执行按 `context.run_id` 筛选，再按 `context.worker`、`context.task` 或 `context.job` 缩小范围。`source.file/line/function` 是业务日志调用位置；`error.traceback` 是异常发生路径。用 `event` 搜索下表中的模块，定位相应实现。旧日志结合 `code.revision` 定位；`code.dirty=true` 表示包含未提交代码，单凭提交号不能完全复现。

| 事件 | 实现模块 |
| --- | --- |
| `RUN_INITIALIZE` | `csttool/application_backend.py` |
| `RUN_PREPARE` | `csttool/application_backend.py` |
| `RUN_PREPARED` | `csttool/application_backend.py` |
| `MESH_CONVERGENCE_START` | `csttool/application_backend.py` |
| `MESH_CONVERGENCE_RESULT` | `csttool/application_backend.py` |
| `MESH_CONVERGENCE_POINT` | `csttool/application_backend.py` |
| `RUN_EXECUTE_START` | `csttool/application_backend.py` |
| `RUN_EXECUTE_DONE` | `csttool/application_backend.py` |
| `RUN_STOP_REQUESTED` | `csttool/application_backend.py` |
| `RECOVERY_START` | `csttool/application_backend.py` |
| `RECOVERY_REQUIRED` | `csttool/application_backend.py` |
| `PROJECT_LOCK_BUSY` | `csttool/application_backend.py` |
| `PROJECT_LOCK_ACQUIRED` | `csttool/application_backend.py` |
| `PROJECT_LOCK_RELEASED` | `csttool/application_backend.py` |
| `MANAGER_READY` | `csttool/cstmanager.py` |
| `WORKER_CREATED` | `csttool/cstmanager.py` |
| `TASK_QUEUED` | `csttool/cstmanager.py` |
| `WORKER_RESTART_START` | `csttool/cstmanager.py` |
| `WORKER_RESTART_CANCELLED` | `csttool/cstmanager.py` |
| `WORKER_RESTART_FAILED` | `csttool/cstmanager.py` |
| `WORKER_RESTART_DONE` | `csttool/cstmanager.py` |
| `TASK_START` | `csttool/cstmanager.py` |
| `TASK_DONE` | `csttool/cstmanager.py` |
| `TASK_ABANDONED` | `csttool/cstmanager.py` |
| `MANAGER_STOP_START` | `csttool/cstmanager.py` |
| `MANAGER_STOPPED` | `csttool/cstmanager.py` |
| `WORKER_TASK_DISPATCH` | `csttool/managed_cstworker.py` |
| `CST_COMPLETION_FAILED` | `csttool/managed_cstworker.py` |
| `CST_COMPLETION` | `csttool/managed_cstworker.py` |
| `RESULT_READ_DONE` | `csttool/managed_cstworker.py` |
| `RESULT_READ_FAILED` | `csttool/managed_cstworker.py` |
| `TASK_ACK_PUBLISHED` | `csttool/managed_cstworker.py` |
| `TASK_ACK_READY` | `csttool/managed_cstworker.py` |
| `TASK_ACK_FAILED` | `csttool/managed_cstworker.py` |
| `WORKER_TASK_COMPLETE` | `csttool/managed_cstworker.py` |
| `WORKER_ALREADY_EXITED` | `csttool/managed_cstworker.py` |
| `WORKER_STOP_REQUEST` | `csttool/managed_cstworker.py` |
| `WORKER_STOPPED` | `csttool/managed_cstworker.py` |
| `WORKER_STOP_FAILED` | `csttool/managed_cstworker.py` |
| `HOM_RESUMED` | `csttool/myAlgorithm_pop.py` |
| `HOM_CHECKPOINT` | `csttool/myAlgorithm_pop.py` |
| `HOM_INTERVAL` | `csttool/myAlgorithm_pop.py` |

