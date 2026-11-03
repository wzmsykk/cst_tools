# CSTManager 现行设计

2026-11-03静态核对。完整旧设计见[归档](archive/20261103-semantic-review/cstmanager-design.md)，其中runWithParam、相同worker ID重建、未迁Managed等已不是实现合同。接口参数和示例以[API](cstmanager-api.md)为准。

## 职责与执行链

Manager维护有界Worker槽位、内存任务/结果队列、ThreadPoolExecutor和任务序号。算法提供SimulationTask，经worker_factory构造的对象以run_task(result_name, params=...)执行；生产工厂为ManagedCSTWorker.create。Manager不生成优化目标，不把内部内存队列当远程/持久队列。

每批在状态锁内从IDLE转RUNNING，为存活槽submit消费循环；同一槽串行领取，多个槽并发，完成后按序号排序。run_batch是阻塞调用。外部停止、资源准入失败或ACK待定可能停止派发，因此中断批次不保证每个原任务都返回一行。

SimulationTask是frozen数据类，但params的Mapping本身不深冻结；调用方负责不在运行中变更。WorkerConfig/SimulationResult形成边界，Worker内部协议、结果解析和原生关闭归Managed负责。依赖注入只提供测试能力，不证明注入对象满足真实CST生命周期。

## 身份、回收与恢复

Worker槽位保留确认快照和成功计数，实际worker ID每次重建重新分配、目录不复用。失败后默认使用配置基准工程；成功HOM快照接力显式开启且不跨槽。达到成功任务阈值后轮换；构造器阈值默认6，GUI/应用并发默认1与Manager构造器maxTask默认2分开。

重建先DRAINING并核验原Worker停止，再RESTARTING；停止失败不能继续创建重叠实例。只有明确开启的HOM非标准失败退役满足严格证据才可继续；结果仍Failure。已完成但ACK待定时先持久对账，不作为普通失败盲重试。

任务接收、ACK、算法采用和原生关闭是不同事实。RunStore及receipt持久关联，adopt_result在算法确认后写采用屏障；检查点对账只补元数据，不运行Solver。恢复依据模型身份/hash和检查点，而非“最后找到频率”或进程名。

## 状态与资源所有权

Manager：IDLE→RUNNING；协作停止进入STOP_REQUESTED；完整关闭进入STOPPING→CLOSED。槽位：ALIVE→DRAINING→RESTARTING→ALIVE，异常可DEAD。stop对全部槽独立尝试并汇总失败，再关闭线程池；内部CLOSED不等于所有原生进程标准退出。

request_stop不抢占阻塞Solver；Managed正常求解无固定总超时，启动/通信/退出有界。普通清理不强杀，未知身份保留恢复门禁。ApplicationBackend清理栅栏、Runner/GUI退出各有独立职责，不能由Manager一个状态替代。

## 验收边界

假Worker证明队列、顺序、并发、异常和状态处理；真实CST及恢复证据按各验收批次，不由本设计推断。无公开单任务Future/抢占取消，也没有远程执行调度；动态入口/清理定位见project-map.json的R010–R014。
