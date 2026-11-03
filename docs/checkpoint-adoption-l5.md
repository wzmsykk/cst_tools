# L5 检查点采用标记对账与补写

现行更新2026-11-04；原2026-10-24验收保留原范围。检查点确认结果与receipt/RunStore的采用标记是两个持久化步骤；补写只同步已确认事实，不导入新结果、不推进覆盖、不改变模型、不调用Solver。

## 权威与绑定

- 标准批次：schema/pending_index与results一致，读取成功结果的TaskID；核对receipt中的任务、会话、任务名、参数、后处理与快照路径/原SHA256。
- HOM：先经现有ScanCheckpointStore验证策略/已确认快照，使用adopted_task_ids及mode.task_id的并集。有模式记录时逐项核对模式号、频率及完整有限标量指标与receipt.postprocess一致；缺值、改值、重复指标及歧义拒绝，不能用数值容差掩盖。允许同Task产生多个模式、也允许已确认任务没有新mode；后者不伪称完成模式数值核验，不把模式数当采用依据。
- 2026-10-25修正：HOM的mode.project_snapshot相对项目根目录解析，绝对路径保持原义；不能按程序cwd解析。真实中断发现、修正和重验见[HOM记录](hom-interruption-l5-acceptance.md)。此补验不改写下方2026-10-24标准批次的历史范围。
- 所有receipt必须身份匹配、状态Success、阶段为received/acknowledged/algorithm_adopted，workspace绑定session；原始快照必须存在且哈希相同。歧义、缺证据或跨检查点同Task冲突继续阻断。
- 只核对生产日志workers及配置runtime内的received记录，标准检查点也可提供ReceiptPath。所属RunStore的run.json必须指向本项目；不会在任意目录猜测结果或新建未知来源的历史运行。

缺TaskID的旧结果不补造身份；有TaskID但证据不足时不宣称采用成功。补写需保留原始快照，已清理的验收数据需重新生成。
先验证整批任务证据，再改元数据。I/O中断可能留下部分标记，下次按相同证明继续补齐；不承诺多个文件瞬间原子提交。

## 最小实现与幂等

[checkpoint_adoption.py](../csttool/checkpoint_adoption.py)提供confirmed_tasks、reconcile_checkpoint_adoptions、validate_hom_mode_receipt及mark_adopted。Backend显式恢复在会话收口、检查点验证后调用；resume准备阶段也在项目锁内调用。普通Manager.adopt_result复用同一标记写入逻辑，receipt已采用也不跳过缺失RunStore修复。

正常/恢复采用顺序：先核验当前运行、receipt祖先运行及该TaskID已有日志索引的run.json归属，再分别幂等补齐RunStore事件日志→任务索引attempt.json，最后写receipt.phase。这也覆盖新运行接力旧receipt时原运行索引仍acknowledged的缺口。每步中断可重新进入；TaskID及已确认检查点是采用身份，不能靠phase字符串创造新计算结果。
RunStore.ensure_adopted每个所属运行对同Task至多保留一条algorithm_adopted事件；同任务在多个历史RunStore中的索引同步仍为同一TaskID的状态副本，不是多次导入。项目级统计须按TaskID去重，不将历史副本计为新计算。
进程内同目录的Worker/Manager RunStore共享锁与采用缓存，避免不同实例并发追加重复事件；旧进程退出后新进程重新从日志恢复缓存。跨进程仍依赖现有项目所有权，不新增分布式服务。

日志中完整有效但缺换行的末行仅补换行。无效的截断末尾先原样保存events.truncated-<hash>.bin并fsync，再截去无效尾部重写元数据事件。中间损坏、完整重复采用事件或证据冲突保留并阻断，不清空日志、不静默去重。该修复不触碰CST模型或检查点。
重复对账不重复追加采用事件、不改已完整的receipt/index，不产生新TaskID。日志CHECKPOINT_ADOPTION_RECONCILED表示核验与同步任务数，包含原本已一致的任务，不等于新增导入数量。

## 证据与当前边界

源码为checkpoint_adoption.confirmed_tasks/reconcile_checkpoint_adoptions/mark_adopted与RunStore.ensure_adopted；离线用例见test/checkpoint_adoption_test.py。2026-10-24三个标准双任务串行副本窗口和10月25日HOM相对快照路径修正见[原批次完整记录](archive/20261103-semantic-review/checkpoint-adoption-l5.md)及[HOM记录](hom-interruption-l5-acceptance.md)。旧原始模型清理后须重新生成；不以旧“进程为空”描述今天。

本功能不新导入结果、不推进覆盖、不调用Solver。各批次768/34/85项存在重叠，不作为本次新验收。跨文件采用仍可能部分写入，暂停/重入按证据幂等补齐；跨进程依赖项目所有权，不宣称分布式事务。

生产Runner/HOM真实官方中止、首结果采用、四时点Runner退出及反复恢复的当前专项见[闭环验收](runner-hom-abort-adoption.md)。首模式采用后主动暂停，不代表目标区间完整扫描，也不等同物理模式身份判定。
