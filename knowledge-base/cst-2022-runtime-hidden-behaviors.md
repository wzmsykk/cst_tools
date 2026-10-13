# CST2022运行时隐含行为与排障知识

记录日期：2026-10-13。范围：本项目使用的CST2022.5、指定测试工程和执行路线。本文汇总此次场匹配、参数重建与退出对照中取得的新信息，不是CST全部版本的行为规范。

“未见文档承诺”表示已查阅的安装版帮助未说明或未保证该行为，不代表已证明所有公开/私有文档都没有记载。文档契约、实测现象和原因推测必须分开；失败实验也是知识，不能作为可用接口推广。

## 1. 快速定位

|问题或现象|本轮新信息|当前防护|
|---|---|---|
|重建时报concaveL标量转换错误|空工程编译宏后OpenFile，与先加载工程再执行脚本并不等价|Managed及预处理采用`-m -b project.cst`和工程内Model.run|
|依赖参数读取滞后一轮|本例Evaluate返回旧的依赖值，RestoreDoubleParameter返回更新后的工程参数值|参数数值读取与表达式求值分开；不固定化表达式|
|算完但无法关闭|活跃批宏内关闭可能触发“Unable to close sheet while a batch job is running”|保存、发布StopAck、返回批执行器，再验证进程退出|
|退出0但没有结果|错误调用、缺少完成标记也可能最终退出0|检查返回值、完成标记、预期产物和实际退出|
|无窗口|后台CST仍可能存在；受限进程查询也可能看不到它|核实PID、创建时间和子进程，不凭窗口判断|
|导出场坐标差1000倍|指定点HDF5路线的米制开关未产生预期坐标单位|显式记录原始单位/比例并校验真实坐标|
|场读取成功但全零|GetListItem成功不证明采样点在场支持域内|计算盒范围检查、全零场拒绝；材料掩码仍待验证|
|COM方法看似存在却不可调用|pywin32动态绑定不能等同于VBA对象语义|失败适配不接入生产；按版本核对接口|

## 2. 工程上下文会影响宏编译和重建

文档说明当前工程参数自动暴露为脚本Double变量，但未承诺：脚本编译后再打开另一个工程，会自动重绑定这些变量。Application、3D Project、DS Project以及simulation project参数集合也不是一个统一命名空间。

本例受控对照：

- `-m probe.bas`先进入空工程，宏内OpenFile，更新参数并完整Rebuild：内部`EvaluateInternal CDbl(concaveL)`出现错误。
- 同一源工程副本、相同表达式与更新，改用`-m -b input.cst`执行`input/Model/3D/Model.run`：完成标记、正常退出及表达式检查通过。
- 实时枚举显示3D与DS均存在concaveL、concaveR及其依赖，数值也一致；枚举顺序不同不是“DS缺参”的证据。

证据：`artifacts/parameter-shutdown-702e569f`、`parameter-shutdown-5a34d2cd`、`parameter-shutdown-5169b2df`。可复现的启动上下文差异已证明；CST内部编译器/参数同步的具体根因未逆向证明。不能据此认定OpenFile在所有场景都错误。

## 3. Evaluate不等于读取当前参数值

保留表达式`concaveL=(Leq-Gap)/2`、`concaveR=concaveL`，把Gap从150改140再恢复150，重建后读取：

|阶段|期望L/R|Evaluate路线实测L/R|RestoreDoubleParameter路线实测L/R|
|---|---|---|---|
|初始|55/55|55/55|55/55|
|Gap=140|60/60|60/55|60/60|
|恢复Gap=150|55/55|55/60|55/55|

证据：`artifacts/parameter-shutdown-569330ae/project-script-dependent/linked.tsv`及`parameter-shutdown-97c129de/project-script-dependent/linked.tsv`。

实测结论是本路线中Evaluate依赖值滞后；宏变量缓存/作用域是解释方向，不应写成已证明的内部实现。文档定义的字符串表达式求值不能替代工程参数数值读取。当前使用RestoreDoubleParameter，表达式用RestoreParameterExpression保留；nmodes另做正整数与范围校验。不将表达式改成固定数字。

## 4. 批执行、退出与成功是不同事件

关闭工程或Application.Quit并非无条件安全的批宏尾声。本轮存在关闭冲突、Quit调用返回但进程仍在、最终退出0却缺失功能产物等情况。没有求解也可能触发重建表达式错误，不能归因于“尚未运行Solver”。

