# MCP的CST能力、作用域与实施边界


架构决策更新：以[MCP优先、CST Tools共用底层](mcp-framework-static-design.md)为最新约束。此前mcp_service专属业务层及“仅允许Runner小幅增量”的限制已被替代：按统一契约迁移旧底层，GUI/CLI/MCP共用公共应用服务；旧源码映射仍是现状证据，不是目标接口保证。

日期：2026-10-28。属于M0详细设计，不是已发布API；本轮未启动CST、导入原生扩展或修改运行代码。协议基线见[MCP符合性矩阵](mcp-protocol-conformance.md)，工具清单及阶段见[接入计划](mcp-design-plan.md)。

## 1. 依据与证据强度

本轮直接阅读本机CST2022安装帮助的下列完整页面，以及Python包装源码、生产Worker与宏。这里的“官方提供”限定该安装版本，不声称已审查2026最新版CST。CST求解器、OLE服务和Python原生扩展内部源码不可见，不能把包装层审查称为完整底层逆向。

本机基准目录：`D:\Program Files (x86)\CST Studio Suite 2022`。

|编号|相对于基准目录的官方资料|核查内容|
|---|---|---|
|S1|Online Help/advanced/commandlineoptions.htm|模块、批处理、Model.run、参数导入、MPI/DC和退出码|
|S2|Online Help/advanced/vbaapplicationobject.htm|OLE Application、版本选择、Active3D/ActiveDS和QuietMode|
|S3|Online Help/Python/source/cst.interface.html|DE、Project、Modeler、Schematic实际方法及作用域|
|S4|Online Help/Python/source/cst.results.html|0D/1D、子工程、参数run id、读取一致性限制|
|S5|Online Help/mergedProjects/VBA_3D/special_vbasolver/special_vbasolver_eigenmodesolver_object.htm|求解方法、频率下限、实际模式数、外部Q|
|S6|AMD64/python_cst_libraries/cst/interface/studio.py；cst/results.py|包装代码实际委托编译扩展；results模块支持范围|

仓库已有[对象语义审计](cst-vba-document-semantics-audit.md)、[历史持久性对照](cst-history-persistence-and-solver-failure.md)、[工程内宏作用域修正](concave-expression-scope-rebuild-fix.md)及[运行时隐含行为](../knowledge-base/cst-2022-runtime-hidden-behaviors.md)保留各自日期与真实证据。本轮重新核对有关帮助和现行源码，不把历史测试数量作为当前验收。

## 2. 官方接口与当前实现不是同一层

|通道|官方能力与限制|本项目现状及MCP取舍|
|---|---|---|
|CLI批处理 S1|`-m`选择MWS；`-b`在已加载工程执行Model/3D/Model.run；`-e`直接启动Eigenmode；`-par`支持含表达式的UTF-8参数文件；`-i`为最小化启动|Managed使用`-m -b worker-input.cst`，生成工程内宏。不是仅调用`-e`；后者没有本项目任务循环、复杂后处理、ACK和收尾回执。最小化不是Windows无GUI/headless保证|
|OLE Application S2|非版本ProgID启动最后安装版本；版本ProgID可明确2022。OpenFile返回工程；Active3D/ActiveDS访问当前对象；QuietMode不能消除所有需输入的对话框|不通过全局活动实例控制任务，不让MCP遍历并关闭其他用户实例。Application.Quit影响应用，不能当Project级释放|
|Python控制 S3/S6|DE支持new、connect(pid)、open_project；Project分modeler与schematic。modeler有add_to_history、run_solver、start_solver、is_solver_running、abort/pause/resume；schematic有execute_vba_code|生产仍是批宏文件协议；Python接口可作为以后独立后端候选，不能仅把调用替换后宣称恢复协议仍成立。execute_vba_code的接收者是schematic，不能按名字当通用3D执行器|
|Python结果 S4/S6|`cst.results`离线读取0D/1D；支持2021/2022未打包、未保护工程；支持显式子工程及结果run id|现有native_results是按声明路径读取单行标量文件，并未接入cst.results。不能把Native provider称为官方Python SDK适配器|
|VBA与Result Template|工程内VBA可使用现有求解/场后处理对象；模板有自己的配置及生成结果|保留运行时复杂算子；原生结果仅在积分定义、轴、偏移、单位和来源相符时替代。模板存在不代表已计算结果，已有结果不代表允许修改配置后无损重算|
|官方DC/MPI S1/S5|CLI的-withmpi仅列出特定求解器，未列Eigenmode；Eigenmode.SetRemoteCalculation提交网络求解，说明其不影响DC参数扫描/优化|不能将use_mpi、use_remote配置字段等同于HOM集群可用。CST内部并行、官方网络提交与本项目跨节点任务分发分别验收，仍归E6–E9|

