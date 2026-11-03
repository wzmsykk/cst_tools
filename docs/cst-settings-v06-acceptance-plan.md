# V06验收用例与实施前合同

> 适用性复审（2026-11-03）：冻结设计/验收目标，非生产API清单；原候选名称、旧尚未实现及待办只在设计时点成立。现行实现见[当前状态](current-status.md)、[功能索引](feature-index.md)及对应API；不重算或追认旧证据。

## 原生采集/RunStore及B4子集（2026-11-02）

[共享采集链](native-execution-capture.md)已冻结意图/nonce/来源和安装，三阶段固定原生帧，六字段pre必须不存在才能Start，退出后归档DB并绑定对账。真实小网格Pillbox正常1模式、实际Start=0/0模式且配置匹配、旧库拒绝均取得副本证据，回执不将失败退出1写成正常成功；索引缺失可补且不重算。按用户要求2022大版本共用行为规则，精确版本/hash仍留档。默认Managed/HOM及公共single-simulation服务未自动接入，完整B4/G03/MCP闭环仍待完成。此前“采集/RunStore未实现”是较早阶段记录。


## B3执行快照内核实施（2026-11-02）

[公共只读验证器](execution-snapshot-verification.md)已实现六维绑定、固定2022.5/root/Tet profile、时间/阶段核对、6位g精度、严格快照JSON及实际数据库双hash。11项E oracle实际执行，另重放6组历史原生字符串；B2新增exact_values避免预期先转float丢精度。B3采集/RunStore权威接入及B4新副本未验，publish_ready始终false；不证明live、求解/结果/退出成功。下文B3未实现及56项全部not-run是历史阶段记录。


## B2首阶段历史与身份完成（2026-11-02）

[51项命令profile](a1-history-command-profile.md)已实现完整人工Pillbox XYZ历史投影：从同一scope有效历史核验mm/MHz、显式ChangeSolverType；不再接收调用者frequency_unit，元数据/注释不能补缺。修正Reset对象归属并拒绝无依据Mesh/MeshSettings.Reset，保留表达式、逐字段来源与失败语句定位。首阶段静态子集完成，不代表任意旧模板、实际保存重建、live身份或MCP服务器通过；B3/B4/G03仍待验。下文“完整历史允许表和单位身份pending”是本批之前状态。


## B2子集实施更新（2026-11-02）

已新增[受限历史投影](settings-history-projection.md)：H/S/M共35项语义oracle实际执行通过，保留表达式、逐字段来源与缺失配置，未知调用清空字段并拒绝。B1与新投影组合只读入口已实现；完整历史允许表、单位/solver身份锚点及B3仍pending，G03未通过，MCP服务器未实现。下文56项not-run是B0历史记录，不代表本轮35项仍未执行；未实施执行快照、启动CST或迁移GUI/CLI。


## B1更新（2026-11-02）

已实现[保存来源严格适配](saved-project-source.md)：固定复用cst_version只读方法、精确scope、原字节/哈希、严格编码/JSON、预算/CRC/读取变化校验及便携发布。旧文“B1待实现/未接入”是本批次之前状态；B2/B3生产语义与G03仍未通过，56项oracle仍not-run，无真实CST启动。来源复用采用随包固定上游摘取，未修改兄弟仓库，也未迁移所有旧入口。

日期：2026-10-28。按用户确认，本轮只补用例和设计；没有实现生产语义解释器、接入MCP、启动CST或自动提交。前置实测见[设置读回设计](cst-settings-verifier-design.md)及[执行快照校准](../knowledge-base/cst-solver-settings-readback-calibration-20261028.md)。

## 交付和证据分层

- [cases.json](../test/fixtures/cst_settings_verifier_v06/cases.json)：56项人工正反例的输入与预期，唯一规范性用例表；不是运行时请求/响应Schema。
- [evidence.json](../test/fixtures/cst_settings_verifier_v06/evidence.json)：5个真实保存历史片段的源文件/成员/片段SHA256、scope、step、原始行区间和编码观察；不是完整历史解释结果。
- [用例检查](../test/v06_casebook_test.py)：仅检查结构、未执行标记、证据hash与关键预期是否保留。它不运行待实现解释器；通过数字不等于56项语义通过。
- [编码/导航新增边界](../knowledge-base/cst-v06-source-boundaries-20261028.md)：共享读取器的方便默认、替换解码与严格验证边界。

所有用例semantic_execution=not-run，生产semantic_implementation=not-implemented，publish_ready=False。真实摘录与人工样例分别存放，不把人工故障视作CST实际响应，不将固定文本期望当作调用图或已实现接口。原始CST源只读；没有生成损坏CST文件。

## 用例范围

