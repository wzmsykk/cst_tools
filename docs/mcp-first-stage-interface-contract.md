# 首阶段统一接口契约：参数化建模到单次仿真结果

日期：2026-10-28。**静态冻结，运行未实现。** 本文细化[首阶段G01–G08门禁](mcp-first-stage-conversational-gate.md)，与[公共控制/错误/幂等契约](unified-interface-contract.md)共同组成A1接口。CST依据见[本轮官方文档与作用域核查](../knowledge-base/cst-first-stage-api-semantics-20261028.md)。GUI/CLI/MCP使用同一业务模型/服务，不维护旧调用兼容。

## 1. 首阶段可表达的物理问题

固定项目几何单位mm、频率MHz；新建MWS三维工程、全局坐标、已有内建Vacuum实体、PEC背景、六面electric边界、无对称/端口/激励。支持参数化实心圆柱，axis可x/y/z；首个验收用Z轴。Tet/Default Eigenmode、关闭自适应、nmodes=1、有限正频段、beta=1全范围轴向R/Q。首阶段不提供自定义材料、多实体布尔、局部WCS、开边界、多物理模块或任意VBA。

axis是实体/积分轴，不代表旋转任意角；首阶段“任意轴”指XYZ。后续能力可以扩展，不改变现行复杂后处理已支持XYZ的事实。没有端口不要求外部Q。PEC背景和electric计算盒边界是不同设置，都显式写入，不互相替代。

圆柱参数不能硬编码成演示：例如R="100"、L="100"，实体outer_radius="R"、axial_range=["-L/2","L/2"]、center=["0","0","0"]、inner_radius="0"。可通过同一set_parameters修改R/L；不能每次向历史追加StoreParameter R=100把后续参数改回常数。

## 2. 身份、前提与返回

project_id是授权工作区，document_id是其中具体工程定义，不等于活动CST窗口；document_revision是不可变定义版本；definition_revision绑定document revision、仿真设置和后处理定义；run_id是一次执行；result_revision是实际已采用结果。客户端不能以文件路径、树项标题或当前窗口代替这些身份。

所有请求对象拒绝未知字段。下面W表示既有request_id、control_handle、expected_instance_id，P表示project_id。编辑额外要求document_id及expected_document_revision；查阅使用document_id及明确document_revision，不用“latest”字符串。ID规则、错误/Artifact、预算及幂等沿公共契约。公共请求≤256KiB，参数≤1024项、每表达式≤8192字符、每批变更≤64项；能力仍受具体对象/资源预算限制。

返回沿用公共业务信封；长操作返回operation receipt，通过get_command/get_run_status跟踪。最终data必须有requested、applied、verification、artifacts及新revision（适用时），不是只给success。verification逐项包含field、expected、observed或null、source、evidence_level（native-query/native-run-database/persisted-history/persisted-metadata/history-replay/artifact-check/unverified）及状态。unverified不得用请求值填成observed。

服务端按单一工程所有权锁验证预期revision及控制权；提交意图持久化后再触发CST。相同request返回原操作事实，不重复建工程/求解/导出。STALE_DOCUMENT、DEFINITION_NOT_READY、MODEL_VALIDATION_FAILED、SETTING_UNVERIFIED、RESULTS_WOULD_BE_INVALIDATED、DOCUMENT_BUSY、MODE_NOT_FOUND、RESOURCE_CLOSE_UNCONFIRMED补充到公共Error.code。错误不得靠中文消息猜分类。

## 3. 九个操作的字段级定义

下表是A1建模/单次仿真子集的唯一新接口，不是现有代码方法；既有公共连接/控制/停止/恢复/诊断操作继续沿用。所有读操作不启动CST；需要活对象验证由明确写操作触发并留操作回执。query只读最近已发布证据，标注其时间/来源。

