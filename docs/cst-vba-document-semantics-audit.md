# CST2022 VBA调用语义审计

最新[历史持久性及真实失败对照](cst-history-persistence-and-solver-failure.md)发现Start返回1但求解器拒绝且无结果的CST2022反例；Managed新增solver-result门禁已真实通过。文档返回值契约不能单独作为成功证明。

日期：2026-10-13。基于安装版Online Help与仓库vendor帮助，不以函数名推断语义。本次覆盖三个Worker模板、HOM预处理、正式场导出、Simple/Complex核心入口及独立效率探针；并非全部ModeRec算法或每个积分公式的完整物理验证。

## 来源

- Application：`D:\Program Files (x86)\CST Studio Suite 2022\Online Help\advanced\vbaapplicationobject.htm`。
- Project：`knowledge-base/vendor/cst-2022-vba-help/VBA_3D/common_vbaapp/common_vbaappapplication_object.htm`，虽然文件名含application，页面标题实际为Project Object。
- EigenmodeSolver：`VBA_3D/special_vbasolver/special_vbasolver_eigenmodesolver_object.htm`。
- VectorPlot3D、ASCIIExport、Boundary、Units、Port：上述vendor目录对应对象帮助。

## 已修正

|调用/位置|文档定义及问题|修正|
|---|---|---|
|Application.OpenFile / 独立探针|官方示例返回Project；没有承诺重新绑定正在执行的宏。旧测试返回对象未用于SaveAs、SelectTreeItem|禁用该未经验证的测试入口；保留已验收Project入口，不再混用作用域|
|EigenmodeSolver.Start / 三个Worker|返回int，成功1、失败0；此前忽略返回值，可能继续读旧结果并发布成功|返回非1立即发布SOLVER_FAILED，不执行后处理/成功发布|
|SetNumberOfModes / Worker与预处理历史|参数文档为int，不是表达式字符串；此前传"nmodes"依赖隐式扩展|RestoreDoubleParameter读取实际参数数值，校验正整数及CInt范围，再传整数；历史内读取最新参数，保留变化后的绑定|
|SetFrequencyTarget、SetMeshAdaptationTet / 历史|bool/double，不应把"False"与表达式字符串当作契约|使用Boolean字面量及RestoreDoubleParameter读取频率参数|
|Rebuild / 预处理|返回bool；失败不能继续Save并写SUCCESS|检查False，明确失败|
|EigenResult_Complex缺场/缺网格|VBA Double函数提前退出会默认返回0，0不是“无结果”|抛明确错误，拒绝缺失模式、缺场、缺网格、非正频率；Simple也拒绝非正模式编号|

## 已确认的语义及边界

- Rebuild处理历史并删除所有结果；仅在求解前调用。后处理和已有场导出禁止Rebuild或参数更新。RebuildOnParametricChange也不保证保留全部结果。
- Backup复制工程与结果，不改变当前工程；不能用它推断当前工程已经Save。SaveAs可带结果且改变当前文件归属；只有.cst的文件系统复制不包含E/H。
- Project.Quit在结构改变时可能需要保存；Application.Quit退出应用。两者都不保证可以在batch尚执行时关闭sheet。探针与Managed采用宏正常返回，仍验证StopAck及进程退出；旧One-shot/Warm Gate不在本次退出迁移范围内。
- GetListItem的bool表示读取采样值，不表示空气域/材料域/物理支持证明。CalculationBox只是计算盒范围，不是材料掩码。现有范围/全零检查不能升级为全域积分验收。
- GetModeFrequencyInHz返回Hz；除以GetFrequencyUnitToSI得到工程频率。场工件保留Hz；不把两类输出混淆。
- Port.GetNextPortNumber是迭代已有端口，不是“下一个可创建端口”。现Simple已先StartPortNumberIteration，符合迭代前置条件；首端口截止检查不能证明所有端口均满足条件，外部Q仍依赖求解配置。
- ASCIIExport.Mode("FixedWidth")表示固定步宽，不等于指定点列表模式。SetPoints在现有复制帮助中未找到定义，是CST2022实测扩展，不能声称有该帮助的完整契约。坐标摘要/点数/坐标一致性验证仍必须保留。
- ExportCoordinatesInMeter文档说True导出米；现有指定点HDF5实测仍输出工程单位。生产明确False并记录原始单位比例，不假定名称保证单位。
- SetQuietMode只抑制消息框，要求用户输入的对话框不保证被抑制；不是安全退出机制。

## 作用域迁移门禁与本次失败证据

Application应属于实例/项目控制层，返回Project须用于所有后续工程操作。工程内宏可以使用隐式Project，但必须已在目标工程执行。GetObject全局获取活动实例不是多worker归属契约，不推广到生产。

受控试验15d1e833尝试`project.RunMacro(绝对.bas路径)`，实际报Macro not found。文档参数是macroname，不能凭“执行宏”措辞推断任意脚本路径。试验入口已撤销，没有加入正式导出。随后退出监测报告exit-unconfirmed并保留进程；无强杀，也不宣称迁移成功。该次失败说明仅补一个RunMacro同样不足以建立工程作用域。

后续若迁移，必须使用已明确的外部Project调用或经过验收的工程内宏分发接口；先验证工程身份、结果树、保存目标、两个连续任务和正常退出，再推广。当前修正是拒绝错误的Application路径并修复已证实的契约违例，不宣称Application后端迁移完成。

新增静态契约测试检查返回值、整数参数、Rebuild与缺失结果失败；它们不能证明CST加载、场计算或所有故障恢复。真实Worker求解回归待残留验收实例安全关闭后进行。

最终离线回归：403 passed，19 deselected，8.24秒。另修复P5.6生成器按原始字符串计数误将诊断消息算作第二次Solver调用的校验，改为调用行边界检查。

交接前提升权限只读检查未发现CST主进程或Modeler残留；这不改变该次对照“宏分发失败、规定退出阶段未确认”的结论。未进行强制清理。新版作用域路径仍未通过验收，真实求解回归尚未执行。

以上为早期审计状态。最新[concaveL作用域修正](concave-expression-scope-rebuild-fix.md)已验证官方-b工程内脚本路线并接入Managed/预处理；单/连续两任务、快照新会话、Pillbox预处理通过。Application直接替换及RunMacro任意路径仍不采用。还实测发现Evaluate读取长宏中依赖参数可能滞后，读取参数值应使用RestoreDoubleParameter/GetParameterNValue，不能把字符串求值等同于参数依赖刷新。最新离线416通过；跨版本/任意多工程和故障仍待验收。
