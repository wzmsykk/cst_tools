# CST设置验证器：读回来源、作用域与门禁

日期：2026-10-28。静态设计，未实现/未启动CST。服务契约见[首阶段接口](mcp-first-stage-interface-contract.md)；固定样本/官方来源见[读回核查知识库](../knowledge-base/cst-settings-readback-20261028.md)。本设计区分**保存的配置程序、运行中设置、实际求解行为**，不把三者互相冒充。

## 1. 本轮结论

没有在已核查CST2022官方接口中找到这五项均适用Default/Tet的完整直接getter。`Solver.AKSGetNumberOfModes`已在本机2022.5副本Default/Tet、General (Lossy)/Tet与AKS/Hex的1/2设置及重开校准；不推广为所有版本/方法通用getter。Python Modeler和SolverParameter也不提供这五项的通用属性查询器。

可靠的现有基础是：复用cst_version经过中央目录/CRC验证的容器读取，以明确scope读取Model.mod、Parameters.json、simulationproperties.json和Model.prj，**读回已保存定义及来源**。但cst_version当前只提供文件内容/历史块，不解释最终有效求解设置，更不能证明当前CST会话没有保存后修改。

因此冻结两条独立验证链：

- **持久定义链**：已关闭文件快照 → 严格读取 → 受支持历史语法解释 → 配置/参数/版本证据 → 定义符合性。可证明“保存的程序将怎样配置”，不能直接称live readback。
- **会话/行为链**：重开只读检查或受控副本重放 → 原生可查询锚点 → 已校准设置读取器/求解器输出 → 与持久定义交叉核对。本轮已执行受控设置/重开校准，模式数及现代Tet分区读数有实测；其余五项整体门禁仍未解锁。

第一阶段不因缺getter而改成永远只做代码生成；也不降低门禁为“脚本写着正确”。持久读回设计可先实施，实际设置证据不足仍返回SETTING_UNVERIFIED。之后通过有意制造差异的副本探针逐项校准，不能用正常一次成功替代。

## 2. 五项设置来源矩阵

|统一字段|官方直接查询与范围|持久读回及解析规则|当前可证明/不可证明|
|---|---|---|---|
|solver.method_by_mesh / selected_method|GetSolverType只返回HF Eigenmode类别；本轮未找到GetMethodType。SetMethodType按Hex/Tet分别设值|Model.mod中的EigenmodeSolver.SetMethodType(method,mesh)，按mesh分别维护；再结合SetMeshType和原生Mesh.GetMeshType确认选用分支|可读保存的Default/Tet与AKS/Hex并存配置；active_solver或Last Solver Type不能证明具体算法|
|solver.frequency_target.enabled/value_mhz|GetFmin/GetFmax读全局频段，不是SetFrequencyTarget；未找到专用getter|读取SetFrequencyTarget(bool,expr)，保留表达式、求值来源和单位；enabled=false时只报告存储值，不能当有效下限|保存历史中的目标和频段可不同。Pillbox的fmin=400、target=fmin*1.2，独立算术为480，不能取400替代|
|solver.requested_modes|AKSGetNumberOfModes官方称defined modes，但同页明确AKS由Solver配置；Default/Tet适用性待探针。GetNumberOfModesCalculated是结果实际数|读取EigenmodeSolver.SetNumberOfModes，支持有界整数/参数表达式及新生成器CInt(RestoreDoubleParameter(...))；读取同scope参数|可读保存请求数；参数nmodes单独存在、实际算出1个都不证明请求数。参数缓存value不代替依赖刷新|
|solver.mesh_adaptation.tet|SetMeshAdaptationTet明确setter；MeshAdaption3D配置细化策略，不是本征模开关getter；Solver.MeshAdaption在TD设置区|解析EigenmodeSolver.SetMeshAdaptationTet及Reset/后续覆盖，Hex开关另存|可读保存的Tet开关；没有自适应日志或仅一pass不能证明false|
|mesh.tet.density|StepsPerWavelengthTet是文档化setter，无同页配套getter；GetNumberOfMeshCells/GetMaximumEdgeLength为结果统计|分别记录旧Mesh.StepsPerWavelengthTet与MeshSettings/Tet的StepsPerWaveNear/Far、CellsPerWavelengthPolicy、Version及上下文|可读保存的数值/策略；两种通道的等价/覆盖优先级未校准，不把near=10/far=4压成一个“密度=4”或矛盾|

