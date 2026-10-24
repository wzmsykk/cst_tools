# 真实HOM恢复：路径语义与扩窗观察

日期：2026-10-25。验收入口：[小网格HOM](../docs/hom-interruption-l5-acceptance.md)。

## 已确认的项目格式语义

生产 `HomScanAlgorithm.start` 将结果快照保存为相对 `manager.currProjectDir` 的 `mode.project_snapshot`；`confirmedSnapshot.path` 则由 ScanCheckpointStore 保存为相对检查点父目录。两者相对基准不同，不能共用cwd，也不能凭字段都叫path就互换。

receipt.snapshot为绝对路径并绑定snapshot_sha256。采用对账必须先按各自格式解析，再比对同一个快照及哈希。修正仅影响Python恢复核验，不改变CST、VBA或历史参数。

## 实测

首轮合法HOM检查点恢复被旧核验拒绝：`HOM checkpoint result differs from receipt`。快照、receipt和检查点身份一致，仅相对路径基准错误；原确认覆盖仍在，未退回起点或调用Solver补偿。失败报告保留在 `artifacts/hom-exit-l5-d1252d1f/checkpoint/acceptance-report.json`。

无中断小网格基线在480–530MHz找到503.494643596MHz；随后返回688.745670981MHz并按现有策略扩窗至约738.745671MHz，扩窗计算返回503.583114639MHz，被登记为另一近频结果。本基线最终需要5次Solver调用、两次扩窗，不应武断将所有超过两次的调用都归为恢复重复。

## 推测与待验证

扩窗伴随网格生成，频率变化可能与网格/求解设置相关；尚未在固定实际网格上做对照，也未用场重叠证明两个近频结果属于同一物理模或退简并。不能因TaskID不同就宣称独立物理模式。此物理判别问题与本轮确认结果/任务采用幂等分开记录。

## 证据保存

最终真实基线及checkpoint/received/solver三窗口均通过，每例Solver5次，任务参数顺序与基线相符，恢复不改确认检查点/旧结果/四场哈希，CSV和采用事件不重复。各用例无活跃进程或needs_recovery阻断；孤立旧CST失去退出码观测时明确abandoned-dead，而非捏造标准退出0。汇总 `artifacts/hom-interruption-l5-verification-20261025.json`。

跨独立求解区间末位约1e-12MHz差异是真实输出差别，不能要求逐字节相同；容差与严格旧产物SHA/身份/计数检查分别记录。不是通过容差接受重复Task或重复CSV行。

真实矩阵及清理结果以验收文档最终记录为准。artifacts不保证随Git迁移，清理后报告中的模型路径需重新生成，不能仅依据轻量元数据再次进行严格快照核验。