|操作|输入（除P外）|行为与最终返回|
|---|---|---|
|create_project|W、name、installation_ref、module="mws"、units={length:"mm",frequency:"MHz"}|name为安全ID≤100字符；无覆盖，创建新document。返回document_id/revision、安装身份、空工程工件及bootstrap关闭事实。仅创建，不建模/求解|
|inspect_model|document_id、document_revision；parameter_cursor/limit可选|返回发布定义、参数表达式/数值、实体/材料/边界/单位/mesh/solver证据、simulation refs及有效性。不因查询重建/Save，不伪装实时活动树|
|apply_model_changes|W、document_id、expected_document_revision、changes、invalidate_results=false|有类型变更列表，见第4节。在新候选副本应用/核对/保存重开；旧revision和结果保留。若目标已有结果/会失效须显式true，不能静默删结果。成功发布新document_revision及无结果状态，失败不移动定义指针|
|configure_simulation|W、document_id、expected_document_revision、simulation（第5节）、postprocess（第6节）|只配置，在新候选副本写持久历史并完成求解前重建/保存重开验证；返回新document_revision与definition_revision、设置证据。不会调用Solver.Start|
|save_project|W、document_id、expected_document_revision、verify_reopen=true|验证并固化该revision，不另起求解；定义工件无结果。按新文件集保存/关闭/重开检查，返回hash/manifest。不能对已采用结果路径SaveAs覆盖|
|close_project|W、document_id、expected_document_revision、disposition="save"或"discard_candidate"|无活动运行/编辑才允许；save先确认持久文件，discard只放弃未发布候选。返回operation关闭证据，不停止独立run或其他实例。已无活句柄可确认already_closed，不编造一次Quit|
|submit_run|W、submission={mode:"new",kind:"simulation",document_id,definition_revision}|仅使用已验证不可变定义，新建执行副本；不接受source路径、algorithm对象、运行中覆盖参数、HOM恢复配置。返回受理run_id，执行完成须核对实际结果/采用/收尾|
|get_simulation_results|run_id、result_revision（首查可省略）、mode_index=1|返回当前run已采用频率/RQ、指标状态/单位/积分定义、定义/结果来源与工件；未就绪返回明确状态，不读上轮结果。不是读取HOM checkpoint|
|export_simulation_results|W、run_id、result_revision、formats为json/csv非空去重数组|后台只导出已采用数据至受控results目录；同ID幂等，返回JSON/CSV Artifact。无重新求解/重建；不得从显示字符串重新解析数值|

create/configure/save可能需启动CST，因此都是显式有副作用操作，正常时限有界；若超时但进程未确认关闭，保留candidate及归属记录、阻断同doc新写操作。不能把超时当成可直接重做。

首阶段simulation只支持new；resume明确拒绝UNSUPPORTED_CAPABILITY，不从头静默重算。若已有completion/receipt但采用未完成，recover_project对账并补写既有结果；若Solver被中断且无已确认结果，只能由用户明确新请求计算，不承诺Solver内部续算。HOM已有续跑能力不受此范围定义降级。

## 4. 有类型变更与参数表达式

changes按顺序执行，每项op为以下之一；对象ID与CST名称映射由服务保存，名字不作全局身份。首阶段限制单真空圆柱，不以operation数量绕过物理范围。

|op|字段与约束|CST映射与前提|
|---|---|---|
|set_parameters|values：name→{expression,quantity,description}；quantity为length/frequency/dimensionless，description≤1024字符|Project.StoreParameters批量提交表达式，SetParameterDescription另设；同工程作用域。读取RestoreParameterExpression/GetParameterSValue与RestoreDoubleParameter/GetParameterNValue分别验证表达式/数值|
|ensure_component|component_id：安全ID|先Component.DoesExist，再New；组件必须先于Cylinder。不同ID重名拒绝，不隐式删除/合并|
|create_cylinder|object_id、component_id、axis、center三表达式、axial_range两表达式、outer_radius表达式、inner_radius="0"、material="Vacuum"、segments=0|显式WCS.ActivateWCS("global")；Cylinder.Reset/Name/Component/Material/Axis；按轴设置X/Y/Zrange；Smooth segments=0。Create只能新建，不通过同caption覆盖旧对象|
|set_background|material="PEC"、padding_mm六值均0|Background.Type("pec")及六个Space显式0；无Background.Create/Reset全局其他对象等猜测调用|
|set_boundaries|faces六面均"electric"、symmetry三轴均"none"|Boundary六setter及对称setter，六Getter和Get*Symmetry读回；不是实体金属材料名称|

参数名为`[A-Za-z][A-Za-z0-9_]{0,63}`，拒绝生成器保留名及CST内建冲突，不能在宏中靠同名局部变量“补scope”。A1表达式语法仅数字、已声明参数引用、括号和+−*/，不含换行/引号/语句；为CST表达式建立有界语法树，禁止Python eval。quantity只是服务定义的量纲标签，CST参数数值按工程单位解释，服务需检查合法依赖/维度，不宣称CST会自动执行该标签。

