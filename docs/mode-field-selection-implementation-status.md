# 场匹配六阶段实施与验收记录

日期：2026-10-13。对应[实施计划](mode-field-selection-implementation-test-plan.md)。本实现是可选诊断，不改变HOM扫描、默认 `nmodes=1`、原始模式编号或标量后处理结果。

## 阶段结果

|阶段|交付与实测|尚未通过的门禁|
|---|---|---|
|M0 数值核心|加权复内积、MAC、一对一匹配、歧义拒绝、Gram白化/SVD；合成相位、尺度、旋转、缺失及解析dipole测试|解析合成测试不替代真实Pillbox验收|
|M1 同语义效率|公共点与非均匀权重下，原生SetArray小矩阵和HDF5→Python数值一致，误差低于1e-6；本次样本HDF5路线更快|跨快照总成本、独立资源对照未完成，不宣称全局最优|
|M2 工件|运行时E/H公共点HDF5导出，原子发布、摘要、单位/坐标/点数检查；24个跨网格工件可读|几何材料掩码未独立验证|
|M3 跨网格|cell=30/36，在12³、24³、48³共同ROI采样比较，E匹配稳定|全域求积、真实Pillbox及更多网格/模族校准|
|M4 模组|E/H双模子空间均稳定；H单模差值不足时明确未确认，而非强行分配|阈值仍为试验策略，未作为自动物理身份门禁|
|M5 接入与恢复|真实CST求解成功，7项标量与3项场工件分离；故意越界导出失败不影响求解成功；恢复仅重算诊断，不重跑求解|GUI设置入口和自动模式接收不在本次范围|

离线回归：`python -m pytest -q -m 'not integration' --basetemp .pytest_cache/field-final-20261013`，**391 passed，19 deselected，9.04秒**。被排除的是集成测试，不表示其失败；本次真实CST另由专用验收脚本运行。

## 接口与使用

- `csttool/mode_matching.py`：纯NumPy数值计算。场数组为 `(points, 3, modes)`；加权矩阵经过尺度归一化，仅用于匹配，不是物理储能。
- `csttool/field_artifacts.py`：`SamplingSpec`定义SI单位矩形域中心采样；按需加载h5py，校验工件后读取。
- `postprocess_cst.py`注册 `ExportModeField`；实际宏为 `data/postprocess/ExportModeField.vb`。具体参数配置参见 `test/support/validate_managed_field_diagnostic.py`，包括模式、E/H、采样点数及SI边界。
- 安装可选依赖：`python -m pip install ".[field-analysis]"`。
- Manager可选参数 `field_reference_result`、`field_match_policy`，对应WorkerConfig同名字段；策略必须显式提供。默认不启用。
- `SimulationResult.FieldArtifacts`与`PostProcessResult`分开，`FieldDiagnostic`记录诊断。诊断在任务Ack及归档后执行；失败不会回滚已经成功的求解。
- `saved_field_export.py`用于已有场结果：CST带结果另存，再导出，不改参数、不Rebuild、不调用Solver。不能仅复制.cst便假定已有E/H场可用。

## 真实证据与结论边界

证据目录均在工作区 `artifacts/`，默认不进入源码发布包：

- `field-efficiency-a96127bc/report.json`：串行公共点对照，原生小矩阵与Python结果一致，标准退出且原工程未变化。Result3D.SetArray需要明确的Double数组；Variant数组曾失败。计时包含采样/权重转换和HDF5准备读取，不只比较点积算子。
- `cross-mesh-fields-b8ab3d42/report.json`：24个工件。E单模对应发生1↔2交换，MAC约0.999995以上；双模子空间最小平方奇异值约0.999979。H单模差值约0.036，低于试验要求0.05，因此未确认；组级值约0.99978。
- `managed-field-diagnostic-337eb346/report.json`：最新接口真实验收。两个有效场、一个故意无效域；求解成功，初始诊断incomplete，剔除无效工件后的分析恢复complete，`recovery_solver_replayed=False`；StopAck及标准退出通过，源文件摘要不变。

所有匹配报告保持 `physical_identity_confirmed=False`、`policy_calibrated=False`。ROI稳定只能证明该采样指标稳定，不能证明完整场身份，更不能证明R/Q方向或位置无关。

## 发现的问题与防护

1. CST2022指定点HDF5导出的坐标仍为工程单位，即使设置导出米单位。读取曾被严格坐标检查拒绝；现显式记录原始单位及比例，转换为SI再比较。
2. `GetListItem=True`不等于点位于有效场支持域；越界点可能返回全零。现增加CalculationBox边界检查及全零拒绝。材料掩码仍需后续独立验证。
3. 场导出失败必须是可选诊断失败，不能污染标量结果或触发求解重放；工件状态、任务/会话身份和原子发布负责防护。
4. 资源补测 `field-efficiency-ce4e7d62`曾与求解重叠，只作后台负载记录，不用于排名。随后串行补测 `field-efficiency-c195c01e`遇到LoadProject的`bad function call`及批任务关闭提示，未产生有效计时，也不用于排名。标准Quit调用返回不等于进程退出；随后检查确认该进程已退出，未强制结束。

## 下一门禁

先完成独立资源对照与全域支持验证，再做真实Pillbox极化旋转、多网格/多模式及冷缓存对照。校准阈值后，另行评审是否允许诊断参与自动接收。当前功能可以用于观察与故障排查，不应用于自动删除、合并模式或跳过扫描区间。
