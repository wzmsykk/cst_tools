# 五项CST设置读回：官方接口与保存工程证据

日期：2026-10-28。静态只读；设计见[设置验证器](../docs/cst-settings-verifier-design.md)。没有启动CST或修改原工程。现有工程盘点是文件观测，不是API运行验收。

## 1. 官方定义

本机CST2022 Online Help的EigenmodeSolver、Solver、Mesh、SolverParameter、MeshAdaption3D和Project Object六页方法标题/原文件哈希保存在`artifacts/settings-readback-static-20261028/official-method-inventory.json`。

- EigenmodeSolver页有GetConsiderLossesInPostprocessingOnly及结果查询，没有所求五项的完整getter集合。GetNumberOfModesCalculated是结果实际数量。
- Solver页Eigenmode Queries列出AKSGetNumberOfModes，解释为defined modes；同页开头注明AKS由Solver配置。该getter可作为校准候选，**没有**运行证据证明适用于Default/Tet，不能因名称直接排除或全局采用。
- GetFmin/GetFmax明确是频段；SetFrequencyTarget另定义下限。Solver.MeshAdaption在TD设置区，不是自动等价的Tet本征开关。
- SolverParameter控制模型简化（忽略损耗/非线性、细线等），不是任意求解器参数字典；MeshAdaption3D设置细化策略/阈值，不提供本征开关读回。
- Mesh文档化StepsPerWavelengthTet为波长相关边长约束；统计接口不是密度设置读回。Project.GetDataBaseValue存在，但本轮未找到这五项的公开key映射；不猜key。

## 2. cst_version实际实现

只读`D:\work\cst_version\cstv.py`，SHA256：`612eb6da9132ecf6aea8e2e0416877063c0bf70dfde1db3a4e01e7e9f52e23fc`。Git只读命令被环境拒绝，本轮以源码内容hash固定身份，不请求额外权限、不修改该仓库。

CstFile的中央目录和CRC校验、scope/member读取、history_steps及参数/JSON/Model.prj解析已实际用于本轮文件盘点。它**没有**五项最终有效设置解释器。历史块disabled识别有用，但不是完整VBA控制流；simulation()缺失/JSON错都可能返回{}，严格验证不能直接继承这种合并状态。

目前本项目搜索未发现对该CstFile的生产导入，不能把文档引用当已接入。后续复用同一共享只读实现，不复制成GUI/MCP两套，不依赖本机绝对路径。

## 3. 保存文件观测

|样本|容器版本/scope|观察|
|---|---|---|
|model/Pillbox.cst|2020.0/root|没有simulationproperties.json；Model.prj的Mesh Type=Tetrahedral、Mesh Cells=16,262、Last Solver Type=HF Eigenmode；历史给出更细的设置|
|model/Enlarged.cst|2020.0/root、SP/FMF、SP/FME、SP/FMEport|4个独立scope；FMF的Last Solver Type是HF Frequency Domain，其余为Eigenmode。不能用根配置解释子工程|
|project/WTC2022WORKNEW/WTC_ALT_2022_OPT.cst|2022.4/root|simulationproperties version=3，active_solver=HF Eigenmode、10–100MHz；没有五项完整设置；历史有nmodes表达式|
|cst_version/SSS500-L120-Hx90-Fx30-Fxx15-EG.cst|2022.5/root|simulationproperties为490–510MHz；历史两次Eigenmode配置，后一次模式数6、Tet自适应True、target490；这些是保存配置程序，非live读取|

4文件共7个scope，盘点前后SHA256一致；完整文件身份、元数据及候选成员保存在`inventory.json`，3文件历史定位在`history-traces.json`。均为可再生成轻量证据，不保证随Git迁移；原.cst只读未复制到artifact。

### 必须保留的反例

- Pillbox最后活动Eigenmode块为step61，模式数1；step60为停用块且写12，早期活动块还出现5/2/6。不能正则计数或只找“最后出现”的文本。
- Pillbox历史同时SetMethodType AKS/Hex与Default/Tet，是分别存配置，不是前一次错误/后一次修复。
- Pillbox参数fmin=400，target表达式=fmin*1.2；离线简单算术为480。读取全局fmin不能替代目标；这只是保存表达式解释，不是本轮CST重算数值证据。
- Tet mesh块有StepsPerWaveNear=10、StepsPerWaveFar=4、CellsPerWavelengthPolicy=cellsperwavelength；同文件Hex分区还有15。不能取一个数字代表所有Tet密度。
- WTC最后块SetNumberOfModes="nmodes"，参数expr/value均1；仅看参数并不能证明历史确实绑定它，且缓存值不自动证明当前会话依赖已更新。
- 样本Model/3D/Model.ads出现SOLVERTYPE=Transient，但active_solver/历史为Eigenmode；不能按文件里任意“solver”键判断当前算法。Model.bwc观察到ACIS/mesher几何文本，Model.dsn含端口描述，不据扩展名猜五项设置二进制位置。

## 4. 结论与剩余边界

保存的历史/参数是可解释且有准确来源的持久配置证据；需要新增受限语义解释、冲突/未知处理和版本校准，才可作为验证器。它们不能独立证明当前会话没有未保存修改，也不能证明Solver实际使用的算法/密度。完整可靠链必须再核对重开/重放与原生/行为证据。

当前找到了读回来源和验证器设计，并未找到可直接解除全部缺口的五个getter。V01–V06校准、Default/Tet上的AKSGetNumberOfModes适用性、Mesh旧新通道优先级及未保存live设置导出仍pending。结果少于请求数、总cell数、无自适应日志均不足补证。

本轮证据核对：20项只读文件事实断言通过，artifacts/settings-readback-static-20261028/static-checks.json；文档索引2 passed（0.70s），artifacts/settings-readback-docs-20261028.xml。前者不是新验证器单元测试，后者不证明文档语义/live读回；CST及V01–V06均未运行。

## 5. 后续受控校准

以上为先前静态批次。新增实测见[V01–V06受控副本校准](cst-settings-calibration-20261028.md)：V03本机三分支可读请求数，V05现代分区可读但新旧密度映射未证；五项完整门禁及V06语义解释仍未通过。

V01/02/04后续[执行数据库校准](cst-solver-settings-readback-calibration-20261028.md)已确认本版key与数值/开关映射，以及求解前缺失、Save仍陈旧、Rebuild清除、数值格式化边界；它不是通用当前live来源。