R/L及几何有效值必须有限，outer_radius>0，inner_radius=0，axial_hi>axial_lo。轴向center分量固定0，避免与range起点重复表达轴向平移；其他center为横向中心。Create前解析依赖/查缺参和循环；写后以官方参数读取接口核对，不能用Evaluate字符串求值替代参数依赖刷新。

参数表独立持久；生成的结构/设置历史引用参数，不在每次重放时将当前参数重设旧值。几何字段的简单表达式AST编译为历史内算术与RestoreDoubleParameter叶节点读取，每次重放重新取当前参数值，不把本次求得数字写死进几何历史；不假设所有Double setter都接受表达式字符串。新参数在单独参数阶段写入，结构宏在工程已载入上下文编译；每个历史块唯一caption包含change/object身份，禁止相邻同标题替换被误判为幂等。

## 5. 仿真设置冻结

simulation必填字段：solver="eigenmode"、method="default"、mesh={type:"tet",cells_per_wavelength:4,adaptive:false}、frequency_range_mhz={min:500,max:2000}、frequency_lower_target_mhz=500、requested_modes=1、losses="postprocess_only"。数值由请求提供，例值不是固定演示限制。mesh密度正整数1–1000（新资源上限）；A1该标量明确定义为新工程统一near/far波长密度策略，分别写near=n、far=n，不从旧StepsPerWavelengthTet做等价转换；导入已有不同near/far时保留分区值，不压缩或静默归一；0<min<max，0≤lower_target≤max；A1要求lower_target=min；无total_solver_timeout字段。

|定义|实际CST调用|验证边界|
|---|---|---|
|求解器种类|Project.ChangeSolverType("HF Eigenmode")|GetSolverType读回；不能只设置EigenmodeSolver参数就宣称活动solver已切换|
|频段|Solver.FrequencyRange(min,max)，以工程MHz数值或定义绑定表达式提供|Solver.GetFmin/GetFmax读回。官方说明可能改变mesh、删除结果并询问保存旧结果，故只在无结果的新候选副本上应用|
|频率下限/模式数|SetMethodType("Default","Tet")；SetFrequencyTarget(True,lower)；SetNumberOfModes(CInt(n))|lower是下限，不是最近目标；模式数输入是整数，不直接传"nmodes"表达式字符串。实际模式数结果查询不能用作设置值读回|
|固定Tet网格|Mesh.MeshType("Tetrahedral")；MeshSettings选择Tet，Version=1，StepsPerWaveNear=n、StepsPerWaveFar=n、CellsPerWavelengthPolicy=cellsperwavelength；EigenmodeSolver.SetMeshAdaptationTet(False)|[V05实测](../knowledge-base/cst-tet-density-mesh-calibration-20261028.md)确认本机现代通道对输入步长和实际网格生效。MeshSettings.Get为版本限定实测接口；需支持profile、分别读回，未知版本SETTING_UNVERIFIED。旧StepsPerWavelengthTet在本Version=1上下文不改变网格，不作回退；不是固定cell数或精度保证|
|损耗处理|SetConsiderLossesInPostprocessingOnly(True)|GetConsiderLossesInPostprocessingOnly读回；实际算例仍是理想PEC/真空，不据QFactor默认电导宣称PEC损耗物理结果|

所有需要重建后保持的设置进入经过检查的历史；设置块不能包含Start、Backup、导出或退出调用。AddToHistory Boolean必须检查，随后重建/保存重开；每项记录native-query或history-replay证据，不能将setter返回当已回读。

读回方案已由[设置验证器设计](cst-settings-verifier-design.md)细化：官方原生锚点+按scope解释保存历史/参数+版本校准；持久定义匹配不冒充live getter。Solver.AKSGetNumberOfModes已在本机2022.5的Default/Tet等三分支1/2及重开校准，范围见[实测](../knowledge-base/cst-settings-calibration-20261028.md)。legacy密度与现代near/far不能直接等价，固定Tet路线仍待生效验证。

执行设置补证：[V01/02/04实测](../knowledge-base/cst-solver-settings-readback-calibration-20261028.md)提供版本限定GetDataBaseValue执行快照，不能当求解前当前live设置。验证报告将其单列execution_snapshot，绑定attempt/revision/阶段及hash，方法/网格枚举显式profile，target数值按约6位有效数字比较且保留表达式。Save不刷新旧执行值，Rebuild后可能缺失；缺失不默认False/0，禁止为配置查询额外求解。前置公共历史投影和profile仍未实现，G03不解锁。