五项之外的锚点可直接查询：Project.GetSolverType、Solver.GetFmin/GetFmax、Units.GetFrequencyUnit及比例、Mesh.GetMeshType、EigenmodeSolver.GetConsiderLossesInPostprocessingOnly。它们支持身份/单位/选择分支交叉核对，不补齐缺失字段。

`Project.GetDataBaseValue(key)`只保证按给定key读取数据库；本轮未得到这五项的厂商公开key清单。禁止按英文名称拼key、遍历敏感数据库或把空串解释为默认值。找到并校准某版本key后才可登记为可选version-scoped读取器，不形成通用反射接口。

## 3. 复用cst_version的边界

当前只读来源是`D:\work\cst_version\cstv.py`，源码SHA256固定在知识库。实际实现：

- CstFile._central_entries/_entry_data：EOCD和中央目录定位、同名/偏移/大小及CRC检查，不在压缩数据中猜DE标记。
- CstFile.project_scopes/scoped_member/history_list/history_steps/parameters/simulation/project：根工程与SP/<name>显式取成员。
- history_steps_of/_is_disabled：历史块边界/行号和全注释停用块识别；**不是**完整VBA解释器。

集成选择：工程容器/参数/历史读取共用cst_version基础组件，GUI/MCP验证器不复制解析器。当前仓库源码搜索未见对该CstFile的实际导入，不能宣称已经完成集成；后续需将固定、可测试的只读组件按公共模块依赖接入，不让发布包依赖开发机D盘路径。settings语义解释是该统一基础之上的专用投影，不另建容器框架。

生产验证器不得直接把当前宽松返回当验证通过：simulation()在缺失和JSON错误时都返回{}；history_list()用UTF-8 replace；_parse_prj可能覆盖/忽略重复键。验证路径要保留原始成员、严格解码/重复键/类型、明确missing/malformed/unsupported，不能把{}当默认配置。可以在共享组件补严格模式/状态类型，但不维护两套读法；本轮不改任何代码。

读取只接受已发布/已正常关闭的不可变快照；校验读取前后文件hash/身份一致，拒绝活跃写入。限制文件/成员数量、声明/实际解压大小及文本总预算，先核对中央目录长度再解压；现有CstFile整文件载入不能被宣传为无限规模流式读取。ZIP64/未知压缩/格式变体没有支持证据时明确unsupported，不降级字符串扫描。

scope必须来自project_scopes返回的确切列表。A1只接受root/MWS 3D；复合工程导入时要求显式SP身份。相同参数名和Mesh Type在不同scope不能混合；Model/DS/Model.dsn、模板r0d/r1d和plot_settings均非五项设置权威。Model.prj的Last Solver Type是辅助元数据，不自动等于当前保存/待运行求解器。

## 4. 有界历史语义解释设计

验证器读**保存后的Model.mod原始字节**，而不是服务自己生成的VBA字符串。保存文件哈希、成员哈希、scope、CST版本、参数成员哈希及定义revision必须一致。解释过程只构建数据，不运行宏、不调用Python eval、不改原工程。

按历史真实顺序处理，保留step/line/对象/前后值的链：

1. 正确认识CST标题/版本注释、停用块、行尾注释及字符串；不能把注释内SetNumberOfModes当命令，也不能把每行所有前导引号都剥掉。
2. 维护With栈和显式对象名；EigenmodeSolver.SetMeshType选择求解分支，MeshSettings.SetMeshType只选择被编辑的配置分区，后者的All/Unstr/Hex不能自动当活动求解网格。
3. SetMethodType("AKS","Hex")和SetMethodType("Default","Tet")分别写不同槽位；后者不抹掉Hex配置。active mesh单独取证后才产生selected_method。
4. Reset使相关字段进入reset-unresolved；只有精确安装版本默认已登记并验证，才能补默认，否则等待后续显式setter。不能套最新版帮助默认到旧工程。[VERSION]注释可能是历史来源版本，与保存容器版本分别记录。
5. SetNumberOfModes/SetFrequencyTarget/SetMeshAdaptationTet按同对象显式写覆盖，持久表达式读取同scope参数。支持数字/布尔字符串的已知CST录制形式，但公共新请求仍严格类型。原表达式与解析/值来源独立返回，不把缓存value当最终值。
6. 简单表达式只支持白名单算术、参数依赖及新A1生成器的受限RestoreDoubleParameter/CInt模式；无任意函数求值。对缓存value和离线求值不一致返回stale_parameter_cache，真正live值仍需原生核查。
7. Mesh密度按对象/mesh partition/policy分别保存。旧legacy setter与新MeshSettings同时出现时，在优先级映射未校准前报告ambiguous-channel；不靠最后一个匹配“StepsPerWave”的文本决定。
8. If/For/Do/With未知别名、Call/RunMacro、Execute/Evaluate动态生成代码、条件Restore、未识别Reset或可能修改目标字段的未知调用，相关字段tainted/unsupported。文件中可有已知无关几何命令，但必须由固定允许表确认，不是随意忽略陌生命令。

