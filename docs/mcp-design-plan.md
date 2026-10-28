# CST Tools MCP 接入设计与分阶段计划


架构决策更新：以[MCP优先、CST Tools共用底层](mcp-framework-static-design.md)为最新约束。此前mcp_service专属业务层及“仅允许Runner小幅增量”的限制已被替代：按统一契约迁移旧底层，GUI/CLI/MCP共用公共应用服务；旧源码映射仍是现状证据，不是目标接口保证。

日期：2026-10-28。状态：**仅设计，M0–M5均未实施**。未增加SDK依赖、工具服务或新的Runner端点；本轮没有启动CST。现有独立Runner属于E0–E5实现，MCP不等于E6–E9远程/分布式已实现。

## 0. 标准先行：2026-07-28协议基线

先完成[官方规范完整阅读记录](../knowledge-base/mcp-protocol-reading-20261028.md)，再审查本计划；[符合性与验收矩阵](mcp-protocol-conformance.md)是进入M0/M1的前置标准。COMSOL MCP仅用于实现比较，不作为标准。首次计划只引用2025-06-18三篇规范，覆盖不足，现已修正。

规范正文及TypeScript定义采用正式日期版本2026-07-28；官网原文哈希与官方Schema固定提交可复核。不得手工混合旧initialize协议与现代逐请求元数据。M0必须先验证官方SDK和目标宿主实际支持；若SDK/宿主不支持所选现代基线，记录阻塞并升级或更换支持组合；不设计旧版降级路径。不为兼容预先自研双协议栈。

首版只声明tools能力，静态工具目录，不启用可选Tasks、Resources、Prompts、Completions、Elicitation或已弃用Roots/Sampling/Logging。现代版必需的server/discover、逐请求版本/能力、resultType及缓存提示由SDK按规范处理并验收。业务run_id是显式运行句柄，不是MCP Task；MCP消息complete/受理/求解完成分别表达。

## 1. 目标与范围

总体功能目标为[对齐COMSOL MCP工作流](comsol-mcp-functional-alignment.md)：工程管理、参数表达式、几何/选择、材料/边界/端口、网格、求解/扫参/优化和结果分析/导出；GUI/CLI/MCP共用底层。已有工程HOM的14操作是A1首阶段子集，不能作为最终范围。新增工程编辑/通用分析须继续按CST官方文档冻结子契约，不按COMSOL名称猜语义。

```text
AI宿主 ─ MCP stdio适配进程 ─ RunnerClient ─ 独立Runner
                                           │
GUI/CLI ────────────────────────────────────┤
                                           └ 算法 → Manager → Worker → CST
```

MCP退出不停止Runner/CST，不移走算法、检查点、项目锁、任务采用或VBA收尾职责。正常求解无固定总超时；控制请求、连接、文件读取及退出确认有界。默认单Worker、窄窗口、nmodes=1；HOM前向扫描及缺口补算沿现行实现。

## 2. COMSOL MCP参考：核查来源与适用边界

“COMSOL MCP”不是单一实现。本次选两项公开第三方项目，均非COMSOL官方接口保证；按固定提交阅读源码，未运行其服务、测试或COMSOL。参考日期2026-10-28，不按README工具数量推断成熟度。

