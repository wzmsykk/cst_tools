# L5 检查点采用标记对账与补写

2026-10-24。检查点确认结果与receipt/RunStore的采用标记是两个持久化步骤；补写只同步已确认事实，不导入新结果、不推进覆盖、不改变模型、不调用Solver。

## 权威与绑定

- 标准批次：schema/pending_index与results一致，读取成功结果的TaskID；核对receipt中的任务、会话、任务名、参数、后处理与快照路径/原SHA256。
- HOM：先经现有ScanCheckpointStore验证策略/已确认快照，使用adopted_task_ids及mode.task_id的并集。允许同Task产生多个模式、也允许已确认任务没有新mode；不把模式数当采用依据。
- 2026-10-25修正：HOM的mode.project_snapshot相对项目根目录解析，绝对路径保持原义；不能按程序cwd解析。真实中断发现、修正和重验见[HOM记录](hom-interruption-l5-acceptance.md)。此补验不改写下方2026-10-24标准批次的历史范围。
- 所有receipt必须身份匹配、状态Success、阶段为received/acknowledged/algorithm_adopted，workspace绑定session；原始快照必须存在且哈希相同。歧义、缺证据或跨检查点同Task冲突继续阻断。
- 只核对生产日志workers及配置runtime内的received记录，标准检查点也可提供ReceiptPath。所属RunStore的run.json必须指向本项目；不会在任意目录猜测结果或新建未知来源的历史运行。

缺TaskID的旧结果不补造身份；有TaskID但证据不足时不宣称采用成功。补写需保留原始快照，已清理的验收数据需重新生成。
先验证整批任务证据，再改元数据。I/O中断可能留下部分标记，下次按相同证明继续补齐；不承诺多个文件瞬间原子提交。

## 最小实现与幂等

[checkpoint_adoption.py](../csttool/checkpoint_adoption.py)提供confirmed_tasks、reconcile_checkpoint_adoptions及mark_adopted。Backend显式恢复在会话收口、检查点验证后调用；resume准备阶段也在项目锁内调用。普通Manager.adopt_result复用同一标记写入逻辑，receipt已采用也不跳过缺失RunStore修复。

正常/恢复采用顺序：RunStore事件日志→任务索引attempt.json→receipt.phase。每步中断可重新进入；TaskID及已确认检查点是采用身份，不能靠phase字符串创造新计算结果。
RunStore.ensure_adopted每个所属运行对同Task至多保留一条algorithm_adopted事件；同任务在多个历史RunStore中的索引同步仍为同一TaskID的状态副本，不是多次导入。项目级统计须按TaskID去重，不将历史副本计为新计算。
进程内同目录的Worker/Manager RunStore共享锁与采用缓存，避免不同实例并发追加重复事件；旧进程退出后新进程重新从日志恢复缓存。跨进程仍依赖现有项目所有权，不新增分布式服务。

日志中完整有效但缺换行的末行仅补换行。无效的截断末尾先原样保存events.truncated-<hash>.bin并fsync，再截去无效尾部重写元数据事件。中间损坏、完整重复采用事件或证据冲突保留并阻断，不清空日志、不静默去重。该修复不触碰CST模型或检查点。
重复对账不重复追加采用事件、不改已完整的receipt/index，不产生新TaskID。日志CHECKPOINT_ADOPTION_RECONCILED表示核验与同步任务数，包含原本已一致的任务，不等于新增导入数量。

## 真实串行副本验收

工具[validate_controller_exit_l5.py](../test/support/validate_controller_exit_l5.py)的--point adoption-cases，在实际标准批次R=229/220、cell=8、nmodes=1、400–800MHz中结束本轮Runner Python，不结束CST。

|窗口|退出前receipt / index /采用事件数|恢复目标|
|---|---|---|
|检查点两项已确认、采用尚未开始|acknowledged / acknowledged / 0|两端补齐，事件1条|
|事件已fsync、索引尚未写|acknowledged / acknowledged / 1|索引与receipt补齐，不追加事件|
|索引已写、receipt尚未写|acknowledged / algorithm_adopted / 1|仅补receipt，不追加事件|

本轮三个窗口均实际通过于artifacts/controller-exit-l5-0a38ff1f下对应子目录。每例显式recover两次，第二次标记文件/日志哈希不变；原检查点字节不变，首任务工程/四个场哈希不变，续跑后TaskID保持且Solver总调用数仍2；find_received_result不再把已采用Task作为可导入候选。
对应report含marker_before_exit、marker_final及marker_repair_idempotent，不将脚本退出0单独当验收。
清理前统一复核已通过，汇总artifacts/checkpoint-adoption-l5-verification-20261024.json。三个用例各自为两个任务，Solver总数每例2，而不是三轮合计2。

## 离线门禁与剩余

[checkpoint_adoption_test.py](../test/checkpoint_adoption_test.py)覆盖单边标记、日志/索引中断、截断尾部、错误/重复/歧义证据、多个RunStore实例并发、同Task多个运行索引、HOM有模式/空任务及无检查点不采用。合成模型字节不是CST实测；准确最终数字见current-status。
最终离线768 passed、21 integration deselected（167.10s）；主窗口独立34 passed（1.28s）；最终采用/日志/恢复/后端/文档和事件索引85 passed（7.99s，含重叠）。报告artifacts/checkpoint-adoption-l5-{offline,window,focused}-20261024.xml。最初一项整批验证夹具重复创建目录失败已修正，失败不计通过；生产门禁未因此放宽。
真实测试为标准双任务链，不代表完整真实HOM、所有可选后处理、掉电、文件系统损坏或任意指令级窗口。新采用对账已替代上一轮“标记补写pending”；L5其他未触发项仍pending。无需修改Python/VBA wire，也不热替换旧Runner。
轻量报告/宏/参数/哈希保留；artifacts不保证随Git迁移，原始副本清理后不能直接重验旧路径。

本轮三例测试Runner全部离线，正常权限CST清单为空，原Pillbox SHA256保持7b63939b2dbed3de567aa55a5ff19cb69e7447245882a691be15d28580f1ddfa。已清理93488634字节模型/原始场和pytest临时数据；检查点、标记与报告仍保留，但其旧模型路径现不可用于直接恢复或重验，须先重新生成。源码/文档未提交或打包。