`connect_to_any()`帮助明确多个DE存在时随机选择；`ExistingOrNew`也不能证明新建实例归本任务所有。未来原生控制后端必须记录新建/连接模式、PID、创建时间、版本、工程绝对路径及所有权证据。仅PID匹配不足以抵抗PID复用。

安装目录实际存在cp36–cp39的`_cst_interface` Windows扩展；不能据此承诺当前GUI的任意Python版本可直接导入。S6只是薄包装，不证明线程安全、重入、连接断开后的调用完成状态或timeout是否中止求解。这些均需单独探针，不能用Python Future.cancel替代CST停止。

## 3. 六层作用域与身份

|层|身份及读写边界|禁止的推断|
|---|---|---|
|应用实例|版本、用户/会话、PID和创建时间；只控制明确归属实例|进程名为CST就归当前任务；关闭GUI等于关闭CST|
|工程及子工程|项目路径/摘要、显式subproject tree path；区分3D modeler与schematic|同名参数跨3D/DS/Simulation Project自动同步；根工程结果代表所有子工程|
|Worker会话|worker_id、session_id、私有副本与协议目录；生产宏在该副本编译执行|宏内OpenFile会重新绑定已编译参数作用域；任意绝对bas路径都是RunMacro支持的名称|
|逻辑运行/任务尝试|Runner run_id、task_id、attempt、参数及结果revision|CST整数run id等于Runner UUID；重试就应换逻辑任务身份|
|模式及后处理|当前CST模式编号为1-based；跨窗口匹配身份另存；积分线/域/权重/单位随结果|Mode 1在下一窗口仍是同一物理模；get_3d就是三维场读取|
|采用与收尾|completion、ACK、snapshot、RunStore采用、close.receipt、StopAck及进程退出分别核对|ACK即已采用；Save返回即完整关闭；进程退出0即任务成功|

MCP查询结果的来源键拟定为：project_id、Runner run_id、task_id/attempt、session_id、snapshot/revision、可选subproject、CST result run id、treepath及mode index。不存在的字段为null。第一版只查询框架已采用的结果，不开放任意CST树路径或任意子工程执行。

S4的get_all_run_ids默认只返回最高自适应网格pass；单个树项可缺少某些run，run=0还可能与参数run重复。未来官方结果适配器须按具体树项get_run_ids并核对参数组合，不能对所有树项笛卡尔遍历，也不能靠数字相同拼接跨工程结果。

## 4. 生产调用链与成功条件

入口由[Runner](../csttool/runner.py)受理，经[ApplicationBackend](../csttool/application_backend.py)、[CSTManager](../csttool/cstmanager.py)分发至[ManagedCSTWorker](../csttool/managed_cstworker.py)。MCP只适配该链，不再同时拥有一个DE控制器。

1. `ManagedCSTWorker._prepare_project_copy`复制prepared工程及存在的同名配套目录；`_build_macro`组合任务协议、v2收尾协议、主宏和后处理，覆盖副本Model.run；`_launch_command`进入已加载工程。复制.cst满足无结果预处理需求，但不能保证已有E/H结果可用。
2. [生产宏](../data/runtime_managed_worker_v1_main.vb)依次读取任务、捕获本任务涉及参数、逐个StoreParameter、Rebuild、配置求解器、Start、查询实际模式数、后处理、Backup、发布completion、等待ACK。参数表达式保留，恢复只处理实际已尝试修改的参数并删除新增项。
3. Start非1失败；Start=1仍须GetNumberOfModesCalculated至少1，再验证所需结果/工件和任务身份。S5说明实际模式数可能小于请求值；不能以少于nmodes判求解失败，也不能用失败证明窗口为空。
4. Backup形成任务结果快照；Python `run_task`读取并校验后再ACK，框架采用另有检查点/RunStore步骤。MCP submit仅返回受理，最终成功读采用事实。
5. `request_stop`只发布合作停止请求；宏在检查点响应。同步EigenmodeSolver.Start内部没有轮询这些文件，故不能承诺立即打断当前求解。官方Modeler.abort_solver虽存在，但尚未纳入此生产链和恢复验收。
6. `stop`核对收尾评估，共享退出deadline避免重复等待；`retire_failed_session`仅严格匹配失败、restored-saved、ACK清理、回执及实际退出1等证据时记录abandoned-dead，仍非标准关闭。失败后的新Worker基准为processed/prepared工程，HOM已采用覆盖及结果保留。

