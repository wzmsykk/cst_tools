# 场匹配六阶段实施与验收记录

过程发现及未见文档承诺的行为见[运行时知识库](../knowledge-base/cst-2022-runtime-hidden-behaviors.md)，其中区分实测、推测、失败路线和待验收边界。

日期：2026-10-13。对应[实施计划](mode-field-selection-implementation-test-plan.md)。本实现是可选诊断，不改变HOM扫描、默认 `nmodes=1`、原始模式编号或标量后处理结果。

## 当前结论

六阶段的最小诊断实现已有交付，但**六阶段最终验收尚未全部完成**。已有真实证据只覆盖CST2022、指定ROI、cell=30/36和双模样本；不能据此宣称全域物理身份、最优性能或新版Application作用域迁移已通过。

最近一次代码状态：`8c5c9d1`提交了初始六阶段实现；其后的验收会话、退出策略和VBA语义修正仍在工作区，尚未提交。最新离线回归416通过；Managed已改用工程内Model.run启动，本例concaveL错误消失，单任务、连续两任务、快照新会话及Pillbox预处理正常路径已补测。真实故障和物理校准门禁仍待完成。

## 阶段结果

|阶段|交付与实测|尚未通过的门禁|
|---|---|---|
|M0 数值核心|已实现并通过离线数值安全网：加权复内积、MAC、一对一匹配、歧义拒绝、Gram白化/SVD；合成相位、尺度、旋转、缺失及解析dipole测试|真实Pillbox、阈值校准属于后续物理验收，合成测试不替代它们|
|M1 同语义效率|公共点与非均匀权重下两路线数值一致，误差低于1e-6；本次样本HDF5路线更快。串行资源最终报告已通过|分路线资源峰值、跨快照总成本、冷缓存和重复性未验收，不宣称全局最优|
|M2 工件|运行时E/H公共点HDF5导出，原子发布、摘要、单位/坐标/点数检查；24个跨网格工件可读|几何材料掩码未独立验证|
|M3 跨网格|cell=30/36，在12³、24³、48³共同ROI采样比较，E匹配稳定|全域求积、真实Pillbox及更多网格/模族校准|
|M4 模组|E/H双模子空间均稳定；H单模差值不足时明确未确认，而非强行分配|阈值仍为试验策略，未作为自动物理身份门禁|
|M5 接入与恢复|最新Worker单/连续两任务、7项标量与3项场工件分离、越界隔离及分析恢复通过；StopAck/退出/源保护通过；本例batch/表达式错误消除，快照新会话及Pillbox预处理通过|真实Start返回0、缺网格及其他故障回归未完成；非2022版本及任意多工程scope须验证|

最新离线回归：`python -m pytest -q --basetemp .pytest_cache/concave-fix-final`，**416 passed，19 deselected，8.65秒**。原六阶段回归为391通过；后续增加验收会话、生命周期、资源报告和文档契约测试。被排除的是集成测试，不表示其失败；真实CST证据按下方独立记录，不与离线通过数合并。

## 接口与使用

- `csttool/mode_matching.py`：纯NumPy数值计算。场数组为 `(points, 3, modes)`；加权矩阵经过尺度归一化，仅用于匹配，不是物理储能。
- `csttool/field_artifacts.py`：`SamplingSpec`定义SI单位矩形域中心采样；按需加载h5py，校验工件后读取。
- `postprocess_cst.py`注册 `ExportModeField`；实际宏为 `data/postprocess/ExportModeField.vb`。具体参数配置参见 `test/support/validate_managed_field_diagnostic.py`，包括模式、E/H、采样点数及SI边界。
- 安装可选依赖：`python -m pip install ".[field-analysis]"`。
- Manager可选参数 `field_reference_result`、`field_match_policy`，对应WorkerConfig同名字段；策略必须显式提供。默认不启用。
- `SimulationResult.FieldArtifacts`与`PostProcessResult`分开，`FieldDiagnostic`记录诊断。诊断在任务Ack及归档后执行；失败不会回滚已经成功的求解。
- `saved_field_export.py`用于已有场结果：CST带结果另存，再导出，不改参数、不Rebuild、不调用Solver。当前保留Project加载入口，宏正常返回，由批执行器退出；Python确认退出与产物。最新保存场导出包装器需补真实回归，效率宏对照通过不等于该包装器全路径通过。不能仅复制.cst便假定已有E/H场可用。

## 真实证据与结论边界

证据目录均在工作区 `artifacts/`，默认不进入源码发布包：

