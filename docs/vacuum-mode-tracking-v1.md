# PEC背景、封闭真空腔模式追踪第一版

日期：2026-10-14。第一版是独立的Python已保存场分析入口，不改变CST求解协议、生产HOM窄窗口枚举、默认nmodes=1或GUI。当前未自动判断工程是否满足物理前提，也未自动生成/登记掩码；调用者必须提供明确域证据及已校验工件。不能将用户声明当作CST工程自动审计的结果。

## 用途与边界

跨网格/重复计算寻找同一模式或同一退简并模组；不是将顺序HOM扫描的不同频率模式匹配成同一个模式。

要求背景PEC、封闭、内部真空、固定几何、完整共同采样盒、E场和独立原生真空solid掩码。所有有效区域为Vacuum，其余excluded。仅真空solid可可靠识别的工程适用；若真空由金属空洞形成，当前不能推断空洞真空。背景识别、端口/开放边界、薄层、多材料、跨几何映射均不在此版。体积权重不是材料能量权重。

`VacuumTrackingDomain`要求几何身份及boundary_evidence/coverage_evidence/sampling_evidence三个证据说明。`TrackingSnapshot`保存场工件、独立材料支持和快照ID。参考场1至4个、候选场1至8个；不按频率接近自动创建退简并组，组成员由调用者明确选择。

## 算法与恢复

1. 校验E场、SI坐标、公共点、工件SHA及独立支持域；ROI、几何变化、不同材料/掩码拒绝，不能自动缩小交集。
2. 读取一次参考/候选场，在真空体积权重上累计Gram和交叉矩阵；候选子集只切小矩阵，不反复读大文件/积分。
3. 单参考使用频率门禁、MAC和匹配差值；多个候选无法唯一确定时unconfirmed。
4. 明确模组枚举同维候选子集，先独立检查存在满足频率门禁的排列，再做白化Gram/SVD子空间比较。缺维、病态、低重叠、多个合格子空间差值不足均unconfirmed。
5. 输出候选模式编号或整个模组；模组匹配不指定X/Y极化成员，也不重排/合并R/Q结果。
6. `VacuumModeTracker`固定锚点，每步均与同一参考比较。无论成功、缺场或歧义，都不自动更新参考，避免累计漂移。更换参考需显式新建Tracker/请求。
7. 每步原子JSON与累计summary；输入坏了可恢复工件后重新分析，完全无Solver回放。原子写入失败向上传播，不伪造已持久化成功。

matched仅表示给定域和显式策略下数值判据通过；physical_identity_confirmed、policy_calibrated及member_identity_confirmed保留False。阈值无默认物理校准；必须提供maximum_frequency_change，频率单位Hz。缺候选不是“区间无模式”的证明，恢复建议不是自动扩窗求解授权。

## 使用入口

Python：`select_vacuum_modes(reference, candidate, domain, policy)`；持久化单步使用`VacuumModeTracker.evaluate(candidate, destination)`。

批量复算：

```powershell
python -m csttool.vacuum_mode_tracking --request tracking-request.json --output tracking-reports
```

所有步matched退出0，有未确认退出2，配置/参考输入错误或写入失败非零退出。参考无效时整个请求拒绝；单个候选加载失败则记为未确认并继续后续候选。每步文件step-0001.json等，summary.json记录所有已处理步；同一输出目录重跑覆盖相同编号，建议每轮独立目录。

请求格式（路径相对请求文件，或绝对路径）：

```json
{
  "domain": {
    "geometry_id": "verified-cavity-geometry-v1",
    "background": "PEC",
    "interior": "Vacuum",
    "closed": true,
    "boundary_evidence": "工程历史/边界核对记录路径和版本",
    "coverage_evidence": "真空solid与完整采样盒核对记录",
    "sampling_evidence": "至少三层采样收敛记录与实际采用的点集"
  },
  "policy": {
    "minimum_mac": 0.9,
    "minimum_margin": 0.05,
    "minimum_subspace_overlap": 0.99,
    "maximum_frequency_change": 0.01
  },
  "reference": {
    "snapshot_id": "reference-task-id",
    "result_file": "reference/task_result.json",
    "support_file": "reference/support.tsv",
    "support_sha256": "替换为实际SHA256",
    "modes": [1, 2]
  },
  "candidates": [{
    "snapshot_id": "candidate-task-id",
    "result_file": "candidate/export-result.json",
    "support_file": "candidate/support.tsv",
    "support_sha256": "替换为实际SHA256"
  }]
}
```

以上阈值仅为接口示例，不是通用推荐。result_file接受Managed任务归档的FieldArtifacts或saved_field_export的PostProcessResult，目录由ResultDirectory/result_directory读取；只选E场，modes可指定参考/候选子集。支持TSV由render_material_support生成；全域证据不能只用CalculationBox或非零场值代替。不要指向已经清理的大文件历史路径。

## 验收与TODO

新增离线测试覆盖单模换号、整体相位/幅度、旋转双模与额外候选、缺维、病态、候选组歧义、频率门禁、错误域/ROI、缺文件后下一步恢复、归档载入/批量报告和写入失败。底层真实物理证据见[Pillbox全域与第二网格验收](physical-domain-pillbox-acceptance.md)；此版Tracker本身尚未重跑真实CST链，不能将之前的真实数据摘要当新接口运行验收。

离线全套469 passed、19 deselected；参考初始化另拒绝缺失文件与秩不足的参考组。CLI子进程实测matched退出0、unconfirmed退出2。pytest临时工件在验收后清理，不保留测试产生的HDF5副本。

- [x] 单真空域固定参考追踪及失败保留锚点、已存场批量复算入口。
- [ ] 新Tracker接入真实Pillbox连续计算验收（先保持独立、串行）。
- [ ] Managed自动掩码登记、物理前提预检和GUI入口。
- [ ] 对目标模式/模组的候选请求控制；与逐频枚举分离，不借组匹配静默合并HOM。
- [ ] 三层mesh及更多模族阈值校准；复杂域后续扩展。

原始场必须在复算时存在并满足SHA；固定参考不能跟随普通临时缓存清理。验收结束可清理一次性测试副本，但生产参考应独立保留并纳入工件保留策略。
