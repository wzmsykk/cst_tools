# P0：保存场缺失、工件损坏与分析恢复验收

日期：2026-10-14。CST2022.5。功能F06/F07/F08/F17；本轮增加验收工具，不改变生产HOM扫描、必需标量后处理或物理身份策略。

## 实际验收

工具：`test/support/validate_field_failure_recovery.py`。证据：`artifacts/field-failure-recovery-21dbe3e6/report.json`。

保留状态：该历史报告及原始工件已在用户磁盘清理中移除；此处保留当时验收记录，路径不是当前可访问证据。工具与离线测试可用，真实原始数据需重新生成，不能仅凭本文复算。

1. 从已求解工程只复制.cst到新目录，故意不带同名结果目录。只对新副本调用保存场导出，无Rebuild、参数修改或Solver.Start。
2. CST导出Mode 1 E场明确返回`FAILURE -2147221502 mode field missing`；工件unavailable，整体incomplete，尽管进程退出0且宏完成标记存在。原工程与导出输入副本哈希不变，所属进程退出，无残留。
3. 选取先前实际CST导出的12³ ROI E场，在独立HDF5副本注入四种故障；不修改参考工件，不以Python合成场替代本次真实数据。

|故障|失败诊断|恢复|
|---|---|---|
|移走工件（保存在同目录quarantined.h5）|FileNotFoundError，incomplete|从完好参考工件恢复副本，complete|
|改变真实HDF5属性，保持原SHA声明|field artifact hash changed，incomplete|恢复副本及原身份，complete|
|删除E-Field数据集，并重算SHA|KeyError，incomplete；证明不是只靠哈希拒绝|恢复副本，complete|
|修改采样坐标，并重算SHA|coordinates do not match SI sampling specification，incomplete|恢复副本，complete|

所有恢复只运行Python场分析，未调用CST或Solver；仍physical_identity_confirmed=False、policy_calibrated=False，不自动确认或合并模式。

## 工具故障及重跑

首次CST缺场验收成功，但后续工具未显式提供MatchPolicy阈值，抛TypeError。该次不能算完整通过。修正为显式0.9/0.05/0.99诊断阈值，使用`--resume-root`复用已保存的缺场导出证据，重新生成独立分析副本并完成四项验证；原工具错误保留在report.previous_probe_failure中，没有重启CST或重跑Solver。

这些阈值仅用于诊断自一致对照，不是本次获得的物理校准值。恢复是利用完好备份，不是从丢失文件中重建场。

## 范围与后续

- 已通过：无结果目录的真实保存场导出失败判定、真实导出HDF5的四种故障及分析恢复。
- 未覆盖：已求解且仍有频率/网格时仅部分E/H缺失、原生网格文件缺失、必需运行时标量积分缺场、全部存储/退出故障及跨CST版本。
- 原生E/H结果丢失时须提供有效结果目录或备份；没有备份就不能声称无需求解即可恢复。本轮也不恢复物理身份或猜测缺失模式。
- 原始模型/场数据位于本地artifacts，未保证随Git迁移；源码、测试及本文保留入口和证据摘要。

离线完整回归442 passed、19 deselected（9.10秒），文档索引包含新入口及源码符号。尚未提交。
