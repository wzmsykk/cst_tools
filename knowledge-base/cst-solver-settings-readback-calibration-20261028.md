# V01/V02/V04：求解设置数据库读回校准

## 结论及作用域

本机CST 2022.5 Release（2022-06-03，change 981760）可以通过官方`Project.GetDataBaseValue(key)`读取本征模执行配置，但实测这些字段属于**求解尝试生成的设置快照**，并非当前未计算工程的通用live getter。新工程求解前及Save后字段不存在；执行后出现；修改当前设置再Save仍可能返回旧值；Rebuild会清除这些字段。

因此本轮解决的是“核对某次执行采用的配置及识别陈旧证据”，没有找到可替代前置验证器的三个实时getter。不得为了读取设置在生产环境额外求解，也不得将旧快照作为新定义的发布凭证。

## 官方定义、静态发现与探针

官方Project帮助只定义GetDataBaseValue返回给定key对应字符串，没有公开本轮key清单。EigenmodeSolver帮助只有SetMethodType、SetFrequencyTarget、SetMeshAdaptationTet，没有找到对应三个查询方法；Solver/Modeler不能按名字推断为通用设置反射器。

只读安装`AMD64/modeler_AMD64.exe`发现`objdata\EigenmodeParameter`及SolverTypeTet、FrequencyTargetActive、FrequencyTargetValue、AdaptionActiveTet等字段字符串。进一步在该固定文件定位GetDataBaseValue调用链：RVA 0x29bc770→0x42f9180，分支识别反斜杠路径，按数据库类型格式化输出；0x4300120负责路径节点。静态片段只是候选来源和格式证据，不单独证明运行时适用性。文件SHA256、字段偏移/上下文和反汇编保存于`artifacts/solver-settings-readback-20261028`。

使用[calibrate_solver_readback.py](../test/support/calibrate_solver_readback.py)的`keys`/`render`/`render_staleness`/`main`，复用[现有会话门禁](../csttool/acceptance_session.py)和[设置探针run](../test/support/calibrate_cst_settings.py)。只测试22个有限候选（含不存在哨兵），没有遍历数据库或连接任意Active3D。短key及省略objdata前缀的候选均明确报Data item not found，只有下面完整路径在执行后可用。