解释范围以A1自身生成的可枚举结构优先；任意用户宏不能承诺完整支持。已有history_steps标题只是导航，不作为类型判定；整个块未disabled也可能含局部注释/条件，不允许整块正则粗提取。

## 5. 验证结果与可靠性等级

公共字段结果扩展为：field、expected、persisted（raw/expr/value/unit）、live_value或null、behavior_value或null、source（file/member/scope/step/line及hash）、parser_profile、observed_at、status、missing_evidence。source必须能回到真实保存位置，不只指向服务请求。

状态冻结：

- persisted-match / persisted-mismatch：在支持语法内可还原保存定义；不是live验证。
- live-match / live-mismatch：已校准当前设置查询或独立配置导出，绑定同一会话/工程/当前revision；同一会话存在也不足排除旧执行快照。
- execution-snapshot-match / execution-snapshot-mismatch：绑定某次attempt和定义revision的原生执行配置；source.phase、观测时间、配置/结果数据库hash齐备才可比较。不能作为新定义的live-match。
- replay-corroborated：官方重建成功、保存后历史/参数一致且可用原生锚点一致；仍注明缺失的直接live字段，不改名为getter-match。
- unresolved / ambiguous / unsupported / malformed / stale：缺失、多个通道、语法范围外、内容损坏或哈希/参数缓存不一致。

先前verification.evidence_level补充persisted-history与persisted-metadata，新增native-run-database，保留history-replay、native-query、artifact-check；原生执行数据库放在execution_snapshot，不填入live_value。不同来源矛盾不能按“信任请求”覆盖；记录field/expected/observed冲突，SETTING_UNVERIFIED或MODEL_VALIDATION_FAILED。

A1的严格门禁继续要求：五项持久定义明确匹配、求解前保存重开/重放事实、原生锚点一致，以及该安装版本/配置通道的校准profile通过。未经校准的persisted-match/replay-corroborated单独不足G03，当前仍未ready。未来若通过有差异的受控验证证明某通道能可靠反映重开设置，可将其标记为经过校准的持久设置读取器，**无需强求不存在的getter**；它仍不是当前未保存会话通用读回。

## 6. 版本校准与对照设计（已启动，非全部通过）

|探针|有意制造的差异|必须排除的伪通过|
|---|---|---|
|V01 method|相同Tet模型Default与General (Lossy)副本；另留Hex/AKS配置|只读active_solver=HF Eigenmode、混用Hex方法、拿求解成功倒推算法|
|V02 target|固定fmin，target=0/其他正值/禁用，逐副本保存重开|用GetFmin/频率最低模式替代target；启用与值混为一谈|
|V03 modes|请求1/2，先比较AKSGetNumberOfModes在AKS/Hex与Default/Tet的设置响应；不能依赖实际仅一个模式|GetNumberOfModesCalculated、端口.NumberOfModes、参数nmodes数值作为设置|
|V04 adaptation|同密度下Tet true/false，记录配置/重开与原生日志；必要实际求解另授权|一次pass或未出现progress标签当false；MeshAdaption3D.MinPasses当开关|
|V05 density|legacy StepsPerWavelengthTet及MeshSettings/Tet near/far/policy分别单独改动和双通道顺序对照|只用cell总数/网格变细证明某具体值，或把近/远密度忽略|
|V06 scope/history|root/SP不同值、停用最后一块、Reset后无setter、参数依赖、条件宏、损坏JSON/CRC|last regex、fallback到root、解析失败返回默认空配置|

无CST静态用例先验证解释/来源/拒绝规则；新语义读取器运行实现尚未写。本轮已获受控副本校准授权并执行[校准记录](../knowledge-base/cst-settings-calibration-20261028.md)，没有启动求解；不直接编辑私有二进制构造CST工程，不让探针保存覆盖原模型，不强杀无关实例。