|组|ID|数量|预期重点|
|---|---|---:|---|
|历史/表达式|H01–H26|26|显式/With写、停用与局部注释、Hex/Tet槽位、配置分区、Reset、依赖/环/缓存失效、未知调用/控制流/动态代码、续行及整数域|
|作用域|S01–S07|7|明确root/SP，未知/缺失/方便别名拒绝；参数不跨scope；Eigenmode历史不证明当前solver family|
|Tet通道|M01–M02|2|near/far/policy分别保留；未匹配校准上下文的混合通道保持ambiguous|
|来源完整性|D01–D10|10|JSON缺失/损坏/重复键/类型、CRC、声明编码违反/未知旧编码、读取期间变化、压缩与资源预算|
|执行快照|E01–E11|11|失败尝试仍可有配置、工程/attempt/revision/DB hash绑定、未知枚举、缺失及精度；不冒充当前设置|

表内数量是设计覆盖，不是验收通过数。字段路径是用例断言标签，reason是规范性拒绝原因；尚未创建wire错误枚举或公共DTO。实现时映射到统一契约，不另建一套公共接口。

## 1. 来源与scope先于语义

读取入口接受已经解析的明确scope身份，不把缺省/便利别名当权威。必须先读取共享组件project_scopes给出的确切清单，验证请求scope，再读取该scope成员。内部read-adapter的scope=None或FME应拒绝；这不是要求终端用户手填scope，公共服务可从文档/子工程ID明确解析后传入。

共享cstv._scope_prefix目前把None/空串当root、把FME补为SP/FME；这是方便用法，验证器不能据此决定选哪个工程。S02–S04禁止fallback及擅自补前缀，不改共享库方便API，不复制容器解析器。scope、文件hash、参数成员hash与history member必须属于同一快照。

Enlarged真实证据的root/fmin=499与SP/FME/fmin=498.5不同；SP/FMF的保存Last Solver Type为Frequency Domain，但历史中仍有Eigenmode设置。该元数据也不是当前live solver证明；选A1配置分支需要独立身份锚点，不能靠历史对象名。

读前/后身份不一致为stale；CRC/中央目录错误不降级正则扫描。预算超限不截断后宣布匹配。未知编码与损坏格式分开，见第4节。资源预算的数值留到实现基准确定，本用例只冻结“超限必须显式拒绝”的行为。

## 2. 最小历史语法合同

从不可变保存成员读字节，保留member、scope、step、原始行/字节区间及hash。先词法分段，再处理对象/语句；不能逐行last-regex取最终设置。

1. 支持明确EigenmodeSolver、MeshSettings对象及平衡With栈；标识符/已知命令按VBA规则识别。字符串双引号转义、字符串外单引号注释和字符串外`_`续行独立处理，保留原始位置。
2. 整块停用要以真实保存格式确认；不对所有行剥前导引号。局部注释不使其他有效行停用，也不从注释提取setter。
3. SetMethodType按Hex/Tet槽位存储；EigenmodeSolver.SetMeshType选求解分支，MeshSettings.SetMeshType只选被编辑的配置分区。没有活动分支证据，不产生selected_method。
4. 已知Reset清除相关已知值。无明确profile默认登记时保持reset-unresolved；当前一次Reset读1不构成通用默认。后续明确setter可恢复对应字段，其他字段仍未知。
5. 表达式只支持已声明白名单算术/参数依赖，禁止eval、宏执行或任意函数。同scope依赖拓扑有环/缺失时unresolved；缓存值与表达式推导不符时stale。保留原表达式，不改固定值。
6. A1的受限CInt(RestoreDoubleParameter("name"))仅支持已证实为整数的参数值；分数输入超出此子集，不模拟完整VBA舍入。H22/H26是新验证子集的规范性拒绝，不宣称CST会作同样拒绝。
7. If/For/未知别名、Call/RunMacro、Evaluate和未知可能改设置的调用不执行。相关字段tainted；不能保留未知调用前的旧值当最终值，也不因文本条件恒真就执行。已审查无关几何/设置命令才能进入明确允许表，未知命令不静默跳过。

这不是VBA解释器。H01/H09只证明用例关注的模式数字段可被明确赋值，不能据未列出字段推断五项配置齐全或ready。A1自身可控生成结构优先；任意用户宏不承诺支持。

## 3. 缺失和错误的范围

D04允许“可选simulationproperties不存在，但历史中已有明确请求模式数”保留该字段投影；仍记录metadata missing，不能补出频段/算法等默认。D01–D03的成员实际存在却不可解码、重复键或类型错误，与缺失不同，进入严格验证失败。