**静态已知读回缺口**：当前读过的官方页面没有给出全部method/target/requested_modes/adaptive/density的getter。禁止发明GetStepsPerWavelengthTet之类接口，或用GetDataBaseValue的任意猜测key取值。新契约允许逐项证据等级，但“required_native_readback”项无可靠来源时返回SETTING_UNVERIFIED、禁止发布为ready。待在实施前通过官方页面补查、cst_version只读结构或受控探针确认设置检查器；历史请求文本/实际cell数单独不足以证明所有设置生效。该缺口不阻止冻结字段/错误语义，但阻断相关能力解锁及G03通过。

## 6. 后处理与结果输出

A1 postprocess是[已冻结算子子Schema](postprocess-optimization-subschemas.md)的受限子集：必须包含Frequency（one/index=1）及R_over_Q（one/index=1、beta=1、range=full、axis与圆柱轴一致、相对中心线的offset_mm=0）。模型横向中心非零时后端将局部偏移转换为全局线位置，不能把offset=0误解释为世界原点；首阶段配置要求横向center=0，非零中心返回UNSUPPORTED_CAPABILITY，不在尚未实现的坐标变换上宣称可用；几何接口字段保留但执行能力受此前提约束。新接口暂不开放其他算子，不删除原项目已有算子能力。

Frequency直接取GetModeFrequencyInHz/1e6得到MHz，或核对现有读出中的工程频率单位后转换。R/Q复用Complex算法，基于选定模式E/H和能量，返回Ω及公式/归一化/积分域来源；求解后不StoreParameter、不UPDATE PARAMS、不Rebuild。若现有算法依赖缺失场/网格或返回非有限值，该指标failed，不以0填缺项。

get_simulation_results最终data冻结为：definition_revision、result_revision、task_id、session_id、mode_index、frequency_mhz、metrics（metric_id/value/unit/status/source）、solver_evidence（Start返回及实际模式数）、postprocess_definition、execution_active、session_safety、artifacts；未知为null并附错误，不从当前窗口补来源。mode_index不等于跨参数物理身份。

后台采用成功时自动写受控轻量JSON结果与manifest，export操作可再产生CSV。CSV列固定run_id、definition_revision、result_revision、task_id、mode_index、metric_id、value、unit、status；UTF-8、数值不带本地化千位符。JSON含模型/设置证据、单位与参数表达式引用；工件名由ID生成而非自由显示标题。工程与同名计算目录构成结果快照，不仅复制.cst；大场按任务需求保留/清理并记录availability。

失败仍输出结构化运行/诊断摘要；不产生可误用的成功结果表。G05要求本次frequency有限正值、R/Q有限正值，G06另核对解析频率，不以相同数量/模式名代替物理检查。

## 7. 实现通道与作用域冻结

创建与编辑/计算是同一CST后端的不同操作，不是两套业务框架：

1. 空工程bootstrap拟用**所选安装版本自带的Python及官方cst.interface**的专用短进程：新建独立DE→new_mws→保存空白工程→显式close Project/DE并确认进程归属与退出。不连接any/active；不让MCP/GUI Python直接加载ABI不匹配的扩展。CST2022自带运行时与现代MCP Python3.12隔离，只传受控操作/结果，不开放通用脚本执行。该通道仅创建/保存空壳，不复用已编译宏跨OpenFile重建。
2. 有了保存的空工程后，编辑/配置/保存验证统一使用**已加载工程的Model/3D/Model.run**，通过官方`-m -b <candidate.cst>`进入正确3D参数scope。主宏不再OpenFile；读回Project.GetProjectPath("Project")等归属证据，GetOwnProject代表当前工程，不是宿主Application。
3. 单次求解基于该已发布definition创建独立执行副本。拟让现有Managed执行后端增加明确single-simulation路径；不调用HOM预处理自动绑定fmin/fmax/nmodes/cell去覆写通用定义，不建立第二个Worker类/任务库。所有求解、PPS、快照、completion/ACK、采用及v2收尾规则共用，实际迁移点待实施。
4. 多进程是官方接口ABI/生命周期边界，不是多个CST同时操作同一工程；同一项目CST操作串行，bootstrap必须关闭确认后再启动批宏。官方Python.close不保存，必须先save；它的close语义不等于VBA Project.Quit，后者可能询问保存。运行中的批任务用正常宏返回并验证收尾，不在宏内抢关sheet。

