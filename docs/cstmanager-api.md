# CSTManager API 与使用

2026-11-03按csttool/cstmanager.py核对。面向进程内调度调用者；生产GUI经Runner使用该层。旧接口和阶段验收保存在[复审前快照](archive/20261103-semantic-review/cstmanager-api.md)，不按历史样例调用runWithParam。

## 构造与配置

```python
from csttool.cstmanager import CSTManager, SimulationTask
from csttool.managed_cstworker import ManagedCSTWorker

with CSTManager(gconfm, pconfm, params,
                maxTask=1, worker_factory=ManagedCSTWorker.create,
                max_jobs_per_worker=6) as manager:
    results = manager.run_batch([
        SimulationTask({"radius": 90.0}, "R90"),
        SimulationTask({"radius": 95.0}, "R95"),
    ])
```

以上gconfm/pconfm须已完成配置和项目准备；不是用普通字典替换配置管理器的示例。

|参数|现行合同|
|---|---|
|gconfm|settings必须为GlobalSettings，需有效CST executable|
|pconfm|settings必须为ProjectSettings，提供currProjectDir及get_postprocess_settings，准备模型文件名必须存在|
|params|工程参数定义；不是本任务参数值|
|logger|可选标准Logger/ContextLogger；run_id不得与已有上下文冲突|
|maxTask|构造器默认2，至少1；GUI/应用默认1且可调，不混淆两层默认值|
|worker_factory|必需；生产默认注入ManagedCSTWorker.create，不隐式选择旧Worker|
|max_jobs_per_worker|默认6，至少1；成功任务达到阈值后下一次领取前轮换|
|run_id/run_directory/run_overview|关联RunStore、可读日志和任务观察；不能伪造另一运行身份|
|resource_budget/progress_callback/stop_check|资源准入、进度回调与协作停止；不构成抢占Solver能力|
|field_reference_result/field_match_policy/vacuum_domain|可选场分析；策略显式校验，vacuum_domain要求单Worker|

创建Manager会调用工厂创建Worker，可能启动CST；不是只读配置操作。

## 任务与结果

SimulationTask字段：params、非空job_name、retry_count=0、continue_from_snapshot=False、retire_failed_session=False。frozen只阻止字段重绑定，不深复制Mapping；调用方不能在排队/执行期间修改params。retry_count是额外尝试上限，不保证停止或ACK待定后仍会重跑。

- submit(task)返回递增队列序号；run_batch(tasks)阻塞处理并按提交序返回已完成结果；execute(task)要求至少有一个结果。
- 正常批次可并行完成但按序返回；停止会清除未派发任务，不为每个被取消任务编造成功结果。
- Worker可返回SimulationResult（会转mapping）或字典。调用方检查TaskStatus；成功不等于算法已采用，采用屏障由adopt_result/检查点处理。
- Python异常通常转Failure字典；但替换/关闭失败、协议或状态冲突可直接阻断批次，不能保证所有异常都只通过结果返回。

典型字段为TaskStatus、RunName、RunParameters、PostProcessResult；Managed还可提供TaskID、ReceiptPath、ProjectSnapshot及场/登记信息。字段缺失不能凭退出0补造物理结果。

## 重试、快照与停止

失败任务在标准关闭/严格可选退役核验后从配置的预处理基准新建Worker，不继承失败模型。HOM成功快照接力须continue_from_snapshot=True，只使用本槽确认快照；重建分配新的worker ID/目录，不复用旧会话身份。ACK待定的完成结果先对账，Manager设置停止，不自动重放已完成求解。

retire_failed_session仅显式开启：已死退出1、失败任务/恢复保存和v2回执、StopAck、accepted ACK及无待消费成功结果等须严格满足；记录非标准失败退役，绝不改判标准成功。详细条件见[HOM恢复](hom-solver-failure-recovery.md)。

request_stop设置STOP_REQUESTED、停止新派发并向Worker发布协作停止，不等待Solver立即返回。stop按独立清理线程处理全部槽、关闭线程池/清空队列；关闭失败会汇总抛错，即使Manager内部已CLOSED也不能宣称原生会话安全。上下文管理负责调用stop，串行重复stop幂等，不额外承诺任意并发调用安全。

Manager状态为IDLE、RUNNING、STOP_REQUESTED、STOPPING、CLOSED；槽状态为ALIVE、DRAINING、RESTARTING、DEAD。关闭后新任务被拒绝。正常求解无固定总超时；Managed启动/ACK就绪120秒，stop共享600秒预算，资源保护和进程死亡仍会中断等待。

## 验证入口

默认离线：`python -m pytest -q test/cstmanager_test.py test/managed_cstworker_test.py`。真实CST测试须明确选择integration、--run-cst和--cst-exe，见[测试指南](testing-guide.md)；本次仅静态文档核对，无新CST实测。Manager内存队列不是持久任务调度服务，Runner/RunStore/算法检查点另有持久事实。