casebook的resolved是“关注字段的静态期望可确定”，不是公共ready。unresolved/unsupported/ambiguous/malformed/stale/rejected不允许用请求值填observed。未来公共报告按D15已有状态分层，execution-match映射execution-snapshot-match，不能映射live-match。

## 4. 编码事实与失败责任

本轮实读Enlarged完整历史成员发现非UTF-8字节：root首错偏移9609，SP/FMF 11611，SP/FME 11618；Pillbox历史为UTF-8。这些均为现有CST文件，不能据UTF-8失败认定CST工程损坏，也不能据字节外观猜GBK/系统ANSI。

共享history_steps现有UTF-8/replace只用于本轮块导航，核对字节行数；原始摘录完全保留字节。证据中semantic_fallback_used=False表示没有选择替代语义编码，不否认导航函数用了replace。选中片段即便是ASCII，也不能证明完整历史可安全解释。

- D06：输入明确声明UTF-8而字节违反该声明，malformed。
- D10：未声明编码的旧历史不能严格按已支持profile解码，unsupported/encoding-profile-missing；保留字节和诊断，不替换继续。
- 后续编码支持须明确来源/安装与编码profile、严格解码及字节到字符位置映射；不使用“最像某编码”的启发式来放行G03。

## 5. 执行快照与数值分辨率

E组比较的是某次尝试的配置，绑定project、scope、attempt、definition revision、build、数据库hash及采集阶段。失败结果可有匹配的配置；不能把两种成功混为一谈。未知枚举、缺绑定或空字段不默认；任何绑定不符，即使数值相同也不能采用。

input.expected_execution_config模拟公共服务从冻结定义读取的预期，不能从数据库值反推，也不能由工具调用方自由声明来覆盖存储权威。input.calibration_profile只是该用例的明确前提，不是已登记的生产profile或能力解锁；其版本/方法/数值格式缺证据时仍拒绝。

E06/E07使用已校准%lg六位有效数字语义，而非固定1e-9或任意大容差。E10/E11专门防止把返回480的末位理解成1MHz精度：%g会省掉零，已校准6位有效数字在480量级的分辨率约0.001MHz。480.0001可格式化为480，480.4不能。没有匹配格式profile时，不自动套这个规则。

这些字段只能进入execution_snapshot，live_value仍null。Save不刷新历史执行快照，Rebuild可能清除；不得为了读配置额外求解。原表达式、高精度预期、原始返回字符串和格式profile分别保留。

## 后续验收顺序与完成标准

|阶段|允许推进的内容|必须取得的证据|
|---|---|---|
|B0，本轮|固定人工oracles、真实摘录/来源、拒绝合同|结构/hash检查；不称语义通过|
|B1，已实现|共用cst_version只读基础的严格适配，明确scope/编码/完整性|真实保存源读取及严格故障拒绝；见B1分批验收，不等于新CST运行|
|B2，A1子集已实现|受限词法/历史与参数投影，逐字段来源|H/S/M 35项实际运行、D04组合行为；其余D逐项语义映射、任意旧模板/编码未全部覆盖|
|B3，内核及RunStore入口已实现|公共执行快照、绑定/精度/陈旧性判定|E组11项实际执行、历史字符串重放及[本轮真实采集](native-execution-capture.md)；公共single-simulation服务仍待接入|
|B4，采集子集已验、余项未完成|授权下新小网格副本正常/实际失败/旧库拒绝|源/表达式保持、归属退出、DB hash及索引补写已验；完整保存重开/陈旧组合及首阶段发布仍待验，不追认旧证据为全部新实现通过|

生产G03仍未通过。B1–B3已按后续授权分批实现上述只读内核，没有实现MCP服务或迁移执行链；本用例表不授权真实求解、提交或推送。下文“本轮”是2026-10-28原B0记录，不能覆盖最新分批验收。

本轮验收：用例结构/证据检查4项及既有校准安全/环境/归属/索引回归合计40 passed（2.24s），artifacts/v06-design-verified-20261028.xml；56项语义预期仍全部未执行。测试重算源CST和摘录hash，成员hash在本轮共享读取器只读提取时产生；pytest没有集成外部cst_version，不重新解包核验成员hash。diff空白检查通过。

本轮仅约77KiB固定用例/摘录数据，无CST模型/场文件生成；pytest临时目录已按明确路径清理，保留轻量XML和提取记录。fixtures是拟随Git保存的固定材料；artifacts中的报告/作者脚本不保证随Git迁移。本轮未提交或推送。

提交准备补核：原字节.mod包含CST原生行尾空白，根.gitattributes为该目录片段设置binary，禁止换行转换；提交时另外核对暂存blob与工作区/记录hash，不能为通过空白检查而改写证据。