bootstrap路线是本轮设计选择，未运行/未宣称已通过；不满足官方运行时可用性或关闭门禁时能力返回unsupported/unverified，不自动退回全局OLE Active3D或任意RunMacro路径。当前旧Managed已验证的批宏路线是复用基础，不等于上述新建/编辑路径已验收。

## 8. 持久化与版本发布边界

|内容|持久化归属|影响与限制|
|---|---|---|
|参数名/表达式/说明|项目参数表+定义manifest|StoreParameters非原子事务承诺；失败候选弃用，不回写已发布定义。R/L表达式保留|
|实体/组件/WCS构造、背景/边界、mesh和solver设置|结构历史+定义manifest|历史执行后检查；完整Rebuild会删除结果，所以只对无结果候选操作；隐藏显示不是几何持久化保证|
|postprocess定义|框架definition manifest及版本化宏依赖|不是自动生成CST Result Template；保存.cst不等于保存框架配置，definition必须打包两者|
|批宏Model.run/协议路径|每次操作/会话私有目录|从快照打开前重写本次脚本，禁止重放旧session；宏路径不是永久模型定义|
|结果/场/工件|不可变结果文件集、hash、采用记录|不因编辑新revision覆盖；被清理后返回missing/needs_regeneration，不把报告当原始结果仍可访问|
|编辑/运行/关闭事实|公共命令记录/资源归属/回执|独立于.cst Save；收到Save返回不等于应用安全关闭|

候选发布顺序：意图→创建副本→参数/历史执行→检查返回→重建→结构/设置验证→保存→正常关闭→重开只读核验→关闭→工件/hash manifest完成→原子发布revision指针。CST文件与配套目录不具备跨文件原子事务，发布前读者不可见；失败保留候选诊断，不回滚猜测的半变更。

这不是要求每次编辑都清空重建全部历史。未变的参数与结构保留，首阶段只支持新建实体和参数变化；通用删除/替换历史块另设计。需要扩大对象类型时扩展typed schema，不以任意宏绕过。

## 9. 静态验收与待解锁门禁

本轮冻结输入、结果和失败语义，不冻结不存在的getter，也不以安装文档证明运行成功。下一步需：

- 固定bootstrap运行时/新建保存/关闭、三维参数scope、内建Vacuum存在性及圆柱重建探针；原工程/其他实例不受影响。
- 解决其余设置验证器缺口，并按V05已校准现代Tet通道实现版本profile；不再依赖本Version=1中无网格影响的旧setter，不将未知版本或Version=0作回退。
- 不在结构宏/历史重放中调用Solid.GetLooseBoundingBoxOfShape；官方限制该查询用于后处理，且它是非紧包围盒，不能用作圆柱精确尺寸等式验证。采用合法阶段的体积/点归属/结构盒与参数证据组合，独立选择核查方式。
- 对create/change/configure/save/close/single-run/output逐项设计正反例、响应丢失/同ID/过期revision/部分发布/关闭不明；假后端只证明流程，真实Pillbox G01–G08仍需授权验收。

实际新接口、bootstrap、设置检查器、simulation结果读写均未实现；本轮没有生成运行宏、调用CST或改pyproject。后续实现必须同步索引/状态/TODO，清除旧入口而非保留兼容分支。

## 附录：请求Schema设计工件

