# L5 Controller / GUI 意外退出验收

后续[检查点采用标记补写](checkpoint-adoption-l5.md)已实现，并新增三个真实退出窗口验证；下文首轮receipt仍acknowledged及“补写TODO”保留当时证据，不是现行限制。

2026-10-24，CST2022.5。测试仅结束本轮Popen创建的GUI或Runner Python进程；不结束CST及其进程树，不更改原工程，副本串行。
工具：[validate_controller_exit_l5.py](../test/support/validate_controller_exit_l5.py)。

## 验收安排

同一副本标准批次两个任务：Pillbox R=229、220，cell=8，nmodes=1、400–800MHz，Frequency后处理。
第一个任务已写检查点，记录TaskID与工程快照哈希后，在第二任务指定时点让控制进程意外退出。
重启后先显式recover，再resume；检查第一任务TaskID/快照保持、检查点最终恰好两条结果、所有会话Solver调用总数恰好2。
不把启动新Worker当重新求解，不把控制器重启后丢失退出码解释为标准CST退出；死会话的显式放弃与结果采用仍分开。

|场景|注入位置|验收重点|
|---|---|---|
|GUI退出|实际MainWindow进程结束，Runner继续|新GUI连接同一Runner；两项任务继续，无重复提交|
|Runner求解区间退出|第二次Start调用日志之后、返回日志之前|CST继续完成；重启后接收既有Completion、恢复并续跑|
|Runner完成未接收|实际_wait_completion已读到Completion、尚未持久接收|重启从Completion及产物导入|
|Runner接收未ACK|接收记录已落盘，publish_ack之前|保留received、Completion，不重算|
|Runner归档窗口|实际_name_result_archive完成目录/文件重命名、receipt路径尚未更新|位置变化后仍能核验原Task快照，不盲目寻找或重算|
|Runner检查点未采用|第二结果已写入标准检查点，adopt_result入口之前|以已持久确认的检查点续跑，不能再次执行第二任务|

GUI用Qt offscreen运行真实MainWindow/RunnerController，覆盖进程及客户端逻辑，不代表现场窗口视觉验收。
测试Runner在选定Python调用处使用等待点以确定退出窗口，进入后直接结束该Runner进程，不执行它的finally；CST宏无强制终止。
正常求解不设总超时，启动/通信/退出仍有界。源码修复和实际结果在完成后补入本节，未证实部分保留pending。

## 实际发现与修复

1. 恢复已经报告IDLE，但执行线程仍在释放时，立即start返回409 run still active。原有命令门禁正确阻止并发；新增Runner.snapshot的execution_active运行时事实，GUI在该标志存在时保持RECOVERING/STOPPING，完成收尾后再允许开始。旧后台没有字段时保留旧展示与服务器门禁，不热替换旧后台。此字段是HTTP快照的实时事实，不是status.json中的持久线程身份。
2. 真实归档窗口使receipt.snapshot指向已不存在的旧路径，导致恢复续跑失败，未产生额外Solver。现recover_completed_result即使Completion已清理也检查已有成功receipt；只用同UUID目录的task_result.json、匹配Task/Session/任务名/后处理及原snapshot_sha256修复映射。旧的物理恢复决定已存在时，find_received_result也使用同一严格核验。缺失/多义索引、原文件被改、身份或哈希不符继续阻断，不遍历任意模型、不重算。

采用现有归档索引，没有增加通用事务服务或跨语言ABI。索引尚未写出的中间重命名窗口仍待验收；不能把本次“归档函数已返回、receipt尚未更新”扩大为任意指令级恢复保证。
归档修复不改模型、场或已确认检查点，只更新经过核验的receipt路径及archive_reconciled_from。成功receipt已存在时也校验快照哈希；两项旧离线接收夹具缺快照字段已补成完整合成证据，没有降低生产检查。

## 已有证据

|目录（artifacts下）|结果|
|---|---|
|controller-exit-l5-eb6b63a2/gui-exit|实际GUI进程结束/重新创建，同一Runner完成两项，Solver总数2，第一快照TaskID与哈希不变；保留gui-observed.json中的新观察PID。Qt offscreen，无视觉验收|
|controller-exit-l5-03f5d108/runner-solver|Runner在第二项Start区间被结束，CST继续完成；新Runner显式恢复与续跑，Solver总数2、第一快照不变|
|controller-exit-l5-03f5d108/runner-completion|收尾竞态的失败轮，409安全拒绝，不计通过|
|controller-exit-l5-adca59c9/runner-completion|增加execution_active后通过；Solver总数2、第一快照不变|
|controller-exit-l5-411936a4/runner-received|接收未ACK窗口通过，实际received跨进程恢复，Solver总数2；第一快照与原始场哈希不变|
|controller-exit-l5-411936a4/runner-archive|归档路径失配失败轮，保留原结果及检查点，不计通过|
|controller-exit-l5-e8cc03d0/runner-archive|严格重绑定后通过，Solver总数2、第一快照与场哈希不变|
|controller-exit-l5-77d51daf/runner-checkpoint|第二条检查点已确认、adopt标记前实际Runner结束；恢复后pending_index=2、两条原TaskID不变、Solver总数2、第一快照/四个场哈希不变|

Runner死亡后丢失原Popen退出码的会话仍显示exited-unverified，经显式恢复标为abandoned-dead，不伪造退出0或标准关闭；有效结果独立核验后采用。
最终检查点窗口、复核汇总、离线数字和清理情况见本文补充及current-status。

六类清理前统一复核已通过，汇总artifacts/controller-exit-l5-verification-20261024.json：重算Solver次数、检查点、两条结果receipt快照哈希和原第二TaskID；后四类还比较首任务e1/eenergy1/h1/henergy1四个文件的前后哈希。前两类未事先记录场文件哈希，只验证TaskID和工程快照，不补造更强的证据。
离线746 passed、21 integration deselected（90.83s）；主窗口独立34 passed（1.27s）；最终退出/GUI/恢复/协议/文档与日志索引50 passed（40.24s，含重叠）。XML为artifacts/controller-exit-l5-{offline,window,focused}-20261024.xml。验收结束后全部测试Runner离线，正常权限下CST清单为空；原Pillbox哈希仍为7b63939b2dbed3de567aa55a5ff19cb69e7447245882a691be15d28580f1ddfa。
检查点用例第二receipt最终仍为acknowledged：检查点在标记之前已持久确认，续跑以pending_index为权威而跳过任务，本轮不回写历史采用事件。标记补写及跨算法导入组合仍是独立TODO，不把该标记误读为Solver尚未完成。

所有Runner/CST退出后，本轮六个目录清理249267286字节模型/原始场及pytest临时目录。保留汇总、成功与失败报告、宏、原生日志retained-native、参数、检查点/接收/恢复记录和cleanup.json哈希；大型原始模型/场现已不存在，重验或继续测试必须重新生成，不可把报告里的路径当现存可恢复数据。artifacts不保证随Git迁移，源代码/文档尚未提交或打包。

## 尚未覆盖

整机掉电/文件系统崩溃、归档索引尚未发布的部分rename窗口、任意Python/VBA指令、原生0xC0000005等特定故障源、Start=0/Start异常/退出1原因、大工程和其他CST版本，以及完整HOM扫描中所有窗口组合。本轮为真实标准两任务链，不能替代全HOM回归或远程分布式验收。
