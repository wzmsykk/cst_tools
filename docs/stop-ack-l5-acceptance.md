# L5 停止与任务 ACK 时序验收

后续[六类GUI/Runner实际进程退出](controller-exit-l5-acceptance.md)补验已完成；下文OS级Controller退出pending为本章当时边界，整机掉电、任意指令级窗口等仍pending。

日期2026-10-24，CST2022.5；延续[首轮真实验收](close-v2-l5-acceptance.md)。
使用test/data/Pillbox/Pillbox.cst重新预处理cell=8，每次独立副本，nmodes=1、500–800MHz，串行、不强杀。
工具：[validate_stop_ack_l5.py](../test/support/validate_stop_ack_l5.py)。调度等待点只写入本轮副本宏，不加入生产配置或wire协议。

## 范围与判据

|时点|进入方式|应核验行为|
|---|---|---|
|before-parameters|宏收到Task，在第一检查点之前暂等|取消，不采用，未调用Solver|
|after-rebuild|真实重建后暂等|停止后收尾，不采用，未调用Solver|
|during-solver|观察调用Start日志且尚无返回日志时发StopRequest|不强杀，不重复调用；Start返回后在安全点取消；原始场/中断快照应保留|
|after-solver|真实Start返回、有模式后在检查点暂等|保留中断快照，不把未后处理结果当成功|
|completion-before-receive|成功Completion已发布，Python尚未读取|停止保留Completion；显式恢复先读取产物，再对账|
|received-before-ack|Python已持久接收，尚未发ACK|从接收记录恢复，不重复Solver|
|ack-accepted|真实接受ACK后、尚未删除Task|先接收记录后清理，无重复采用|
|task-deleted|真实Task删除后、Completion仍在|部分清理可恢复，已有快照可核验|
|completion-deleted|Completion也删除，ACK尾部尚在|不能因Completion消失而漏掉未采用的接收记录|
|ready-before-adopt|ACK清理和ready完成，算法尚未采用|关闭事实与结果采用分开，已有成功结果不丢失|
|wrong-ack / truncated-ack|Python已接收，发布其他session的ACK或截断ACK|原生ACK_BLOCKED，不清理原任务；正常停止后核验真实Completion和快照，错误ACK保留，不按它确认成功|

求解等待不设总超时；启动、通信和退出保持有界。during-solver的观测仅证明Python在“调用日志—返回日志”之间发送停止，不是原生线程栈采样。
本轮不是操作系统层杀掉Controller/GUI的故障注入，也不是完整HOM扫频重跑；对正常结果的采用使用实际CSTManager.adopt_result，并两次调用验证幂等及禁止再次候选。
本轮使用手动生产文件协议驱动延后Python接收，实际持久记录为received；acknowledged记录的发现/绑定由离线参数化回归覆盖。未覆盖生产run_task成功后目录重命名中崩溃或RunStore落盘失败，不以ready窗口替代这些验收。
场/工程大小与哈希、真实回执、进程退出和会话发现均在清理前核验；artifacts不保证随Git迁移。

## 过程问题与证据

首个探针误用FileProtocol的通用inbox，而生产宏使用current.task；未提交到生产入口、没有求解。通过该session合法StopRequest正常关闭，失败轮不计通过。工具改为生产固定文件、匹配Task/Completion身份；新增离线探针测试，避免把未触达的时点称为通过。
初期探针测试还发现已生成宏中的占位符已被真实路径替换，调度锚点必须使用生成路径；不改变生产协议来迁就测试。

## 真实发现与修复

`stop-ack-l5-9bcc39c4/ack-accepted`真实复现：ACK清理完成后Completion消失，成功received记录尚未采用；旧发现逻辑不再要求恢复，find_received_result缺少recovery决定，导致已完成结果不能进入恢复候选。
修复`ManagedSessionRecord.pending_result_task_id`：从当前task-context对应的接收记录核对session/task/phase/status，成功received或acknowledged且尚未对账时保持恢复门禁，独立于物理标准关闭。
缺证据使用received-result-not-reconciled，结果状态received-unadopted，不伪称Completion仍在。失败或algorithm_adopted不因此重新打开采用流程。
显式恢复记录received_task_id；历史决定只有绑定同一Task才能沿用（旧记录可用匹配completion_task_id绑定），不同Task不能借用既有决定。
坏接收身份/状态不作为安全证据；新字段为增量内部数据，v1/v2 wire不改。旧Runner需正常退出后更新，无热替换。

## 当前通过范围

前六种停止/接收窗口通过于stop-ack-l5-9bcc39c4；该目录ack-accepted是修复前失败证据，不计通过。
ACK接受窗口修复后在stop-ack-l5-a8d01e5d通过；后半三窗口在stop-ack-l5-7d52a46e通过。
错误session/截断ACK在stop-ack-l5-1d81bb55通过：真实WinWrap记录ACK_BLOCKED，不采用错误ACK、不覆盖错误文件；确认停止及进程退出后，显式恢复依据真正的Completion/快照/后处理导入成功结果。任务ACK错误不被当作StopAck错误或伪造任务失败。
before-parameters/after-rebuild均零次Solver；during/after-solver取消不采用；成功Completion的恢复均使用实际频率503.605585325746MHz、一次Solver，实际Manager连续采用两次但事件只写一次。
复核汇总工具verify_timing_reports会在清理前再次核对回执/原始产物、原子采用事件以及中断副本E/H与活动场哈希；实际完整结果和清理位置以current-status为准。

本轮已实际执行汇总复核，十二点通过：artifacts/stop-ack-l5-verification-20261024.json。
四个通过目录共十二点，未把两个失败轮加总为通过。离线739 passed、21 integration deselected（145.55s）；主窗口独立34 passed（1.31s）；最终停止/ACK/恢复/覆盖/文档及日志索引77 passed（3.96s，含重叠）。XML为artifacts/stop-ack-l5-{offline,window,focused}-20261024.xml。
当源模型已清理时，先运行validate_close_v2_l5.py的prepare，再用输出prepared.cst运行本工具--point all；复核必须在原始副本删除之前进行。

本轮六个验收/准备目录已在全部进程退出后清理186014676字节模型/原始场，pytest临时目录亦清理。保留报告、汇总、宏、原生日志retained-native、错误ACK、接收/恢复记录及cleanup.json哈希清单。现在不能直接对原模型路径重做快照核验或继续算，必须重建副本；原工程哈希保持7b63939b2dbed3de567aa55a5ff19cb69e7447245882a691be15d28580f1ddfa。

剩余：真正Start=0/Start异常/退出1，所有VBA步骤任意指令级停止、Controller/GUI操作系统级突然崩溃、大工程长耗时/多版本等。当前固定参考算法的顺序采用语义不等于任意批量API的所有历史任务恢复验收。