文档内JSON是首阶段请求的静态冻结工件，不是运行模块。faces顺序xmin/xmax/ymin/ymax/zmin/zmax；symmetry为x/y/z。跨字段规则（频段顺序/下限相等、参数依赖/语法与保留名、PPS两个不同方法各一次且ID唯一、axis与几何一致、几何有效性、归属/版本/能力及有限性）必须由同一公共验证器另检查；本轮不实现它。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:csttools:design:first-stage:1",
  "type": "object",
  "properties": {
    "operation": {
      "enum": [
        "create_project",
        "inspect_model",
        "apply_model_changes",
        "configure_simulation",
        "save_project",
        "close_project",
        "submit_run",
        "get_simulation_results",
        "export_simulation_results"
      ]
    },
    "project_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
    },
    "request_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
    },
    "control_handle": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
    },
    "expected_instance_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
    },
    "arguments": {
      "type": "object"
    }
  },
  "required": [
    "operation",
    "project_id",
    "arguments"
  ],
  "additionalProperties": false,
  "oneOf": [
    {
      "properties": {
        "operation": {
          "const": "create_project"
        },
        "arguments": {
          "$ref": "#/$defs/create_project"
        }
      },
      "required": [
        "request_id",
        "control_handle",
        "expected_instance_id"
      ]
    },
    {
      "properties": {
        "operation": {
          "const": "inspect_model"
        },
        "arguments": {
          "$ref": "#/$defs/inspect_model"
        }
      },
      "not": {
        "anyOf": [
          {
            "required": [
              "request_id"
            ]
          },
          {
            "required": [
              "control_handle"
            ]
          },
          {
            "required": [
              "expected_instance_id"
            ]
          }
        ]
      }
    },
    {
      "properties": {
        "operation": {
          "const": "apply_model_changes"
        },
        "arguments": {
          "$ref": "#/$defs/apply_model_changes"
        }
      },
      "required": [
        "request_id",
        "control_handle",
        "expected_instance_id"
      ]
    },
    {
      "properties": {
        "operation": {
          "const": "configure_simulation"
        },
        "arguments": {
          "$ref": "#/$defs/configure_simulation"
        }
      },
      "required": [
        "request_id",
        "control_handle",
        "expected_instance_id"
      ]
    },
    {
      "properties": {
        "operation": {
          "const": "save_project"
        },
        "arguments": {
          "$ref": "#/$defs/save_project"
        }
      },
      "required": [
        "request_id",
        "control_handle",
        "expected_instance_id"
      ]
    },
    {
      "properties": {
        "operation": {
          "const": "close_project"
        },
        "arguments": {
          "$ref": "#/$defs/close_project"
        }
      },
      "required": [
        "request_id",
        "control_handle",
        "expected_instance_id"
      ]
    },
    {
      "properties": {
        "operation": {
          "const": "submit_run"
        },
        "arguments": {
          "$ref": "#/$defs/submit_run"
        }
      },
      "required": [
        "request_id",
        "control_handle",
        "expected_instance_id"
      ]
    },
    {
      "properties": {
        "operation": {
          "const": "get_simulation_results"
        },
        "arguments": {
          "$ref": "#/$defs/get_simulation_results"
        }
      },
      "not": {
        "anyOf": [
          {
            "required": [
              "request_id"
            ]
          },
          {
            "required": [
              "control_handle"
            ]
          },
          {
            "required": [
              "expected_instance_id"
            ]
          }
        ]
      }
    },
    {
      "properties": {
        "operation": {
          "const": "export_simulation_results"
        },
        "arguments": {
          "$ref": "#/$defs/export_simulation_results"
        }
      },
      "required": [
        "request_id",
        "control_handle",
        "expected_instance_id"
      ]
    }
  ],
  "$defs": {
    "Parameter": {
      "type": "object",
      "properties": {
        "expression": {
          "type": "string",
          "minLength": 1,
          "maxLength": 8192
        },
        "quantity": {
          "enum": [
            "length",
            "frequency",
            "dimensionless"
          ]
        },
        "description": {
          "type": "string",
          "maxLength": 1024
        }
      },
      "required": [
        "expression",
        "quantity",
        "description"
      ],
      "additionalProperties": false
    },
    "Change": {
      "oneOf": [
        {
          "type": "object",
          "properties": {
            "op": {
              "const": "set_parameters"
            },
            "values": {
              "type": "object",
              "minProperties": 1,
              "maxProperties": 1024,
              "propertyNames": {
                "pattern": "^[A-Za-z][A-Za-z0-9_]{0,63}$"
              },
              "additionalProperties": {
                "$ref": "#/$defs/Parameter"
              }
            }
          },
          "required": [
            "op",
            "values"
          ],
          "additionalProperties": false
        },
        {
          "type": "object",
          "properties": {
            "op": {
              "const": "ensure_component"
            },
            "component_id": {
              "type": "string",
              "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
            }
          },
          "required": [
            "op",
            "component_id"
          ],
          "additionalProperties": false
        },
        {
          "type": "object",
          "properties": {
            "op": {
              "const": "create_cylinder"
            },
            "object_id": {
              "type": "string",
              "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
            },
            "component_id": {
              "type": "string",
              "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
            },
            "axis": {
              "enum": [
                "x",
                "y",
                "z"
              ]
            },
            "center": {
              "type": "array",
              "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 8192
              },
              "minItems": 3,
              "maxItems": 3
            },
            "axial_range": {
              "type": "array",
              "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 8192
              },
              "minItems": 2,
              "maxItems": 2
            },
            "outer_radius": {
              "type": "string",
              "minLength": 1,
              "maxLength": 8192
            },
            "inner_radius": {
              "const": "0"
            },
            "material": {
              "const": "Vacuum"
            },
            "segments": {
              "const": 0
            }
          },
          "required": [
            "op",
            "object_id",
            "component_id",
            "axis",
            "center",
            "axial_range",
            "outer_radius",
            "inner_radius",
            "material",
            "segments"
          ],
          "additionalProperties": false
        },
        {
          "type": "object",
          "properties": {
            "op": {
              "const": "set_background"
            },
            "material": {
              "const": "PEC"
            },
            "padding_mm": {
              "type": "array",
              "items": {
                "const": 0
              },
              "minItems": 6,
              "maxItems": 6
            }
          },
          "required": [
            "op",
            "material",
            "padding_mm"
          ],
          "additionalProperties": false
        },
        {
          "type": "object",
          "properties": {
            "op": {
              "const": "set_boundaries"
            },
            "faces": {
              "type": "array",
              "items": {
                "const": "electric"
              },
              "minItems": 6,
              "maxItems": 6
            },
            "symmetry": {
              "type": "array",
              "items": {
                "const": "none"
              },
              "minItems": 3,
              "maxItems": 3
            }
          },
          "required": [
            "op",
            "faces",
            "symmetry"
          ],
          "additionalProperties": false
        }
      ]
    },
    "Simulation": {
      "type": "object",
      "properties": {
        "solver": {
          "const": "eigenmode"
        },
        "method": {
          "const": "default"
        },
        "mesh": {
          "type": "object",
          "properties": {
            "type": {
              "const": "tet"
            },
            "cells_per_wavelength": {
              "type": "integer",
              "minimum": 1,
              "maximum": 1000
            },
            "adaptive": {
              "const": false
            }
          },
          "required": [
            "type",
            "cells_per_wavelength",
            "adaptive"
          ],
          "additionalProperties": false
        },
        "frequency_range_mhz": {
          "type": "object",
          "properties": {
            "min": {
              "type": "number",
              "exclusiveMinimum": 0
            },
            "max": {
              "type": "number",
              "exclusiveMinimum": 0
            }
          },
          "required": [
            "min",
            "max"
          ],
          "additionalProperties": false
        },
        "frequency_lower_target_mhz": {
          "type": "number",
          "minimum": 0
        },
        "requested_modes": {
          "const": 1
        },
        "losses": {
          "const": "postprocess_only"
        }
      },
      "required": [
        "solver",
        "method",
        "mesh",
        "frequency_range_mhz",
        "frequency_lower_target_mhz",
        "requested_modes",
        "losses"
      ],
      "additionalProperties": false
    },
    "PPS": {
      "type": "array",
      "minItems": 2,
      "maxItems": 2,
      "items": {
        "oneOf": [
          {
            "type": "object",
            "properties": {
              "metric_id": {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
              },
              "method_id": {
                "const": "Frequency"
              },
              "settings": {
                "type": "object",
                "properties": {
                  "mode": {
                    "type": "object",
                    "properties": {
                      "selection": {
                        "const": "one"
                      },
                      "index": {
                        "const": 1
                      }
                    },
                    "required": [
                      "selection",
                      "index"
                    ],
                    "additionalProperties": false
                  }
                },
                "required": [
                  "mode"
                ],
                "additionalProperties": false
              },
              "on_unavailable": {
                "const": "fail",
                "default": "fail"
              }
            },
            "required": [
              "metric_id",
              "method_id",
              "settings"
            ],
            "additionalProperties": false
          },
          {
            "type": "object",
            "properties": {
              "metric_id": {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
              },
              "method_id": {
                "const": "R_over_Q"
              },
              "settings": {
                "type": "object",
                "properties": {
                  "mode": {
                    "type": "object",
                    "properties": {
                      "selection": {
                        "const": "one"
                      },
                      "index": {
                        "const": 1
                      }
                    },
                    "required": [
                      "selection",
                      "index"
                    ],
                    "additionalProperties": false
                  },
                  "integration_line": {
                    "type": "object",
                    "properties": {
                      "axis": {
                        "enum": [
                          "x",
                          "y",
                          "z"
                        ]
                      },
                      "offset_mm": {
                        "type": "array",
                        "items": {
                          "const": 0
                        },
                        "minItems": 3,
                        "maxItems": 3
                      },
                      "beta": {
                        "const": 1
                      },
                      "range": {
                        "const": "full"
                      }
                    },
                    "required": [
                      "axis",
                      "offset_mm",
                      "beta",
                      "range"
                    ],
                    "additionalProperties": false
                  }
                },
                "required": [
                  "mode",
                  "integration_line"
                ],
                "additionalProperties": false
              },
              "on_unavailable": {
                "const": "fail",
                "default": "fail"
              }
            },
            "required": [
              "metric_id",
              "method_id",
              "settings"
            ],
            "additionalProperties": false
          }
        ]
      }
    },
    "create_project": {
      "type": "object",
      "properties": {
        "name": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "installation_ref": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "module": {
          "const": "mws"
        },
        "units": {
          "type": "object",
          "properties": {
            "length": {
              "const": "mm"
            },
            "frequency": {
              "const": "MHz"
            }
          },
          "required": [
            "length",
            "frequency"
          ],
          "additionalProperties": false
        }
      },
      "required": [
        "name",
        "installation_ref",
        "module",
        "units"
      ],
      "additionalProperties": false
    },
    "inspect_model": {
      "type": "object",
      "properties": {
        "document_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "document_revision": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        "parameter_cursor": {
          "type": "string",
          "maxLength": 4096
        },
        "parameter_limit": {
          "type": "integer",
          "minimum": 1,
          "maximum": 500,
          "default": 100
        }
      },
      "required": [
        "document_id",
        "document_revision"
      ],
      "additionalProperties": false
    },
    "apply_model_changes": {
      "type": "object",
      "properties": {
        "document_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "expected_document_revision": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        "changes": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/Change"
          },
          "minItems": 1,
          "maxItems": 64
        },
        "invalidate_results": {
          "type": "boolean",
          "default": false
        }
      },
      "required": [
        "document_id",
        "expected_document_revision",
        "changes"
      ],
      "additionalProperties": false
    },
    "configure_simulation": {
      "type": "object",
      "properties": {
        "document_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "expected_document_revision": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        "simulation": {
          "$ref": "#/$defs/Simulation"
        },
        "postprocess": {
          "$ref": "#/$defs/PPS"
        }
      },
      "required": [
        "document_id",
        "expected_document_revision",
        "simulation",
        "postprocess"
      ],
      "additionalProperties": false
    },
    "save_project": {
      "type": "object",
      "properties": {
        "document_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "expected_document_revision": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        "verify_reopen": {
          "const": true,
          "default": true
        }
      },
      "required": [
        "document_id",
        "expected_document_revision"
      ],
      "additionalProperties": false
    },
    "close_project": {
      "type": "object",
      "properties": {
        "document_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "expected_document_revision": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        "disposition": {
          "enum": [
            "save",
            "discard_candidate"
          ]
        }
      },
      "required": [
        "document_id",
        "expected_document_revision",
        "disposition"
      ],
      "additionalProperties": false
    },
    "submit_run": {
      "type": "object",
      "properties": {
        "submission": {
          "type": "object",
          "properties": {
            "mode": {
              "const": "new"
            },
            "kind": {
              "const": "simulation"
            },
            "document_id": {
              "type": "string",
              "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
            },
            "definition_revision": {
              "type": "string",
              "pattern": "^[a-f0-9]{64}$"
            }
          },
          "required": [
            "mode",
            "kind",
            "document_id",
            "definition_revision"
          ],
          "additionalProperties": false
        }
      },
      "required": [
        "submission"
      ],
      "additionalProperties": false
    },
    "get_simulation_results": {
      "type": "object",
      "properties": {
        "run_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "result_revision": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        "mode_index": {
          "const": 1,
          "default": 1
        }
      },
      "required": [
        "run_id"
      ],
      "additionalProperties": false
    },
    "export_simulation_results": {
      "type": "object",
      "properties": {
        "run_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "result_revision": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        "formats": {
          "type": "array",
          "items": {
            "enum": [
              "json",
              "csv"
            ]
          },
          "uniqueItems": true,
          "minItems": 1,
          "maxItems": 2
        }
      },
      "required": [
        "run_id",
        "result_revision",
        "formats"
      ],
      "additionalProperties": false
    }
  }
}
```

本轮验收记录：文档内请求Schema13定义，17正例/25反例通过（artifacts/first-stage-cst-contract-20261028/schema-checks.json）；跨字段校验/归属/实际CST效果未实施。既有文档/生成器/Managed/预处理定向离线53 passed（1.93s），artifacts/first-stage-contract-offline-20261028.xml；无新增真实CST证据。