当前Managed路线是Save→StopAck→返回Main/批执行器；Python独立验证StopAck和真实退出。不能把Ack理解为进程已经关闭，也不能把进程退出理解为求解/后处理已成功。`EigenmodeSolver.Start`返回0必须发布失败，不能继续当成成功读取结果。

证据：`artifacts/managed-field-diagnostic-86734df8/report.json`及`managed-field-diagnostic-bf102301/report.json`。后者同一Worker连续两任务通过，StopAck、退出0、源工程未变；仍不是所有异常退出路线的证明。

清理仅针对核实身份的自有实例，采用标准退出；不把结束进程作为常规修复。无窗口时先检查后台进程。受限环境“未找到进程”不足以证明退出，需可靠权限下复核。

## 5. Model.run与工程快照

运行生成的Model.run可以进入保存后的.cst。恢复时需写入新会话脚本，防止旧会话协议被重新执行。

`artifacts/project-script-resume-a8d4b0ac/report.json`使用带旧脚本的求解快照启动新Managed会话：新脚本与生成bas一致，新会话Ready/StopAck及正常退出通过，没有观察到旧会话重放。此证据只覆盖该快照，不建立.cst内部脚本与外部sidecar的通用优先级、时间戳选择规则。

只复制.cst适合重新求解；复用已计算E/H结果还需要对应同名结果目录。此前仅复制.cst后找不到场，不代表导出接口不支持该场。

## 6. 场导出与积分的隐藏边界

### 坐标单位及支持域

安装帮助描述ExportCoordinatesInMeter为米制输出，但本例CST2022指定点HDF5仍输出工程mm坐标。严格坐标校验发现1000倍差异。当前显式使用False，并保存原始单位、转换比例和实际采样坐标，不能只相信开关名称。其他版本、其他导出模式须另测。

VectorPlot3D.GetListItem=True仅表示取值调用成功。本例盒外100–101m ROI得到True及零E场，不能据此确认有效支持域。增加计算盒检查和全零拒绝，但尚未独立验证复杂材料/空洞掩码。

### 数组、采样与算子语义

- ASCIIExport.SetPoints在已复制2022帮助中未找到定义，本次运行验证可用；属于版本受限的实测接口。FixedWidth不能仅按名字理解为任意点列表模式，需回读导出坐标确认。
- Result3D.SetArray在本例Variant数组失败，typed Double数组成功；数组准备/转换用时需计入端到端性能。
- 原始索引求和不是物理体积积分。不同网格必须统一采样点与权重，复场重叠包含共轭，不能以“调用成功”代替数学等价。
- ROI上的高MAC、双模子空间稳定，不等于全域物理身份已确认。同一偏轴积分线R/Q受极化方向影响，不能作为简并模式身份的不变量。

相关实现与证据：`docs/postprocess-operator-execution-plan.md`、`artifacts/field-efficiency-832ec2b5`、`artifacts/cross-mesh-fields-4a14f7cc/report.json`。

## 7. 不应继续尝试的错误接口假设

|尝试|实际结果|形成的边界|
|---|---|---|
|换成RebuildOnParametricChange|仍有标量错误|改变重建方法不是本例作用域修复|
|手工声明/Evaluate同名变量|仍有标量错误|不能靠制造宏变量补工程作用域|
|活跃3D批宏内全量DS.StoreParameters|关闭冲突；最终0xC0000005|不采用跨scope全量覆盖；崩溃具体内部根因未证明|
|`--project-file input.cst probe.bas`双文件通道|退出4、无完成标记|不能猜测命令行加载/执行组合|
|只替换Application.OpenFile|后续未限定SaveAs/SelectTree仍落在错误上下文|单个调用替换不是完整作用域迁移|
|Project.RunMacro传任意绝对bas路径|Macro not found|宏名称契约不等同于文件执行契约|
|pywin32 SaveAs / 强制Method标记 / PROPERTYGET|分别出现int不可调用、MEMBERNOTFOUND、BADPARAMCOUNT|动态绑定未经证明，不形成通用适配器|

证据目录：`parameter-shutdown-aaeb4803`、`88dbd4e4`、`b150ff21`、`9e4e6a2b`；`field-efficiency-f23021ea`、`15d1e833`；`external-parameter-scope-0df0d7bf`、`3745cbb4`、`af12ab52`（均位于artifacts）。危险DS同步和未证明的COM路线已从公开测试入口/候选实现撤下。

