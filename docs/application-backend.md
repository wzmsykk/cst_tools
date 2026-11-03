# CST Application Backend

2026-11-03按csttool/application_backend.py核对；[复审前批次原文](archive/20261103-semantic-review/application-backend.md)保留旧恢复/日志/测试数字，不能作为现行合同。

## 调用位置

CstApplicationBackend负责HOM/标准算法的一次运行配置、预处理、Manager创建与清理。生产GUI使用RunnerBackend草稿和RunnerController客户端，经独立Runner的LocalExecution调用此后端；根base/base_WTC/base_tm020 CLI仍可直接调用。公共类型化定义和single-simulation由ApplicationService接入同一Runner槽，不强行描述为每项都先经过CstApplicationBackend。

GUI的CstApplicationService可用于显式进程内后端注入，不是生产GUI直接持有CST对象的依据。后端不解析Qt事件或命令行参数。

## API与生命周期

配置API包括select_project_directory、select_cst_file、安装选择、算法及后处理get/update。initialize_run(resume, worker_count)冻结设置，prepare_run准备工程/Manager/算法，execute_run运行。非法顺序抛BackendLifecycleError；初始化/准备失败分别使用BackendInitializationError/BackendPreparationError，原异常诊断保留。

BackendState包含CREATED、INITIALIZED、PREPARED、RUNNING、STOPPING、STOPPED、INTERRUPTED、FAILED、RECOVERY_REQUIRED；状态变化不等于原生会话事实。生产并发默认1、可调；运行后冻结。类型化GlobalSettings/ProjectSettings由配置加载器迁移旧INI，不在Manager回退旧conf字典。

request_stop首先持久化/设置StopIntent，即使Manager尚未创建也有效；之后在安全点阻止继续准备/派发。已有Manager通过其request_stop处理。阻塞CST调用不能即时抢占。_stop_manager_once负责一次运行的清理栅栏；部分构造、概览与日志资源失败由调用方补偿处理，关闭异常不能丢弃。

## 恢复与采用

恢复持项目运行锁，加载已有配置，核验会话身份/收尾与检查点，再补确认任务的receipt/RunStore采用标记，最后持久化INTERRUPTED。任一核验/写盘失败或暂停仍保持RECOVERY_REQUIRED。状态FAILED/confirmed-closed不能掩盖项目恢复门禁；缺配置不创建默认文件。

活跃/未知会话不根据进程名、PID或文件年龄放弃；核对PID+创建时间、路径及后代身份。已死但退出证据不足只能按明确条件记录abandoned-dead，不编造退出码。received、ACK、采用、模型保存和进程退出独立；恢复可重读已完成工件，不因元数据缺口重放Solver。

失败任务的新Worker从预处理基准工程启动，保留已确认结果/覆盖；不沿用失败恢复快照作为计算基准。成功HOM任务可显式接力同槽快照，标准独立参数任务默认不接力。checkpoint哈希/项目身份不放宽，已确认覆盖和计算探测上限分开。

resume从项目配置和scan_manifest恢复频率、初始窗口、并发和安装/mesh策略，GUI新建草稿不悄悄覆盖；目标上限变更按[HOM恢复策略](hom-solver-failure-recovery.md)及实现校验处理。恢复时不自动重跑前置收敛分析。

## 等待、日志与结果

Managed正常求解TASK_TIMEOUT=None；30秒等待记录为DEBUG，600秒心跳为INFO，阶段/原生进度另行采集，不把“每30秒刷INFO运行时长”当现行行为。START_TIMEOUT=120秒用于启动/ACK，STOP_TIMEOUT=600秒是同一会话多次stop共享的预算；取消发生在Solver阻塞中不提前消耗退出预算。

成功接收要求Completion身份、必需后处理和可用快照，不以退出0/Start=1单独判断。命名归档在ACK完成后处理，失败可保留原路径及警告；HOM检查点中的各路径按其定义基准解析。外部Q未配置导致该可选量缺失不自动判整个求解失败。

相关入口：[Runner](local-runner.md)、[Manager API](cstmanager-api.md)、[会话核验](session-closure-l1.md)、[采用补写](checkpoint-adoption-l5.md)、[HOM恢复](hom-solver-failure-recovery.md)、[后端测试](../test/application_backend_test.py)。本轮是静态语义核对，不新增真实CST证据。
