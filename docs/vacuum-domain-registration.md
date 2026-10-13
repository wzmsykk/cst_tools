# 真空域自动掩码登记与工程前提预检

日期：2026-10-14。限定PEC背景、六面electric、无对称面、无端口、全部显式solid为内置Vacuum且为体积实体。宁可拒绝范围外的工程，不推断金属空洞、背景真空、多材料或开放结构。

## API与执行链

- `register_vacuum_domain(executable, source, destination, sampling, geometry_id=...)`：独立只读副本加载/带结果另存；查询工程属性与实体包围盒，生成原生掩码和`domain-registration.json`。无Rebuild、历史修改、Solver.Start；独立串行租约、最小化、完成标记/实际退出/源SHA核对。目标目录必须全新。
- `load_registered_support(registration_path, source_sha256=..., sampling=..., geometry_id=...)`：只接受registered，复核源身份、点集、几何身份、库存SHA、掩码SHA和support ID；再次验证库存，不依赖之前status字段单独放行。
- `export_registered_vacuum_fields(executable, source, destination, settings, geometry_id=...)`：先预检/登记再导出E场；拒绝则不调用场导出，返回的`tracking_input`及tracking-input.json可直接作为Tracker快照描述符。只允许同一公共点集的ExportModeField/E步骤。两个原生会话串行，不嵌套CST独占租约。
- `load_tracking_snapshot`新增可选`registration_file`；自动从登记读取掩码，不再手工填support_file/SHA。要求导出JSON有source_sha256且匹配登记；旧显式掩码接口保留，但不因此获得自动工程预检保证。

描述符示例：

```json
{
  "snapshot_id": "task-or-snapshot-id",
  "result_file": "fields/export-result.json",
  "registration_file": "domain/domain-registration.json",
  "modes": [1, 2]
}
```

路径相对Tracker请求文件；工具生成的描述符使用绝对路径。需要明确的固定geometry_id与sampling_evidence；不把整个CST SHA当纯几何身份，不自动证明采样收敛。工程SHA只绑定该次保存快照，不跨mesh直接复用登记。

## 文档依据与拒绝规则

安装版CST2022 VBA：Material Object.GetTypeOfBackgroundMaterial、Boundary.GetXmin/GetXSymmetry等、Port.StartPortNumberIteration、Solid.IsSolidShape/GetLooseBoundingBoxOfShape、Units.GetGeometryUnitToSI。背景getter属于Material，不是猜测的Background.GetType。GetLooseBoundingBoxOfShape为非紧包围盒，保证覆盖solid体积，但文档禁止历史重建/结构宏期间调用；本实现独立控制宏加载已保存工程，不进入AddToHistory。

要求采样盒覆盖所有solid的非紧包围盒（SI，1nm数值容差）。这可能保守拒绝本来覆盖实际实体的更小盒子；不偷偷截断。检查所有实体而非仅选择某个Vacuum solid；非体积薄片或其他材料拒绝。无solid时拒绝，不能自动将空洞判为真空。

registered仅是工程前提与工件校验通过，不是物理模族、材料普适性、体积求积误差或mesh收敛证明。六面electric/无ports保守限定封闭域；未提供通用CAD拓扑有效性检查，也不判断真空并集连通性。标准CST体积实体查询是本版几何支持依据。

状态：registered可使用；rejected有具体rejection_reasons，不得进入后续导出/目标求解；查询/退出失败为incomplete并保留宏/日志/会话状态后抛异常。拒绝目录可能保留诊断掩码，但没有合法登记，不可绕过使用。

## 验收入口和剩余边界

`test/support/validate_pillbox_cross_mesh.py --meshes 8 10 --tracking --automatic-domain`：在任何Solver前预检prepared工程，每个完成快照自动登记，再检查解析掩码及新Tracker/CLI。

`--reject-preflight-root artifacts/<本轮目录>`：仅在基准副本中历史化修改背景Normal和Xmin=open，再独立预检；无Solver，预期rejected。原基准不改。

自动登记是上述显式API/验收流程的一部分，尚非所有Managed任务默认行为；GUI、扫描候选请求自动调度仍待接入。采样门禁继续由独立收敛证据提供。

## 本轮真实结果

证据：`artifacts/pillbox-cross-mesh-6df09e8c/report.json`。prepared工程在Solver前registered；cell8/10两份完成快照分别registered，原生掩码与圆柱解析逐点一致，共同64³采样。实际单元数5332/10220，跨网格最小平方子空间重叠约0.999944823，Tracker/CLI正常、缺文件恢复及缺成员后恢复通过。生产默认网格未改变。

`preflight-rejection.json`：独立错误副本（Normal背景、Xmin=open）rejected，两个明确原因均出现；查询退出0且源不变，无Solver。

`registered-export/workflow-report.json`：公共export_registered_vacuum_fields实际调用通过，自动产生tracking-input.json且load_tracking_snapshot成功读出两mode；仅复用cell8保存场，无重建/求解回放。登记与导出源SHA一致。

所有native步骤串行标准退出，无强杀。离线门禁包含错误背景/边界/材料/端口、覆盖不足、登记源不符、库存/掩码变动及预检拒绝后不调用导出。

最终完整离线478 passed、19 deselected（16.48秒）。可靠进程检查无CST主实例/Modeler/Solver残留，源工程SHA不变。本轮大型模型/原生场/HDF5与pytest临时目录已清理；登记、拒绝、Tracker及workflow报告、库存/掩码TSV、宏与日志保留。描述符原始场路径已失效，复算需重新生成，不能把轻量登记视为原始场仍存在的证明。