- `field-efficiency-a96127bc/report.json`：串行公共点对照，原生小矩阵与Python结果一致，标准退出且原工程未变化。Result3D.SetArray需要明确的Double数组；Variant数组曾失败。计时包含采样/权重转换和HDF5准备读取，不只比较点积算子。
- `cross-mesh-fields-b8ab3d42/report.json`：24个工件。E单模对应发生1↔2交换，MAC约0.999995以上；双模子空间最小平方奇异值约0.999979。H单模差值约0.036，低于试验要求0.05，因此未确认；组级值约0.99978。
- `managed-field-diagnostic-337eb346/report.json`：初始六阶段接口真实验收，早于最新VBA语义修正。两个有效场、一个故意无效域；求解成功，初始诊断incomplete，剔除无效工件后的分析恢复complete，`recovery_solver_replayed=False`；StopAck及标准退出通过，源文件摘要不变。

所有匹配报告保持 `physical_identity_confirmed=False`、`policy_calibrated=False`。ROI稳定只能证明该采样指标稳定，不能证明完整场身份，更不能证明R/Q方向或位置无关。

## 发现的问题与防护

1. CST2022指定点HDF5导出的坐标仍为工程单位，即使设置导出米单位。读取曾被严格坐标检查拒绝；现显式记录原始单位及比例，转换为SI再比较。
2. `GetListItem=True`不等于点位于有效场支持域；越界点可能返回全零。现增加CalculationBox边界检查及全零拒绝。材料掩码仍需后续独立验证。
3. 场导出失败必须是可选诊断失败，不能污染标量结果或触发求解重放；工件状态、任务/会话身份和原子发布负责防护。
4. 资源补测 `field-efficiency-ce4e7d62`曾与求解重叠，只作后台负载记录，不用于排名。随后串行补测 `field-efficiency-c195c01e`遇到LoadProject的`bad function call`及批任务关闭提示，未产生有效计时，也不用于排名。标准Quit调用返回不等于进程退出。此前沙箱内未发现进程被误判为已退出；提升权限重跑发现PID14052、16936仍存在，启动门禁已阻止新增CST实例，未强制结束。

### 问题4修正

两个独立场验收入口现共用 `acceptance_session.py`：操作系统锁覆盖整个验收，拒绝已有CST/Modeler/Solver进程；记录PID及创建时间、宏阶段、所属子进程和外部竞争进程。宏记录加载、另存及导出/采样阶段，Python写入 `session-status.json`。

后处理探针连续180秒无文件进展，或终态标记后60秒仍未退出，会明确报错并保留CST供诊断，不强杀、不盲目调用全局COM Quit。这些是后处理探针的空闲/退出期限，不影响正常求解的无限等待。存在竞争进程的记录不进入有效性能验收。

初次对应离线测试36项通过，真实重跑被已有进程门禁正确拒绝。随后进行了以下对照；最近一次提升权限只读检查未发现CST主进程或Modeler残留，但仍不能宣称异常收尾已通过。

### 加载/退出受控对照（后续修正）

残留进程消失后串行执行同一源工程、相同公共点导出：

|入口及退出|证据|结论|
|---|---|---|
|旧Project.OpenFile＋宏内Quit（历史成功）|a96127bc：约50.15秒，完成且退出0，但出现批任务关闭sheet错误|Quit在宏执行期间引发关闭冲突提示，不必然阻止最终退出|
|旧Project.OpenFile＋宏正常返回|f1e556b5：49.75秒，完成/数值一致/源不变/所属进程全退出，无关闭sheet错误|正式后处理探针采用此路径|
|Application.OpenFile＋宏正常返回|f23021ea：37.57秒，加载及另存后报missing field；失败标记存在，完成标记缺失；所属进程全退出、源不变|加载返回工程与原宏隐式Project上下文不一致；不能只替换OpenFile调用。退出0仍判Incomplete|

新版入口现已禁用，选择application会明确报错，不再执行混合作用域代码。后续必须将场读取、SaveAs、结果选择全部绑定到返回Project，或验证在目标工程中执行宏的接口，再重新验收。当前不是证明旧入口导致历史LoadProject异常，也没有复现其bad function call。

后续`field-efficiency-15d1e833`尝试Application打开工程后用`project.RunMacro(绝对.bas路径)`分发宏，报Macro not found，并在60秒退出阶段内未确认关闭；替代方案已撤销，未用于生产。该记录不参与性能排名。交接检查未发现主进程残留，不会追认其为成功。详见[VBA文档语义审计](cst-vba-document-semantics-audit.md)。

