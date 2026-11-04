# GEO-2–GEO-4共用执行与公共接口

更新：2026-11-04。本页说明当前实现；[设计§15](geometry-selection-interface-design.md#15-设置唯一归属原子分块与显式依赖)说明分块原则，早期离线批次见设计§12–14，不能把旧测试数字当作当前源码验收。最终许可由本地独立GEO校准记录及其源版本/知识库证据决定，不因本页文字或声明投影放行。

## 当前执行链

同一ApplicationService/Runner槽接收create/apply/configure/save/close。GEO沿用不可变revision、CAS、执行意图、提交和响应对账；几何保存和仿真定义分别核验。没有第二套模型状态、任务队列或执行服务。

```text
类型化声明修改 → 参数/实体/归属/依赖检查
→ 共用history_program.partition → 独立程序核对/源图
→ 独立GEO原生版本门禁 → 持久执行意图
→ 归属绑定后的新MWS候选 → 参数表/说明一次写入
→ 每块MacroCheckThis → 检查ErrObject → AddToHistory
→ Rebuild/SaveAs → 标记及所属进程标准退出核对
→ B1读回实际Model.mod/参数表 → 保存/重开两会话原生观察
→ geometry_saved，或再经仿真设置/定义验证得到ready
→ 原ManagedCSTWorker/采集/RunStore/后处理来源冻结/采用/导出
```

候选总是新建；不会追加同caption来更新旧工程，也不会在失败半成品上自动续写几何。旧revision、原工程及已确认结果保持不变。HOM频率扫描继续原Worker复用链，本次不将其改成每个窗口重建。

## 原子分块与读取职责

|入口|实际职责|
|---|---|
|history_program.partition/validate|把既有类型化body降低为完整功能块，核对实际语句的唯一设置写入、初始化顺序、组件/实体依赖及声明一致性；输出block-contracts.json|
|geometry_codegen.render_geometry_history|几何语义中间产物；其中setup仅供共享投影复用，不再作为一个大执行块提交CST|
|definition_editing.render_edit_macro/prepare_candidate_artifacts|A1与GEO共用外层模板，生成物理program、宏、参数及源图；准备本身不启动CST|
|managed_history.extract_program/verify_saved_program|从B1校验过的Model.mod提取框架caption，核对实际块数/顺序/body及符号表达式；不压缩任意用户历史|
|winwrap_checks.execution_definition_map|物理块/行、参数表达式/说明、feature及实现入口到完整宏的诊断映射；不是执行许可或完整编译器|
|NativeDefinitionVerifier._phases|A1/GEO共用保存/重开副本生命周期；未确认关闭不进入下一会话|
|definition_geometry|实体存在/材料/体类型/体积及整体结构/计算域观察；原始观测和声明分别保存|

GEO执行块为单位、WCS、每个组件和每个feature；附带仿真时再加求解器族、背景、边界、求解器上下文、频率、网格密度和模式数。A1综合历史也已拆为对应职责。单位统一为mm/MHz，频率单位由单位块唯一写入，仿真块不重复覆盖。

EigenmodeSolver.Reset只在初始化上下文出现，完整恢复该profile要求的求解器属性；随后频率配置先于全局Mesh.MeshType和密度设置。此顺序同时接受现有严格投影和实际读回核对，不能把Reset移至已配置设置之后。基本体仍保持Reset/属性/Create在同一块；不允许临时builder状态隐式跨块。

依赖允许跨非相邻feature，保留声明顺序；不自动拓扑排序。几何操作对实体的更新/消费可连续发生，不能把合法的两次平移当重复设置删除。参数/实体依赖由现有声明投影推导；已消费、前向、缺失及悬空选择成员拒绝。当前生成profile不需要跨块临时builder连续段：将完整操作拆开会被生命周期/声明检查拒绝，不引入新的段调度器。

## 公开操作及返回

MCP仍是14个工具。apply_model_changes已实际接受geometry_profile，save_project已实际接受validation_target；这些字段不仅出现在Schema中，也进入函数及同一Runner请求。HTTP和CLI继续共用原start定义payload；GUI增加RunnerController.submit_definition适配入口，沿用同一控制权/异步槽。没有新增CAD画布或单独的GUI几何执行后端。

1. create_project创建受管空MWS，得到document_id与document_revision。
2. apply_model_changes明确geometry_profile="geometry-v1"，设置参数、组件、基本体/布尔/平移/删除及文档选择集；修改使用update_feature/remove_feature。
3. 几何目标使用save_project(validation_target="geometry")，实际保存重开和几何核验通过后geometry_saved=true、ready=false、definition_revision=null。
4. 仿真目标先在GEO变更中显式set_background/set_boundaries，再configure_simulation，最后save_project(validation_target="simulation")。只有保存/重开、几何及设置证明通过才ready=true并产生definition_revision。
5. submit_run仍只接收document_id与definition_revision；结果通过既有查询/JSON/CSV导出，不允许调用者传任意宏或路径来绕过验证。

每次写操作都使用最新expected_document_revision和独立request_id。网络响应丢失先查询原run/operation；相同请求幂等返回，已有意图没有提交时进入对账，不重新执行CST。geometry-only文档可close(save)，但不能据此派发仿真；关闭草稿须显式discard_candidate。

几何目标只承诺参数和几何。尚未configure_simulation时，背景/边界可以保留为待配置声明，不据geometry_saved声称它们已获得原生设置确认；完整configure后才生成并核对SIM设置块。使用仿真目标必须提供全部配置。

CLI例：先连接已有Runner，再执行`python -m csttool.runner_client --project <project> start --config <definition-request.json>`；文件内容即同一kind="definition"业务请求，不引入另一种CLI模型格式。查询不会自动启动CST。

## 支持范围

|项目|当前profile|
|---|---|
|宿主/作用域|CST2022、新建受管MWS、root 3D；2022大版本行为沿用户既定假设，具体实测构建记录在证据中|
|几何|Brick、XYZ实心/空心Cylinder、完整Sphere、单次平移、同组件同材料Add/Subtract/Intersect、删除|
|材料|几何保存可声明Vacuum/PEC；首阶段仿真仅支持PEC背景内的存活Vacuum实体|
|设置|HF Eigenmode、Default/Tet、密度Version 1近/远同值、关闭自适应、nmodes=1、六面electric/无对称/背景padding=0、损耗仅后处理|
|后处理|模式1的Frequency与R_over_Q，beta=1、中心全长线、XYZ轴；范围来自保存/重开时整体计算域原生观察，随结果冻结实现及宏hash|
|持久化|参数表达式/说明在参数表；结构与设置在历史；身份/选择集在不可变文档元数据|
|路径/输入|沿用受限表达式及现有ASCII原生宏路径范围；不接收任意VB、导入历史编辑或跨scope写入|

geometry_projection仍是声明投影，geometry_verification才携带实际保存/重开的观察。基本体和其平移可对比解析体积/整体范围；一般CSG输出只核对已保存命令、对象存活/消费、材料、纯实体类型和正体积，不能宣称任意CAD等价、单连通或精确逐实体包围盒。

整体范围使用Boundary.GetStructureBox/GetCalculationBox，**不是**Solid.GetLooseBoundingBoxOfShape。后者有结构宏执行限制，本profile不调用、不冒充紧包围盒；也不暴露基于未校准index的枚举接口。文档选择集不表示创建了CST Group；面/边选择、拓扑重绑定、多材料仿真、其它求解器/边界/自适应/多模仍是独立后续范围。

## 失败、停止及恢复

定义构造宏每阶段检查本候选目录的cancel.request。Python收到显式停止后只通知拥有的宏，继续等待标准关闭；宏在步骤边界退出，不能打断一个正在执行的CST命令并假设回滚。重开验证在每会话开始前检查取消，不因停止再启动下一会话。

会话发现由definition_sessions.definition_status_paths共用，覆盖嵌套GEO验证目录。服务在项目锁下核对整个定义catalog，独立副本验证器仅核对本候选目录，避免遗漏旧会话或误扫其它工程/验收目录。几何目标的原生验证全过程持有项目锁；未知退出在新意图/原生派发前阻断。

语法/应用/重建/保存失败保留原错误、nonce、当前块、最后已应用块及源图。最后已应用块只用于诊断，不授权从该处续写。完成标记、保存产物和标准退出分别核验；保存成功但退出未确认、失败后残留completed、回执身份不符均不采用。

未提交的失败候选可在所属会话确认关闭后由现有恢复流程退役；已提交但响应未写入时补写，不回退current或重复原生执行。后续修正声明用新revision/新操作构建；不损坏旧结果，不强杀其它CST实例。普通求解无固定总时限，启动/通信/收尾仍有界。

独立data/geometry-calibration.json绑定源版本与knowledge-base/geometry-calibration-20261104.json；几何和仿真目标分别授权，旧A1 stamp不能放行GEO。缺失/过期/未知目标在执行意图前拒绝，不靠刷新hash伪造许可。A1仍有自己的校准门禁。

## 验收记录与边界

本批真实Z向小网格Pillbox已返回1147.42737641147MHz、R/Q=58.1026729651567Ω，R=100mm、H=2*R、密度2、模式1。解析TM010频率1147.425278MHz供5%测试门限对照；这不是任意模型的模式身份/网格收敛证明。生命周期日志确认一次Start，结果采用及标准关闭已核对。

C1–C7及GEO-4当前源码串行矩阵已通过，证据为[独立校准](../knowledge-base/geometry-calibration-20261104.json)（源版本绑定）。覆盖基本体/空心体、非默认局部WCS下显式全局平移、三类布尔、删除/身份/参数原表达式重建、声明修改、不发布受控Err.Raise失败及步骤边界停止。X/Y/Z各一次真实Start及正常关闭，Frequency和中心RQ轴间差异小于5%；不是网格收敛或任意模式身份证明。

|轴（R=100mm，H=2R，密度2）|Frequency/MHz|中心线R/Q/Ω|
|---|---:|---:|
|X|1147.42796431385|58.0234672945232|
|Y|1147.42746788338|57.9725643515358|
|Z|1147.42737641147|58.1026729651487|

现代官方SDK公开链已通过新建→GEO声明→几何保存（ready=false）→配置→仿真保存（ready=true）→一次Start→采用/JSON与CSV导出及重复导出→close(save)→Runner正常退出。该模型L=R、密度4，保留表达式，返回1147.42692991921MHz与223.541439593232Ω，不能与上表不同长度模型直接比较RQ。轻量结果、来源hash、实际Start日志路径及退出事实见[本批生产记录](../knowledge-base/geometry-production-20261104.json)。这是新SDK进程验收，desktop_host=false。

退化情形：不相交/相切并集能生成同名纯实体且正体积，不能推断单连通；不相交/相切交集及完全相减输入未发布，CST批处理可能退出0但不产出所需Model.run标记，故明确拒绝，内部原因未核实。只凭退出0不能采用。现代SDK的字段实际分发和假Worker闭环已有独立测试；它们不能替代真实CST，也不能冒充Codex桌面重新加载后的对话验收。

本轮2424个可再生成CST/原始二进制文件已清理（280459818字节）；原始模型/场需重新生成。保留轻量报告、宏/日志、Spec/参数和哈希；已结束pytest的轻量证据经ZIP校验后集中保留，删除临时副本。artifacts不保证随Git迁移。索引/静态测试只证明其范围内的一致性，不以历史473项数字替代本批代码验收。

最终离线回归：功能/故障/现代SDK/文档及源码包组合514项通过；GUI/Runner恢复退出组合89项通过，共603个不同测试项。重复运行不累加。后者纠正4个旧断言：Windows venv启动器PID不必等于Runner PID（改核实启动进程树及实际退出）、明确控制权拒绝不制造transport unknown、等待cancel_start持久接管后再核对恢复状态。未因此修改已校准运行源码。最终文档/登记/源码包63项复核通过（与514集合重叠，不累加）。

本批A1原生许可更新被自动审批拒绝（授权范围为GEO-2–4），data/winwrap-a1-calibration.json保持原字节且失效；未通过修改hash、借GEO许可或间接执行绕过。独立GEO目标许可已由真实矩阵发布。新增范围仍需各自授权及校准。