MCP状态必须同时表达业务终态、execution_active、session_safety和可恢复性；不把FAILED统一改为可以立即新提交。扫描目标endfreq属于算法范围，fmax属于本轮窗口，SetFrequencyTarget是下限而非“最接近目标的模式”。SetModesInFrequencyRange只适用JDM，不作为通用HOM全模开关。

## 5. 修改与读取的一致性

|操作|执行前提与持久化|MCP策略|
|---|---|---|
|预处理|副本内建立fmin/fmax/nmodes及可选cell；稳定历史引用参数；检查Rebuild和产物|只通过现有prepare_run配置进入；不提供绕过运行锁的set_parameter工具|
|每轮频率/模式数|参数表保存表达式，历史重放读取当前数值；Rebuild使旧结果失效|与任务绑定提交，禁止在活跃求解/已有场分析中另行UPDATE PARAMS|
|临时加密/扩窗|一次网格加密后扩窗探测，随后恢复原密度；探测与覆盖确认分别记账|暴露当前attempt的实际窗口/密度及恢复原因，不篡改全局目标；迭代耗尽仍非无解证明|
|原生标量|声明路径、严格有限数值、单位/积分定义匹配|返回来源；缺项明确missing/unsupported/failed，不以0占位。外部Q需求解前启用相应配置|
|三维场匹配|已保存E/H、共同物理域、掩码、体积权重和采样收敛|只返回已有诊断及工件摘要；PEC背景/真空域第一版不升级成任意多材料CAD支持|
|结果读取|S4禁止读取正在仿真的工程；interactive仅允许保存后读，未保存可能陈旧或畸形|只读已采用快照/已关闭工程，或框架已验证的输出；不把allow_interactive=True当事务隔离|

官方Python Project.close文档明确不保存；Project.save默认include_results=True。二者与VBA Project.Quit/Save不是可机械互换的名称。未来迁移须显式保存目标和结果、回读可用性、再关闭自身Project/DE，仍保留收尾证据。

## 6. 当前缺口与实施门禁

发现一项需实施时处理的具体缺口：[预处理宏](../data/preprocess_hom_parameters_v1.vb) `BindHomSolverSettings`当前直接调用AddToHistory，随后日志明确写returned-not-verified，未接收其Boolean。既有Rebuild/输出检查不能单独证明目标历史块已成功登记；不能把“配置已请求”展示为“配置已验证”。本轮仅登记，不擅自改运行功能。后续应检查返回值、记录历史块身份并回读目标设置；构造AddToHistory=False/异常的静态及真实副本验收。

|优先级|实施前必须完成|通过证据|
|---|---|---|
|M0|冻结能力声明：版本、接口通道、对象scope、模型/结果限制；明确不存在的能力|能力矩阵不因import成功或配置字段存在自动置true；未知为unknown|
|M0/M1|查询仅已采用工件；加入来源、单位、revision、可用性；区分CST run id|子工程同名树项、run0重复、缺项、运行中/被清理快照、revision变化离线用例|
|前置缺口|验证预处理AddToHistory返回及设置回读；保留表达式|失败不发布预处理成功；正常路径离线测试及另行授权副本Gate|
|M2|身份与锁在Runner内部原子验证；取消请求与已停止分别展示|假Worker真实子进程、响应丢失、同ID重放、多界面争用、不重复采用|
|后续原生后端|固定Python ABI、版本、明确DE/Project句柄；同步/异步、abort/pause、timeout及异常状态实测|两自有副本+旁观实例、不影响其他工程；取消后结果有效性、资源释放、重连及退出完整Gate|
|M5|现有批宏链的小网格真实MCP副本验收|求解次数/模式/采用唯一/覆盖与表达式/结果哈希/安全退出分别核对|

首版不新增通用VBA执行、任意CAD/材料编辑、官方Solver暂停恢复、三维原始场SDK读取或MPI HOM声明。已有官方接口可减少未来自建控制代码，但不自动替代当前持久化协议和恢复事实。

## 7. 本轮验收范围

仅官方本机文档与可见源码审查、文档同步及离线回归；没有真实CST、SDK导入、暂停/中止或多工程试验。测试结果在当前状态记录；不能把本设计当作14个工具或原生Python后端已实现。

2026-10-28定向离线：29 passed（3.46s），含documentation_index_test、managed_cstworker_test、hom_native_results_test；报告artifacts/mcp-cst-scope-20261028.xml。未修改源代码；没有新增真实运行证据。