|参考及固定提交|核查源码|借鉴|本项目不直接照搬|
|---|---|---|---|
|[wjc9011/COMSOL_Multiphysics_MCP](https://github.com/wjc9011/COMSOL_Multiphysics_MCP/tree/0f6b2c588a08da5ac66915e4f1fce7c07966763e)|[server.py](https://github.com/wjc9011/COMSOL_Multiphysics_MCP/blob/0f6b2c588a08da5ac66915e4f1fce7c07966763e/src/server.py)按session/model/parameter/study/results注册工具；[study.py](https://github.com/wjc9011/COMSOL_Multiphysics_MCP/blob/0f6b2c588a08da5ac66915e4f1fce7c07966763e/src/tools/study.py)提供求解/状态入口|按业务定义工具、输入参数说明、结果读取与求解分开|不机械封装每个CST API；不默认同步等待整个求解|
|同上|[async_handler/solver.py](https://github.com/wjc9011/COMSOL_Multiphysics_MCP/blob/0f6b2c588a08da5ac66915e4f1fce7c07966763e/src/async_handler/solver.py)把进度存内存，由daemon线程调用model.solve；cancel设置标志，源码说明不保证即时终止|长任务返回后查询状态|不把MCP进程内线程作为计算生命周期；不把取消标志视为求解器已停止。代码中的0.1/0.2/0.3是阶段赋值，不是可借用的实际进度|
|[Ching-Chiang/comsol-mcp](https://github.com/Ching-Chiang/comsol-mcp/tree/ccca65aa8277d1205c5de5fb6221e460aca5997a)|[_model.py](https://github.com/Ching-Chiang/comsol-mcp/blob/ccca65aa8277d1205c5de5fb6221e460aca5997a/comsol_mcp/_model.py)核对主模型tag/label/path；[_tools_workflow.py](https://github.com/Ching-Chiang/comsol-mcp/blob/ccca65aa8277d1205c5de5fb6221e460aca5997a/comsol_mcp/_tools_workflow.py)提供连接/载入工作流与异步作业查询|先连接已有服务、明确项目身份、操作留痕，避免隐式换模型|不宣称CST Desktop与本工具共享COMSOL式服务端模型；不接管其他用户的CST或清除无关模型|
|同上|[_state.py](https://github.com/Ching-Chiang/comsol-mcp/blob/ccca65aa8277d1205c5de5fb6221e460aca5997a/comsol_mcp/_state.py)写工作流/状态/操作记录；后台job仍在进程字典，路径resolve后检查存在|可读状态摘要和审计记录|持久文件不自动证明后台job可崩溃恢复；resolve/存在性不等于目录授权。CST侧沿用Runner持久命令和检查点，不另建job权威|

协议标准以第0节完整官方规范记录为准，不能仅凭参考实现采用FastMCP或旧SDK导入路径决定协议行为。官方SDK版本与支持协议/宿主版本在M0确定；工具Schema/结构化结果使用SDK，不自行实现JSON-RPC。

## 3. 本项目当前基础与实际缺口

|职责|已存在的实现/入口|接入前需补齐|
|---|---|---|
|连接、命令及身份|[RunnerClient](../csttool/runner_client.py)：request/connect/status/events/command/command_record；[契约](../csttool/execution_contract.py)|只读连接默认launch=False；脱离Qt的业务错误码和能力版本，不能解析中文异常字符串作为协议|
|后台状态与执行|[runner.py](../csttool/runner.py)：Runner.snapshot/command、validate_run_payload、CstExecutor|返回接受、执行活动、会话关闭和项目可恢复等独立事实；旧后台缺字段显示未知，能力不足拒绝写操作|
|排他及控制租约|[runner_ownership.py](../csttool/runner_ownership.py)、Runner命令claim/release，租期10秒|适配进程稳定身份、显式申请/释放、心跳及与GUI争用测试；不自动抢占、不续租复活已过期控制权|
|结果权威|[hom_scan.py](../csttool/hom_scan.py)、[清单](../csttool/hom_run_manifest.py)、[RunStore](../csttool/run_store.py)|增加可分页、有限读取、与项目/run/checkpoint版本关联的只读结果服务；不能把GUI的最后5000行/32指标展示截断当完整结果|
|诊断|[diagnostic_bundle.py](../csttool/diagnostic_bundle.py)：export_failure_bundle|返回有身份、大小/哈希/截断/缺失说明的工件引用，默认不把整个ZIP或大型场内容塞入上下文|
|知识及工具说明|[功能索引](feature-index.md)、[本机API](local-runner.md)|提供少量工具说明及受控文档入口；首版不加向量数据库、自动RAG或新工作流引擎|

现有RunnerClient HTTP错误主要是RuntimeError文字，不能宣称已经提供稳定错误枚举。Runner普通HTTP接口也不是MCP Streamable HTTP，首版另启stdio适配，保留回环HTTP为内部实现。

## 4. 首版工具边界

首版仅本机同用户，一个MCP进程启动时显式绑定一个项目绝对路径。inspect_project根据固定服务配置返回project_id，其后业务工具显式携带project_id，运行相关工具携带run_id，不依赖之前“选择工程”的请求。所有工具不再接受任意project_path或隐式“当前工程”。CLI配置限定可读源工程根目录及产物目录；超出范围报错。连接不自动start/recover，MCP断开不自动stop/shutdown。

以下是A1运行控制子集的14个拟定操作，**当前不存在**。总体工具数量不设14项上限；C01–C10建模/配置/结果操作按对齐方案继续设计，仍不提供通用任意调用入口。

|工具|输入/用途|副作用与前提|
|---|---|---|
|inspect_project|返回project_id、工程摘要、表达式参数、检查点及能力|只读；离线内容标记来源和时间，不启动Runner|
|get_run_status|可选run_id；查询运行、覆盖、Worker摘要和关闭事实|只读；旧run仅返回可验证持久记录，绝不用最新状态冒充旧run|
|get_run_events|run_id、opaque cursor、limit|只读增量分页，沿用事件source游标，不反复返回全量日志|
|get_command|request_id|只读；查询持久受理记录；found=false不是“求解从未执行”的充分证明|
|connect_runner|无自由命令，显式ensure_running布尔值|默认只连接，true才允许沿既有启动器启动状态服务；启动状态服务不提交求解|
|claim_control|预期project_id/instance_id；可选既有control_handle用于显式续期|返回持久control_handle，隔离交错调用；GUI租约有效返回CONTROL_BUSY，不自动强行接管|
|release_control|control_handle、预期instance_id|释放该句柄持有控制权，不停止任务|
|submit_run|request_id、期望身份、resume、typed HOM配置|默认worker_count=1；A1需支持普通simulation闭环，hom为独立扫描策略；保留既有检查点/清单/恢复门禁|
|stop_run|request_id、run_id、预期instance_id|只请求安全停止；未确认关闭前不得返回stopped=true|
|cancel_submission|request_id、start_request_id|启动回执丢失时沿cancel_start持久墓碑处置；不猜测新run_id|
|recover_project|request_id、run_id、预期instance_id|显式恢复，不包含自动resume或重算；证据不完整继续阻断|
|shutdown_runner|request_id、预期instance_id|仅无活动执行且安全状态可确认时，正常退出并确认OS锁释放；不强杀|
|list_modes|run_id、checkpoint_revision、cursor、limit、可选指标|只读、分页，含单位、TaskID/模式键、mesh来源、已确认标记和匹配字段（存在时）|
|export_diagnostics|request_id、run_id|写入既有diagnostics范围；非幂等ZIP生成需独立去重记录，不自动上传|

不提供任意VBA/Python/Shell执行、任意文件读写、直接改project.ini/checkpoint、清理CST进程或GUI点击工具。复杂运行时后处理仍由已登记的Python/VBA实现执行，工具只选白名单方法/参数和XYZ积分线；不能把“可自定义后处理”降为只能读取原生固定模板。

写操作都需服务端校验授权与身份；除申请控制权外的Runner变更操作显式携带control_handle。宿主的人类确认/annotations仅是交互辅助，不是授权机制。默认不给读操作申请控制权；MCP传输取消要取消本次请求尚可取消的工作并释放请求资源，不只是隐藏等待结果；已经独立持久化的Runner业务运行不因此stop。取消后不再发送该请求的响应/进度，改由后续get_command/get_run_status对账。不能因宿主超时另起任务。

## 5. 请求、结果与恢复契约

### 5.1 业务参数

外部HOM字段使用start_mhz、initial_window_stop_mhz、target_stop_mhz，内部映射fmin/fmax/endfreq；要求有限数值且start < initial_window_stop <= target_stop。没有新频率单位猜测或nmodes覆盖参数。续跑必须同清单/策略，修改目标上限仍未实现，不由MCP绕过。

source_project和CST安装来源由受控配置或已验证清单提供；调用不能注入executable。后处理只接受已注册方法，表达式保留。preprocess_modify_mesh=false明确表示不修改网格；失败临时加密与恢复原密度沿当前扫描策略，不新建第二套策略。

### 5.2 请求身份与提交不确定性

MCP JSON-RPC id、业务request_id、run_id、task_id、instance_id分别使用，不能混用。必须允许调用者提供可复用request_id，写请求在发往Runner前原子保存小型适配记录：项目/预期实例、client_id、operation、规范化payload哈希、Runner request_id与受理状态；不保存Bearer令牌。使用项目内control/mcp专用目录（拟定），不能复用pending-ui-stop.json覆盖GUI意图。

MCP连接/进程不能作为业务调用者会话。claim_control创建显式control_handle，并持久映射独立Runner client_id、项目、实例和期限；后续写操作每次校验句柄，不把进程级唯一client_id隐式借给所有交错对话。适配器配置的OS排他锁防止同配置同时启动两个进程；锁不等于调用者授权。同用户stdio信任域来自本机启动配置/OS权限，clientInfo自报名称不是认证；不同授权上下文的句柄不可互用。

同一业务request_id内容不同必须拒绝。Runner摘要包含client_id，重启后不能换client_id再以同request_id重投。控制claim租约过期用新的claim request_id；求解start仍用原ID和原内容，不能跟着换ID。控制句柄期限与续租策略在M0固定并测试：拟定每次显式申请/续期有效120秒，期内用小于10秒的Runner心跳，过期释放、停止心跳；运行本身可继续，不需要长期独占控制权。重连时不自动复活租约，不新增“续租”工具，只复用显式claim_control。

HTTP回执丢失：先get_command；已存在则返回原受理事实；查无记录仍需核对原实例存活/运行意图及cancel_start墓碑，再在相同身份、相同内容下重投。Runner已换实例或存在未决意图进入SUBMISSION_UNKNOWN/RECOVERY_REQUIRED，不盲目重发。若用户要停止未知start，用cancel_submission并查询其结果；整个流程不能通过修改文件伪造完成。

适配记录仅用于RPC重试身份，不成为任务完成权威或复制RunStore。并发重复请求靠锁/原子记录和Runner去重协调；MCP崩溃、宿主重试、GUI重开均不能增加实际任务采用数。

### 5.3 输出与错误

业务DTO包含schema_version、ok、operation、project_id、instance_id、run_id、request_id、state、execution_active、session_safety、recovery_required、data、error、artifact_refs；字段不适用为null，不编造0/false。它放入标准CallToolResult.structuredContent，不直接替换JSON-RPC result；content提供一致文本，现代版外围resultType=complete。outputSchema同时覆盖成功与工具失败结构。isError与业务ok相反，保留机器可读error.code及简短中文说明。

协议/封装错误由SDK返回JSON-RPC error，例如未知方法/工具、非法请求结构、缺失现代元数据、版本不支持；已进入工具执行的业务校验、控制权冲突、求解/文件错误使用isError=true，不都转成-32603。字段类型是否属于调用封装Schema错误由SDK边界决定，并以契约测试固定；业务范围/频率顺序错误必须可由模型读取修正。本项目字符串错误码只在业务DTO中，不占用MCP保留数值错误码范围。

拟定错误码：INVALID_ARGUMENT、PATH_NOT_ALLOWED、PROJECT_MISMATCH、CONTROL_BUSY、STALE_INSTANCE、STALE_RUN、RUN_ACTIVE、RECOVERY_REQUIRED、CHECKPOINT_MISMATCH、RUNNER_UNAVAILABLE、SUBMISSION_UNKNOWN、RESULT_UNAVAILABLE、RESULT_CHANGED、DIAGNOSTIC_EXPORT_FAILED、INTERNAL_ERROR。error包含phase、retryable（不授权重算）、action、error_ref；详细traceback映射现有日志，不原样返出敏感令牌/任意磁盘内容。

accepted只表示命令受理；模式成功仍需Task/完成标记/可用产物/采用校验；STOPPING不代表已停止，confirmed_frontier与calculated_upper分开，局部CST阶段百分比不是整体扫描完成率。丢失文件和被清理产物返回missing/needs_regeneration，不把旧报告宣传成仍可下载完整原始数据。

### 5.4 分页、读取与工件

模式查询默认100条、最大500条，指标默认常用摘要并可选，响应有大小上限；游标绑定project/run/检查点revision，文件更新返回RESULT_CHANGED并要求重开快照，不静默漏行或重复。频率统一MHz，其他指标必须带可确定单位，未知单位标记unknown。

优先在Runner提供纯只读结果查询，并使GUI与MCP可共用不依赖Qt的reader；不要从GUI类导入后台。离线inspection允许读取有限固定文件且标记offline；无原生快照一致性不能宣称事务读取。现有GET /status不支持任意历史run，需新增受控只读查询或验证历史索引，不能靠run_id过滤字符串猜测。

工件引用保留artifact_id/node_id/sha256和可读名称、相对位置、大小、类型、available/truncated等扩展元数据；统一定义工件契约，现有ArtifactRef构造ABI可直接调整并同步全部调用点。无跨机传输时明确local-only；第一版不实现任意路径下载。M3不增加通用资源浏览器，Resources/Prompts待实际需求再做。

## 6. 权限、并发与诊断

- 路径resolve/Windows大小写/UNC及目录联接需共同核验，原始工程只读，副本归项目。M0/M1拒绝越界、符号链接/重解析点逃逸；不把字符串前缀检查当目录授权。首次只支持本地已授权路径，网络盘留待明确验收。
- 适配进程只连接自身用户可访问的Runner端点；不向工具结果泄露runner.json令牌。新旧契约不匹配时拒绝连接并要求正常重启到同批版本，不设置兼容读取或写入路径。
- 工具调用不得持有全局锁等待CST。每项目写命令串行；状态/事件查询可并行；心跳沿control_handle对应client_id以小于10秒周期续租，仅在显式句柄未到期时运行。退出停止心跳并尽力release，EOF及时退出适配进程，崩溃按既有租约过期，不停计算。验收宿主Windows Job Object/进程树清理不会连带结束独立Runner。
- tools/list确定排序、目录不因前一个调用发生隐式变化；现代discover与tools/list返回ttlMs/cacheScope，首版保守private，不发送动态listChanged。协议progress仅限活跃请求且有progressToken，必须单调增加；CST局部阶段进度改走业务状态查询，不在submit返回后继续发通知。
- stdout只允许MCP协议，日志写stderr及既有可读运行目录。记录MCP_TOOL_RECEIVED/COMMAND_ACCEPTED/COMMAND_UNKNOWN/TOOL_FAILED（拟定）与项目/run/request/task、source函数和error_ref；不每次轮询打印INFO，不重复全量traceback。
- export_diagnostics仍受4MiB单文件、64MiB总源内容和1000候选限额；MCP大结果不另绕过导出预算。导出任务受理去重与最终ZIP哈希分开记录，取消后已生成包允许查询，不重复生成。

## 7. 共用模块与直接迁移

拟新增csttool/mcp_server.py（标准协议装配）、application_service.py（GUI/CLI/MCP共用业务服务，由Runner托管）、result_query.py（共用无Qt查询）。现有execution_contract和RunnerClient按唯一新契约迁移，删除被替代的校验、错误转换和结果读取入口；不新增MCP专属业务框架。全部名称仍为拟定，尚未创建。

Runner/Manager/Worker接口不受旧兼容约束，按现代协议及公共业务契约需要修改。GUI、CLI、后台和测试同批切换，不保留旧错误文本ABI、旧命令别名或旧客户端支持。身份前提在后端同一命令锁内验证，不能只靠客户端查询。数据保护与一次性显式迁移边界见静态框架第9节。

pyproject增加可选mcp依赖，普通GUI/Runner导入不依赖SDK、不初始化MCP。具体SDK版本在M0核实后固定支持范围；不照参考仓库的历史导入写法猜测当前SDK API。不引入Celery、Redis、集群、第二个数据库或新VBA ABI。源码打包增加可选安装说明和宿主配置示例，不把令牌/本机路径入库。

## 8. 分阶段TODO与验收门禁

|阶段|交付|验收/允许进入下一阶段的条件|
|---|---|---|
|M0 契约收敛|完成官方全文/类型阅读与符合性矩阵；确定SDK/宿主版本；冻结14工具范围、业务DTO、错误码/能力、目录权限、请求/控制句柄及日志映射；更新API/索引|先证明SDK/目标宿主支持所选日期版本；不能将旧initialize当2026标准。Schema拒绝NaN/错误单位/越界/nmodes覆盖；GUI频率语义一致，审计旧接口删除范围与身份竞态，不启动CST|
|M1 只读MCP|stdio、inspect/status/events/get_command/list_modes；受控结果reader、分页、manifest/日志工件引用；只读默认不launch/claim|真实MCP客户端按所选版本验证现代server/discover/逐请求元数据/resultType/cache或单列旧版握手；无Qt导入、stdout干净；未启动Runner/CST；坏检查点、超大输出、目录逃逸/联接、旧后台/离线、游标更新均明确报错或降级|
|M2 控制与不确定提交|connect/claim/release/submit/stop/cancel/recover/shutdown；同ID去重与实例前提；GUI/CLI同步切换唯一新契约|假Worker/HOM真实Runner子进程：响应丢失、并发重复、同ID异内容、MCP/宿主退出、租约过期、GUI争用、后台换实例、start前后取消和停止、恢复不重算；不能只mock服务类|
|M3 诊断与宿主交付|export_diagnostics去重；安装extra/配置示例；读写工具说明；发布包解压安装/连接测试|真实宿主只读与假Worker控制全链、令牌不泄露、中文/空格路径、CWD独立、包内源码身份；校验摘要可对应源码/日志/任务。Host审批提示实测，但服务端授权不依赖提示|
|M4 业务扩展（按需求）|submit_run支持标准批任务；现有后处理XYZ/运行时复杂算子及场匹配结果查询；小型KB文档入口|不改标准批次恢复身份，不把无外部Q的预期缺项判全任务失败；不将Fake数值当物理结果。不要求RAG/模型生成器作为首版前提|
|M5 真实CST串行副本|小网格Pillbox HOM提交、停止、MCP退出继续、重连/恢复、ACK/采用窗口、收尾/失败诊断；必要标准双任务|核对原工程哈希、实际Solver次数、TaskID/采用唯一、覆盖与后处理值、正常关闭/OS锁释放；过程不强杀。加密/扩窗等现有pending真实门禁仍独立记录，不能被MCP烟雾测试取代|

每阶段都同步当前状态、TODO、功能索引及API/使用文档，跑documentation_index_test.py和对应功能测试，记录新测试日期与报告。只按实际完成勾选。没有用户真实求解授权时M5保持pending；测试前检查磁盘，结束后清理可再生成副本/大场，保留轻量日志与哈希并说明产物可用性。

M0→M1→M2→M3仅形成控制基础，不能称首阶段通过；A1须同时实现最小工程建模/设置/普通simulation并通过G01–G08，真实CST门禁不可推迟。M4其余业务按需求扩充，不以工具数量为目标。远程MCP传输/跨用户认证与E6、节点Agent与E7–E9统一安排，不另造第二条远程路线；本计划不承诺浏览器直接连接当前Runner HTTP。

## CST详细设计补充（2026-10-28）

以[CST能力、作用域和现行实现审查](mcp-cst-capability-scope-design.md)约束上述工具：首版沿Managed批宏链，不并行建立原生DE控制器。官方Python/CLI能力与当前生产能力分别声明，明确结果模块/维数、子工程及CST run id、批任务与异步Solver、实例所有权和历史持久性边界。预处理历史返回检查属于待修前置缺口；不根据接口名称宣称三维读取、即时停止或MPI HOM。

## 9. 本轮设计核查记录

本轮只完成外部固定提交源码对比、现有Runner源码映射与文档计划。此前测试数字属于各原功能验收，不是MCP工具通过数量。MCP服务、14工具、结果端点、稳定错误枚举、身份前提扩展及SDK依赖均未实现；无COMSOL/CST运行、宿主配置修改或远程部署。

功能实现后再把本节逐步替换为阶段证据，保留日期、失败记录和剩余边界；不把计划自动标为已交付API。

文档专项：2026-10-28 documentation_index_test.py 2 passed（0.69s），报告artifacts/mcp-plan-docs-20261028.xml；仅证明索引链接/符号约定，不证明MCP语义、真实宿主或CST行为。最终修订再核对计划中的本地引用。

官方全文审查后补验：文档索引2 passed（0.66s），artifacts/mcp-standard-docs-20261028.xml；[符合性矩阵](mcp-protocol-conformance.md)的2份标准消息示例与2份缺字段反例经固定官方Schema静态验证，既有本地引用有效。首轮验证脚本$defs路径错误及修复已记录，未修改官方类型。依然不是SDK/宿主或服务端符合性验收。

实施顺序补充：遵循[框架静态设计与冻结条件](mcp-framework-static-design.md)，先完成逐工具契约、当前数据字段和失败分支映射，再进入运行代码；不以生成服务骨架代替设计收敛。

最新契约收敛：以[统一接口契约](unified-interface-contract.md)和[同步迁移/删除清单](unified-interface-migration.md)为准。覆盖原MCP代理控制句柄/client_id映射设计：统一公共服务管理120s显式续期，幂等摘要不包含可轮换凭据；GUI/CLI/MCP同用，不保留旧契约。新增run/scan来源及只读查询边界均为待实施设计。

M0静态补充：后处理和优化子Schema已冻结，详见[子契约](postprocess-optimization-subschemas.md)；官方SDK候选精确固定mcp==2.3.0、Python3.12，目标Codex现代路径需显式开关/服务版本标记，详见[支持核查](../knowledge-base/mcp-sdk-host-support-20261028.md)。目前不修改pyproject或用户配置，运行握手仍待；两优化策略因O01–O05缺口不宣告可用。

总体范围更新：功能覆盖以[COMSOL对齐矩阵C01–C11及A0–A4路线](comsol-mcp-functional-alignment.md)为准；本文M0–M5是基础运行链子计划，不代表完整对齐完成。

阶段门禁更新：[对话闭环G01–G08](mcp-first-stage-conversational-gate.md)优先于原只读/14控制操作首版定义；从空工程建模到真实后处理输出必须在A1完成。

A1静态子契约已冻结：[工程创建/参数化建模/配置/single-simulation/结果输出](mcp-first-stage-interface-contract.md)，官方来源和持久化边界见[本轮核查](../knowledge-base/cst-first-stage-api-semantics-20261028.md)。九操作复用公共身份/控制/幂等；不再仅靠14控制操作实现首阶段。partial readback及新创建通道仍是未验实现门禁，不把字段冻结当功能可用。

设置验证器来源与等级以[五项读回设计](cst-settings-verifier-design.md)为准：持久历史/元数据、重开/live及行为不混同；默认未校准不ready。cst_version共享只读组件尚未集成，语义投影不得复制容器解析器；设置报告绑定scope/定义hash及安装profile。