CST2022官方Python包限制Python3.6–3.9，当前Python3.12不能直接使用；安装内置解释器实测为3.6.0。2022文档中的Modeler包含add_to_history/full_history_rebuild/solvercontrol，不能套用其他版本的run_vba_code。Schematic.execute_vba_code存在，不代表其具有3D作用域。原生Python重建探针仅证明本次返回、保存及退出，未捕获内部引擎日志，不足以宣称所有内部错误消失。

## 8. 测量与诊断流程自身的坑

- 有其他CST求解并行时，资源争用会污染性能排名；现在验收使用单实例租约并记录竞争进程。
- 报告提前return会漏掉资源采集收尾；已统一报告发布出口，最终状态必须在退出后确认。
- 整个会话的峰值内存不是某条算子路线独占峰值，不能据此比较两条路线内存。
- `field-efficiency-832ec2b5`的110592点样本：native约1.74–1.78s，HDF5全流程约0.84–0.88s，最大归一化误差约2.45e-9；只证明该ROI/样本下的结果，不外推全域大场、冷缓存或所有算子。
- 日志尾部“The handle is invalid.”尚未定位；退出0和完整产物不等于零警告。
- `project-script-dependent`早期辅助宏曾退出0且有batch日志，但无完成标记；未通过验收，不能归入成功样本。
- 按原始字符串统计Solver.Start会把错误消息中的名字也算进去，架构守卫已改成调用行边界。
- 测试归档rename的瞬时WinError5与CST物理/协议错误应分开；一次权限环境重跑成功不能证明该环境问题永不复发。

## 9. 证据保存与后续门禁

原工程SHA256：`54eb65fca4c6f5e94d5ccfc3055bf139e48f7123456f5cf0a1de206efc1651e5`。所有工程修改在副本进行。最近代码回归416通过、19 deselected；仅说明已运行的离线范围，不能覆盖真实CST故障与物理正确性。

上述artifacts是本地验收数据，可能未纳入Git。本文和[作用域修正记录](../docs/concave-expression-scope-rebuild-fix.md)保留可检索摘要；迁移机器/清理大场文件前应保留报告、宏、日志、哈希及坐标/单位元数据，不必把大型模型和HDF5全量提交仓库。

仍待验证：

1. 不同CST版本、任意多工程/DS/simulation scope及One-shot/Warm旧启动路线。
2. 真实Start返回0、缺场、批执行异常和退出异常的完整恢复门禁。缺失模式必需后处理失败及同Worker恢复已单独通过，不能替代这些故障。
3. 全域材料支持掩码、跨快照模式匹配、极化/简并样本的物理校准。
4. 冷缓存端到端耗时与路线独立资源峰值；未定位日志警告、无标记辅助宏。
5. Model.run归档/sidecar选择规则的独立对照，避免把单次恢复成功当成格式规范。

每个新结论至少记录：版本、源哈希、启动命令、scope、唯一变化项、完成/失败标记、预期产物、PID身份与退出证据；猜测单列，未完成不写成功，不用无限重试掩盖协议或作用域问题。

## 10. 后续验证：缺失模式后处理可恢复

`artifacts/missing-mode-recovery-d84eee5f/report.json`实测nmodes=1但请求Mode 2，明确Failure/Missing eigenmode #2，无后处理值与成功快照。Ack后同一session提交nmodes=2任务成功，频率570.135507219754MHz；StopAck、退出0、源不变及最终无进程残留通过。详见[验收记录](../docs/missing-mode-recovery-acceptance.md)。它证明该异常后的协议恢复，不证明所有VBA错误均可恢复。

首次新探针直接JSON序列化SimulationResult失败，导致第二轮未执行；改为dict后重跑。该问题属于验收工具而非CST隐含行为，失败数据保留，未把半轮结果算完整通过。

## 11. 历史覆盖与Start返回值的新反例

2026-10-14全域基准补测：Solid.IsPointInsideShape与GetMaterialNameForShape可独立构造几何/材料掩码；理想PEC Pillbox的48³/64³/96³结果与解析圆柱逐点一致。体积切边仍有单元中心误差（16³约3.45%，96³约0.0861%），不能把二元掩码等同于精确切边体积。TM110双模全域子空间与解析基最小平方重叠约0.999999，基准通过不等于任意HOM阈值已校准。验收进程监测也出现晚发现子进程的竞争误报，已按祖先关系与PID+创建时间消除自己实例的旧记录，外来实例仍拒绝。详见[全域与双模验收](../docs/physical-domain-pillbox-acceptance.md)。