宏失败分支不再盲目Save/Quit，避免加载失败时保存源工程或关闭仍执行的batch。正式保存场导出宏正常返回，由CST批执行器完成关闭；Python仍检查完成标记、工件、源摘要与所有所属进程。资源状态不再只由退出码决定。首个对照资源记录曾过早finish为Incomplete，其数值/生命周期证据有效，但不将该资源状态作为正式成功统计。

中间回归出现目录重命名权限错误，单项复查通过；最新完整回归已达到403通过。上述真实对照均无强制进程清理。

## 最新P0验收补测

- `managed-field-diagnostic-fac752c5/report.json`：最新VBA求解2个模式成功；7项标量、2个可用场及1个故意无效工件，诊断失败不污染求解结果，分析恢复complete且不重跑Solver。StopAck、退出0、源不变通过。**收尾日志仍有batch关闭sheet错误及EvaluateInternal CDbl(concaveL)错误**；lifecycle证明Save返回、Quit调用前后均有记录，不能把退出0当成无错误生命周期。此次单任务验证不替代连续任务、真实Start返回0或缺网格故障测试。
- `field-efficiency-832ec2b5/report.json`：统一所有分支最终资源收尾后，任务/资源状态均Success；47.09秒，源不变，所属进程全退出，无其他CST竞争。76个资源样本、0采样错误，峰值私有内存2159280128字节，RSS1297174528字节；这是两条路线共享会话的峰值，不是每条路线独立峰值。9组数值误差最高2.45e-9；110592点原生路线约1.74–1.78秒，HDF5端到端约0.84–0.88秒。仍仅是当前工程ROI对照，不是跨快照/冷缓存全局性能证明。日志末尾另有The handle is invalid文本，未定位，保留原日志不宣称完全无警告。
- `cross-mesh-fields-4a14f7cc/report.json`：最新saved_field_export包装器串行导出cell30/36，共24个E/H工件均available；34.64/37.37秒，源不变、退出0、所属进程退出确认。六份诊断均complete；E单模交换匹配，H仍因差值不足未确认，组级稳定，与历史结果一致。physical_gate_passed仍False。
- 中间`field-efficiency-3e699821`数值/退出通过，但运行时仍有提前返回绕过资源finish的漏洞，不作为最终资源状态证据；现已统一publish_report并补6项测试。保存场包装器也新增4项测试，失败/不可用工件不判complete，退出异常仍写失败报告。

所有真实运行严格串行，无强制清理；最终提升权限只读检查未发现CST主进程/Modeler/Solver残留。

## 仍需实现与验证

### 收尾修正与剩余表达式错误（历史对照）

Managed收尾现采用Save→StopAck→返回Main，由命令行批执行器关闭，不再在活跃batch内Quit。`managed-field-diagnostic-b9a5f9c8/report.json`实测：求解/诊断恢复/StopAck/退出0/源不变通过，batch关闭sheet错误消失；但`Expecting an existing scalar var / EvaluateInternal CDbl(concaveL)`仍存在，新增shutdown_clean门禁正确判失败。没有掩盖或扁平化参数表达式。

无求解副本拆分探针：`parameter-shutdown-702e569f/report.json`中仅Save、仅StoreParameter后Save不出现标量错误；加入完整Rebuild后出现。`parameter-shutdown-aaeb4803`的RebuildOnParametricChange也复现；`parameter-shutdown-88dbd4e4`额外声明/求值相关宏变量同样复现。这两种猜测均未推广到生产。因此剩余错误可在求解前的模型重建路径复现，不能继续归因于Quit、Ack或未执行Solver。

工程Model/Parameters.json保留concaveL=(Leq-Gap)/2和值55、concaveR=concaveL和值55；DS的Model.dss也包含这些参数/表达式，这是进一步核查3D/DS参数同步的线索，不是已证明的根因。后续需定位重建调用期间具体的CST内部求值上下文或模型历史块，不能因缓存值正常就证明重建完全可靠。

最新离线回归413通过、19排除、9.39秒。全部对照未强杀，提升权限最终检查无CST主进程/Modeler/Solver残留。下一优先级为表达式重建错误及真实失败门禁，不宣称所有收尾问题已解决。

### concaveL作用域问题已修正（最新）