|字段|完整key（前缀均为`objdata\EigenmodeParameter\`）|本版本实测映射|
|---|---|---|
|Tet方法|SolverTypeTet|1=Default；2=General (Lossy)，与原生Method日志交叉核对；其他枚举未校准|
|target开关|FrequencyTargetActive|True/False分别读取，不与target数值混同|
|target数值|FrequencyTargetValue|返回求值后数值字符串，不保留表达式；禁用时480仍可存储但不作为生效下界|
|Tet自适应开关|AdaptionActiveTet|True/False；True有实际Pass 2佐证，False有原生明确deactivated警告|
|网格分支辅助|MeshType|本轮Tet=1；未校准Hex枚举|
|请求模式数辅助|Modes|本轮为1；本字段是执行快照，不能替代已校准AKSGetNumberOfModes的当前请求数查询|

上述key是**版本限定实测**，不是官方稳定key契约。不存在、错误或未知枚举必须保持unknown/unverified，不能默认为Default、0或False。

## 副本和计算条件

源`model/Pillbox.cst`只读，SHA256 `f3a4673772d576730373a6310b5a10f7ab5ba79dad9014c2540ddb8ab0de1133`。全部设置写入副本历史，原参数表名称/表达式前后逐项一致。源频段400–1200MHz、nmodes=1；保持参数表达式。小网格用已校准Version=1、near/far=4/4、几何2/1、2个求解线程；关闭外部Q和热损耗计算，不执行自定义后处理。本轮不是R/Q或精度验收。

先无求解完成10组设置及候选查询（`solver-readback-calibration-bd5b95b9`，220次均不存在），再分别从同一源建立6个独立小网格单模副本。求解阶段无总超时，启动/退出有界，进程按PID+创建时间与工程路径核对，不强杀。

|case/证据根后缀|方法快照|target开关/值|自适应|Start/实际模式数|进程退出|独立观察|
|---|---|---|---|---|---|---|
|V01-default / e6b894c0|1|True / 480|False|1 / 1|0|Method: Default；约503.463262MHz；target来自原历史fmin*1.2|
|V01-general / af00e0db|2|True / 480|False|1 / 1|0|Method: General (Lossy)；约503.463416MHz|
|V02-zero / 2e55f5b7|1|True / 0|False|1 / 1|0|原生日志进入自动下界估计，约2.41501MHz；不能把True/0等同于显式正target|
|V02-disabled / 347a0c50|1|False / 480|False|0 / 0|1|自动下界0MHz，最大迭代耗尽；仍生成设置快照|
|V04-true / 9c13f691|1|True / 480|True|1 / 1|0|设MinPasses=MaxPasses=2；实际Pass 2且原生报告精度条件达到，约503.664159MHz|
|V02-precision / c5722491|1|True / 493.827|False|1 / 1|0|历史表达式fmin*1.23456789，数学值493.827156MHz；读回经格式化损失精度|

实际根名前缀均为`artifacts/solver-readback-calibration-`；原始Result/output.txt、Model.log、simulation_overview及solver.tsv、database.tsv互相核对。受控副本失败不是空频段证据：同几何/频段在正target或True/0对照已算出模式；本轮不对求解失败作自动扩窗或“无模式”判定。

自适应2个pass上限只为控制实验规模，不能据此证明普遍网格收敛。False→True由直接快照字段与明确原生日志共同确认，不以缺少某条日志倒推开关。

## 精度边界

GetDataBaseValue的double分支静态使用`%lg`；本轮实测493.827156被读成493.827，与默认6位有效数字格式一致，差0.000156MHz（156Hz）。保留原始字符串、格式精度及表达式来源；不将这个字符串转换后宣称无损double、精确表达式或按1e-9强比较。未来验证器需按已校准输出分辨率比较数值，非有限/无效文本拒绝；保留原表达式及预期高精度值，不因格式化将表达式改成固定数字。

## 保存重开、陈旧值和Rebuild

`artifacts/solver-readback-stale-42f7f320`从已关闭的e6b894c0/input.cst连同完整同名工程目录复制，只改副本。原源副本.cst及Result/Model.db前后hash一致。结果目录是本轮重开的整体前提，未做Model.db单文件剥离验证，也未实现私有.db格式读取器。

|阶段|实时AKSGetNumberOfModes|数据库六字段|结论|
|---|---|---|---|
|带结果重开|1|Default / True / 480 / False / Tet / Modes=1|旧执行配置可以重开读取|
|追加历史：General、target False/600、自适应True、请求2|2|仍Default / True / 480 / False / Tet / Modes=1|GetDataBaseValue是陈旧执行快照，非当前设置|
|随后Save|2|仍同旧六值|Save不刷新执行快照|
|随后Rebuild（仅副本）|2|六个key均Data item not found|重建使本轮执行数据库证据失效；不能将缺失当False/0|

新建无结果副本在设置后、Save后同样查不到key。求解失败副本却可读取它们，说明“配置快照存在”与“结果成功”是独立事实。不能仅凭字段存在判定任务、结果或关闭成功。

## 验证器和MCP设计约束

1. 求解前：当前持久定义仍由共享容器读取器和有界历史/参数投影验证，结合重开/重放及已校准profile；没有原生实时值时明确未验证。不得运行一次求解来给配置查询造数据，不得用旧Model.db放行新定义。
2. 求解后：把上述值作为`execution_snapshot`，绑定工程scope、安装build、实际attempt/run、定义revision、采集阶段/时间和结果数据库/工件hash；与本次冻结定义核对。方法/网格枚举按profile映射，未知值拒绝猜测。
3. 任何设置/参数/历史变更后，旧执行快照对新定义标记stale；Save不能解除，Rebuild之后missing也不能当默认。允许把旧快照作为历史执行证据展示，不能标记live-match。
4. 区分`execution-snapshot-match/mismatch`与`live-match/mismatch`，证据等级新增`native-run-database`，绑定证据不齐则unresolved/stale；这只是设计，生产验证器和公共Schema尚未接入。
5. 求解Start返回、实际模式/工件、执行设置、收尾及结果采用分别核对；本轮禁用target组配置已可读取，但计算仍失败。GUI/CLI/MCP共用同一报告投影，不在MCP单独做数据库读回框架。

原生实时getter仍无完整证据，G03及生产设置验证器未因此宣布通过。V01/V02/V04的执行快照读回与相应边界已有实测，后续重点是公共历史解释器、profile及阶段/陈旧性接入，不再盲目猜getter。

## 测试和收尾

安全回归[solver_readback_calibration_test.py](../test/solver_readback_calibration_test.py)覆盖查询重开不计算/不写设置、计算必须显式单case、陈旧值探针不重算/不扁平参数及候选预算。离线测试、原始数据清理及最终会话汇总见补记；artifact不保证随Git迁移。


最终补记：8个会话均确认归属进程退出，6次实际尝试中5次Start=1/实际模式1且有原生成功结果，1次Start=0/实际模式0/进程退出1并保留最大迭代失败诊断。后者不计成功，未通过强杀或从头重算掩盖。初始10组无求解查询、6组实际尝试及陈旧性阶段的期望值/缺失/精度事实已自动断言，轻量汇总artifacts/solver-settings-readback-20261028/acceptance-summary.json与solve-matrix.json。原工程hash和全部参数表达式复核一致。

最终离线36 passed（2.23s），artifacts/solver-readback-final-20261028.xml，包含新探针安全、CBOR拒绝/网格失败、归属/环境与文档索引；diff空白检查通过。索引仅证明链接/符号，不证明物理结论或公共验证器已实现。

所有CST进程退出后，核实8个本轮校准根和4个临时目录边界，清理55个模型/配套目录目标、pytest临时目录以及artifact内审计用capstone==5.0.7与pip临时目录；未改全局Python依赖/项目依赖。保留原生output/Model.log、simulation_overview、约75KB配置数据库、宏、参数/阶段/会话记录、保存历史摘录、源/模型hash及静态反汇编。原始.cst与场/网格/结果目录已删除，重开需重新生成，不能声称原始结果仍可访问。清理后D盘余量23.64 GiB，未清理用户原工程或其他任务。

重跑方式：默认脚本仅查询；真实计算必须显式`--solve --case V01-default`等单case。`--stale-source`只接受artifacts下已关闭的验收副本input.cst及其完整结果目录；清理后须先重跑成功小网格副本再执行该对照。不自动在配置查询中调用求解。