校准profile至少绑定CST major/release/build、scope/module、method/mesh、设置通道、共享解析器身份、宏实现hash和已完成用例。CST升级或不支持格式直接unknown，不维护旧API兼容；必要重新校准。静态样本的历史[VERSION]不作为安装版本映射证据。

## 7. 公共服务接入位置

configure_simulation/save_project在候选正常关闭后读取持久定义，再由明确验证操作建立重开/重放证据；inspect_model只投影已存报告，不启动CST。submit_run只接受报告与definition artifact哈希一致且ready的定义；执行前检测文件变化，不能使用旧报告放行。

验证器是公共工程基础服务的一部分，GUI/CLI/MCP共用；不在MCP进程重新解析cst。后台记录SETTINGS_VERIFY_STARTED/OBSERVED/MISMATCH/UNRESOLVED与doc/revision/field/source/error_ref，正常重复查询不打印INFO风暴。报告保留轻量字段和来源，完整宏/成员走受控工件引用。

## 8. 本轮范围

只读官方帮助和cst_version源码，离线盘点4个已有.cst/7个scope，源哈希复核未变。没有CST启动、保存、求解或GUI修改；没有新增运行解析器或探针。详细证据及明确反例见知识库，不能用这次静态盘点追认V01–V06或G03通过。

本轮证据核对：20项只读文件事实断言通过，artifacts/settings-readback-static-20261028/static-checks.json；文档索引2 passed（0.70s），artifacts/settings-readback-docs-20261028.xml。前者不是新验证器单元测试，后者不证明文档语义/live读回；CST及V01–V06均未运行。

## 9. 受控副本校准补记（2026-10-28）

[最新记录](../knowledge-base/cst-settings-calibration-20261028.md)覆盖V01–V06的设置/重开及共享读取器反例。V03本机三分支请求模式数读回已校准；V05现代Tet MeshSettings.Get实测有效，但legacy 4→6未改变near/far，不能建立单值等价映射。Get为本版本实测、非已核查官方保证。方法/target/自适应仍缺独立读回；V06语义解释器未实施。生产验证器、MCP接口、G03均未因此解锁。前节“本轮”仅指前一次静态核查，不能覆盖本节新增实测。

V06新增实测：nmodes+1经Rebuild后查询2，Reset后查询1，原表达式不变；仅记录当前版本/上下文，未实现通用Reset或条件宏解释器。

## 10. V05实际网格校准更新（2026-10-28）

[完整实测](../knowledge-base/cst-tet-density-mesh-calibration-20261028.md)将前节密度pending细分：本机Version=1现代near/far映射到独立输入步长约λ(fmax)/N，near4/8使实际网格1408/8720 cell；旧4/8及混用顺序不改变网格。far在当前闭腔未改变最终网格，但输入变化，不能判全局无效。Version=0在当前求解配置拒绝生成网格，宏退出0仍为失败，不提供自动回退。

A1统一标量设计采用新工程near=n/far=n的显式现代策略，导入工程保留分区；不是旧API转换。生产实现尚未接入；其余字段与G03仍未通过。跨版本/其他policy、材料、开放域及最大边长/输入step关系仍待验，前节未校准描述为历史状态。

## 11. V01/V02/V04执行快照校准（2026-10-28）

[完整记录](../knowledge-base/cst-solver-settings-readback-calibration-20261028.md)确认官方GetDataBaseValue可读版本限定key前缀objdata\EigenmodeParameter\：SolverTypeTet（1=Default、2=General Lossy）、FrequencyTargetActive/Value、AdaptionActiveTet。原生日志和实际2个pass交叉核对，支持执行配置证据，未知方法枚举不猜。

这些key在无结果副本求解前/Save后缺失，求解失败后也可出现；带结果重开可读，当前设置改变再Save仍返回旧值，Rebuild后消失。故不是原生实时getter，不用它解除新定义SETTING_UNVERIFIED，不为配置查询自动求解。前置验证仍需公共有界历史投影/重放/profile，执行快照仅核对对应attempt，任何定义变更标记stale。

FrequencyTargetValue输出经过%lg格式化，493.827156读成493.827，必须保留表达式/原始字符串和数值分辨率，不能按无损double精确比较。V01/02/04的执行快照读取和边界已校准，生产解析器、阶段绑定及G03仍未通过；前节“缺独立来源”属于此前批次，实时缺口仍成立。