详见[作用域修正与验收](concave-expression-scope-rebuild-fix.md)。生产Managed和预处理使用`-m -b project.cst`，在已加载工程的Model/3D/Model.run中运行，不再在空工程宏内OpenFile；参数数值使用RestoreDoubleParameter，保持表达式。

`managed-field-diagnostic-86734df8`单任务和`managed-field-diagnostic-bf102301`同一Worker连续两任务真实求解/后处理恢复/StopAck/退出0/源不变通过，shutdown_errors为空。`parameter-shutdown-97c129de`中Gap 150→140→150，两级参数55→60→55，表达式未改变；含旧Model.run的快照在`project-script-resume-a8d4b0ac`新会话ready/新脚本/StopAck/退出均通过。Pillbox预处理集成1通过（20.48秒）。最终离线416通过、19排除（8.65秒）。本例错误已消除，其他故障与多版本门禁不能据此全部关闭。

“待验证”不等于代码缺失；“后续扩展”也不是本次最小诊断必须补齐的功能。

|优先级/阶段|类型|具体工作及通过条件|
|---|---|---|
|P0 / M5|部分故障通过，其余待验证|本例batch/表达式错误已修正；单/连续两任务、快照新会话及Pillbox预处理通过；缺失模式及[重建/求解器拒绝后的同Worker恢复](cst-history-persistence-and-solver-failure.md)真实通过；Start返回1却无结果的新门禁通过，返回0/Start异常及缺场/缺网格仍待验收|
|P0 / M1–M2|部分故障通过，其余待验证|独立效率及saved_field_export正常路径通过；[真实缺结果目录导出及四类HDF5工件损坏恢复](field-failure-recovery-acceptance.md)通过，无求解重放。加载失败/退出卡住、部分原生场或网格缺失仍待对照；分路线峰值与性能重复性未验收|
|P0 / 生命周期|P0-1 pending已完成，其他故障待验收|[坏重建直接停止](failed-rebuild-stop-recovery.md)正常恢复及恢复重建、快照/回执写入失败均真实通过；失败不发布StopAck、不重放Solver，已死故障会话abandoned-dead收口。继续验证父进程先退出、任意历史破坏及其他实例归属故障|
|P1 / M2–M3|核心及双网格基准通过，复杂域待验证|[共同域/原生材料掩码/体积权重](physical-domain-pillbox-acceptance.md)已实现，理想圆柱48³/64³/96³全域采样与cell20/30全域对照通过；多材料复杂CAD、背景支持仍待验收，默认Worker尚未自动生成掩码|
|P1 / M3–M4|解析、真实双模与第二mesh通过|理想闭合PEC Pillbox TM110全域跨网格最小平方子空间重叠0.999998879；对真实场数组交换编号不变，本轮未自然交换编号。三层mesh/其他模族与阈值校准仍待验证，不用单线R/Q判身份|
|P1 / 固定参考第一版|Python入口已实现，真实新接口待验收|[封闭PEC/真空腔追踪](vacuum-mode-tracking-v1.md)支持单模/显式模组候选选择、未确认及不回放Solver的序列恢复；不改变默认扫描/Worker/GUI，不自动更新参考或合并HOM|
|P1 / M4|待验证|更多模族、缺失成员、不同维数/病态Gram、频率接近但场不同的真实样本；校准MAC、差值和子空间阈值，误报/漏报明确记录；当前秩不符按未确认处理，不自动补成员|
|P1 / M1|待验证|两工程参考场准备/加载/切换、采样/转换、读盘/算子/写报告的全流程时间与资源；冷/热缓存、交换路线顺序、重复运行。资源补测修复前不能仅凭局部算子选“最优路线”|
|P2 / Application迁移|待实现＋验证|确定有文档/实测依据的目标Project调用方式；验证工程身份、结果树、保存目标与多版本实例归属。迁移不是继续修改全局OpenFile的一行，也不作为当前ROI诊断使用的前置条件|
|P2 / 使用入口|可选扩展|GUI参考场选择、采样域/策略配置、诊断展示及配置持久化。目前只有Manager/Worker API，不宣称GUI端到端可用|
|后续 / 自动接收|另行设计审批|上述物理校准完成后决定是否接入扫描接收。当前始终physical_identity_confirmed=False，不自动删/并模式或跳过区间|

建议顺序：先最新VBA真实回归与安全生命周期，再完成可复现的资源报告；随后做全域支持、真实极化模组和阈值校准。Application迁移与GUI为独立后续任务，不应反复阻塞已可用的Project/ROI诊断路径。