2026-10-14保存场故障补测：`field-failure-recovery-21dbe3e6`仅复制.cst不带同名结果目录，导出真实报mode field missing；完成标记与退出0不能覆盖unavailable工件，整体仍incomplete。真实导出HDF5副本缺文件、哈希变化、缺数据集及坐标错误全部拒绝，利用完好工件备份可只恢复Python分析，无Solver重放；不能从不存在的原生场凭空恢复。详见[场故障验收](../docs/field-failure-recovery-acceptance.md)。

详见[历史持久性与真实失败对照](../docs/cst-history-persistence-and-solver-failure.md)。`history-persistence-18ad6d40`实测：直接Boundary.Xmax=open在完整Rebuild后变回electric；AddToHistory后在完整重建、部分/完整参数更新都保持open。Gap值、concaveL表达式、新建项目参数与Global Data保留。因此边界/设置的历史化与参数表更新应分开；Global Data不自动失效结果，不应用于规避更新。

`solver-failure-recovery-4d229e05`实测Default/Tet+open被求解日志明确拒绝，但Start返回1，随后查询报无Eigenmode数据库；同Worker恢复原边界后求解及标准退出成功。此版本/路线存在Start返回值与文档成功契约不一致的反例，不能仅凭返回1发布成功。Managed新增solver-result模式可用性检查；少于请求数不判失败，零可用模式或查询异常明确失败。最新历史化门禁证据见上述验收记录。

`solver-failure-recovery-5c962473`的nmodes=0在历史重建阶段失败，不是Start失败。坏状态下立即停止发生保存拒绝、退出4，进程实际退出但标准关闭未通过；源未变，不将其追认为成功。仍需设计坏历史停止时的已知良好快照/恢复策略。

### P0-1后续修正

2026-10-14补测：`recovery-faults-771c8a0a`验证恢复Rebuild返回False及恢复快照/保存回执真实写入受阻，均不发布StopAck，标准批退出4后仅按确已死亡的隔离会话abandoned-dead收口。Backup输出受阻实测10051 Could not open file，成功Save也不能替代回执/停止确认。新增快照非空检查，损坏/非ASCII回执拒绝确认；正常路径9bde6833重跑通过。见[P0-1故障验收](../docs/failed-rebuild-stop-recovery.md)。这些是恢复失败门禁证据，不是所有故障可自动恢复的保证。

原失败记录不追认成功。新增参数表达式检查点和停止恢复后，`failed-rebuild-stop-ae5729af`重建/保存已返回且无保存拒绝，CST仍退出4；说明非零码可能继续携带任务失败，不能与等待UI的未关闭状态等同。

`failed-rebuild-stop-b417feb1`基线恢复及`failed-rebuild-stop-0ea47a64`成功后失败恢复已通过：本会话恢复快照/保存回执、StopAck和实际退出核对，任务Failure保留；无Solver重放，原成功快照及源SHA未变，无主实例/求解残留。只允许这种有证据的特定退出4停止确认；没有通用忽略非零码。参数恢复不回滚任意历史/Global Data。详见[P0-1验收](../docs/failed-rebuild-stop-recovery.md)。

2026-10-14全域双网格实测：理想Pillbox cell20/30实际四面体数83151/283098（Mesh.GetNumberOfMeshCells，文档明确支持四面体），频率相对变化2.599e-7、双模子空间最小平方重叠0.999998879，但单模MAC约0.903。这是数值极化基混合的实测，不是自然编号交换的证据。原生日志求解总时61/450秒；不能以频率接近替代场身份，也不能以加密参数替代实际网格库存。见[第二网格验收](../docs/physical-domain-pillbox-acceptance.md)。

2026-10-14自动工程域预检：CST2022.5的Material.GetTypeOfBackgroundMaterial返回PEC/Normal；背景setter在Background对象，但getter在Material对象，不应按命名猜测。Solid.GetLooseBoundingBoxOfShape文档限制后处理时使用，本轮独立控制宏加载已保存副本查询成功，圆柱返回SI范围±0.229m、±0.1295m；不在历史重建中调用。Boundary.GetXSymmetry等返回none，Port.StartPortNumberIteration返回0。Normal背景加Xmin=open副本原生查询成功、正常退出0，但Python预检明确rejected；进程成功不代表工程满足算法前提。见[自动登记](../docs/vacuum-domain-registration.md)。
