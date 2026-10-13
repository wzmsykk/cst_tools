# concaveL重建求值错误：作用域修正与验收

跨问题的新发现、隐含行为和失败路线汇总见[运行时知识库](../knowledge-base/cst-2022-runtime-hidden-behaviors.md)。

日期：2026-10-13。CST2022.5（2022-06-03）。源工程只读，所有更改及求解在副本进行。

## 结论

本例可复现的触发条件是：通过`-m worker.bas`在空工程上下文启动/编译宏，随后在宏内OpenFile，再Rebuild。CST内部生成的`EvaluateInternal CDbl(concaveL)`无法取得期望的标量上下文。用官方`-m -b project.cst`在工程已加载后执行`Model/3D/Model.run`，相同更新、完整重建和求解不再产生该错误。

这是启动/解释器上下文的受控对照结论，不表示已逆向证明CST内部所有3D/DS同步实现，也不表示OpenFile在任何位置都不适用。

原表达式保持：`concaveL=(Leq-Gap)/2`、`concaveR=concaveL`。没有扁平化表达式，没有删除/重建DS参数或修改DS私有二进制。

## 文档依据与作用域

- `Online Help/vba/vba_macro_language_overview.htm`：当前工程的参数自动作为Double变量暴露给脚本；这不保证打开另一个工程后，已编译脚本的原作用域重新绑定。
- `Online Help/advanced/commandlineoptions.htm`及安装版`CST DESIGN ENVIRONMENT.exe --help`：`-b`执行所选工程`Model/3D/Model.run`。不能把`--project-file`与另一个位置文件名当作独立“加载工程＋执行宏”通道，双文件尝试退出4。
- `VBA_3D/common_vbaapp/common_vbaappapplication_object.htm`：页面实际为Project Object。RestoreDoubleParameter读取指定参数数值；RestoreParameterExpression读取表达式；Evaluate计算字符串表达式，不是“递归刷新全部参数依赖”的承诺。
- `mergedProjects/VBA_DES/special_vbaobjects/cstdesignstudiovbaobjects.htm`及`special_vbacommands/projectobject.htm`：DS内的隐式Project方法属于DS作用域。Application的Active3D/ActiveDS、返回Project和宏隐式对象不能混为一体。
- `mergedProjects/DES/general/usingparameters.htm`：simulation project有独立参数集合，通过Master Name/Link Geometry控制链接，不能看到同名就认为各scope自动相同；这与同一工程的3D/DS对象区别也不能混淆。

实时scope探针`parameter-shutdown-5a34d2cd`读取到3D和DS都具有上述表达式与数值55，只是枚举顺序不同。未找到“DS缺参”的证据，也不能把顺序不同直接当成根因。没有因此向全部DS scope强制覆盖参数。

## 修正

1. Managed Worker先复制.cst；生成诊断用bas及内容一致的`worker-input/Model/3D/Model.run`；使用`-m -b worker-input.cst`启动。Main不再OpenFile。
2. 预处理同样在工作副本的Model.run运行，不再空工程宏内OpenFile。
3. 读取模式数与频率参数使用RestoreDoubleParameter；正整数校验后传CInt。表达式仍存于工程、在历史重建时读取最新参数值。
4. Save→StopAck→返回批执行器；不在活跃批任务内Quit。Python仍检查真实退出，不把返回或退出码0单独当成功。
5. 预处理捕获到宏执行错误时，即使退出0也拒绝接收；真实Worker验收增加表达式/关闭错误门禁。

Managed的-b启动已实测CST2022，其他版本仍须分别验收。One-shot/Warm旧Gate模板仍保留其原启动方式，本次只统一它们的参数数值读取，未宣称作用域迁移也通过。

## 关键对照

|证据|观察|
|---|---|
|parameter-shutdown-702e569f|仅Save、仅参数更新无标量错误；加入Rebuild复现|
|parameter-shutdown-aaeb4803 / 88dbd4e4|增量重建、手动声明宏变量均不能解决；未推广|
|parameter-shutdown-5169b2df|-b工程内脚本：同样参数更新及完整Rebuild，完成标记/退出0/源不变/无标量错误|
|parameter-shutdown-569330ae|Evaluate(concaveR)在依赖变化后出现滞后，不能用它充当参数值读取接口|
|parameter-shutdown-97c129de|RestoreDoubleParameter：Gap 150→140→150，两级结果55→60→55，两个表达式完全保持；无标量/关闭错误|
|managed-field-diagnostic-86734df8|新启动方式单任务真实求解、场工件失败隔离、诊断恢复、StopAck/退出0通过，shutdown_clean=True|
|managed-field-diagnostic-bf102301|最新参数值读取＋新启动，同一Worker连续两个真实任务通过；各有7项标量、2有效场和1故意无效工件；分析恢复不额外求解；shutdown_clean=True|
|project-script-resume-a8d4b0ac|含旧Model.run的结果快照启动新会话，脚本与新bas一致、ready/新StopAck/退出0通过，无求解，不重放旧会话|
|Pillbox预处理集成测试|最新-b预处理：1 passed，20.48秒；输出参数/文件与原工程保护通过|

源码准备用的prepared.cst与修正前source-input.cst的SHA256仍完全一致：`54eb65fca4c6f5e94d5ccfc3055bf139e48f7123456f5cf0a1de206efc1651e5`。

## 被排除的路线与遗留门禁

- 在3D批宏内DS.StoreParameters尝试（b150ff21）发生关闭冲突并异常退出0xC0000005，未完成。该CLI选项已移除，没有加入生产；后台确认最终无残留，未强杀。
- 自写pywin32 Project分发遇到属性/方法及参数计数不一致；试验工具已移除。对两个明确自有的唯一实例调用标准Application.Quit并确认退出，没有结束其他进程。
- 官方cst.interface探针07e9a737在CST自带Python3.6中返回重建1并正常保存/关闭，但没有捕获完整宏错误日志，只作为原生控制对照，不替代本次批宏验收，也未引入生产依赖。
- 早期带DS辅助子程序的-b联动探针aca0ad27无完成标记，不能算通过。最终验收使用明确的3D参数读取；不据此宣称任意混合3D/DS宏都可直接迁移。

已解决本例错误及连续任务/新会话正常路径。跨CST版本、任意多工程参数映射、真实Start返回0/损坏场/缺网格等故障仍单独待验收；场匹配依然仅为ROI诊断，未校准全域物理身份。

最终离线回归416通过、19排除、8.65秒；额外定向复查遇到一次目录重命名WinError5，提升权限复查25项全通过（0.68秒），没有据此改动HOM归档逻辑。最终只读检查无CST主进程/Modeler/Schematic/求解任务进程残留，未强制清理。实现与文档尚未提交。
