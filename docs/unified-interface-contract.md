# 统一接口契约：GUI、CLI、MCP与后台

日期：2026-10-28。状态：静态设计，未实施。优先级：现代MCP协议 → 本文唯一业务契约 → 共用应用服务 → 执行实现。本文收敛[框架设计](mcp-framework-static-design.md)，覆盖旧计划中MCP专属DTO、控制句柄及兼容条款；不宣称协议标准规定本项目的业务字段。协议信封依据[符合性矩阵](mcp-protocol-conformance.md)，CST语义依据[作用域审查](mcp-cst-capability-scope-design.md)。

## 1. 唯一契约与执行路径

GUI/CLI/Python/MCP使用同一套具名操作、参数模型、校验、错误及查询返回。MCP装配负责标准Schema、调用元数据、结果信封及传输取消；GUI负责输入和展示；CLI负责参数解析和输出。服务端应用服务才是业务校验权威。客户端可复用同一校验器作快速反馈，但不得另写规则。

公共应用服务由Runner托管；所有正常执行入口通过统一客户端到达它。CLI不直接构造CstApplicationBackend，GUI不读取业务检查点，MCP不另建任务管理器。后台内部仍可按效率选择调用方式，不要求Worker/VBA传输JSON-RPC。官方SDK/目标宿主的实际支持核实仍是实施前门禁，不能用自研旧协议回退解除。

以下类型和操作均拟定，不是现行API。内部契约修订标识定为`csttools.application/1`，与MCP日期版本、磁盘schema及VBA协议版本分别记录；新旧契约不一致拒绝连接，不提供兼容分支。

## 2. 公共类型与校验规则

所有输入为对象，未知字段拒绝；JSON Schema 2020-12，additionalProperties=false，必填见下文。可选字段必须明确定义默认值；不接受字符串布尔值、bool冒充integer、NaN/Infinity。ID为1–100位ASCII字母数字及`-_`，不作为文件路径。UTC时间使用带时区ISO8601。响应不包含Bearer令牌、私有控制凭据或任意文件内容。

|类型|字段及约束|
|---|---|
|ProjectRef|project_id：由项目身份记录产生；路径仅在本机初始化配置/GUI选择阶段解析授权，不作为每次操作的自由参数|
|InstanceRef|instance_id：本次后台实例身份；连接、控制及变更需校验，不接受“最新实例”通配符|
|RequestRef|request_id：调用方在发送前保存；重试复用原ID和规范化内容。MCP JSON-RPC id另行生成，不作业务去重键|
|RunRef|run_id：框架执行身份；不得与CST结果整数run id或物理模式身份混用|
|ControlRef|control_handle：公共服务颁发、绑定actor/project/instance/期限；GUI/CLI/MCP同用，过期不复活|
|PageRequest|cursor：首请求省略，后续为服务产生的不透明字符串；limit默认100、整数1–500；cursor大小≤4096字节|
|Error|code、message、phase、retryable、action、error_ref、details；details为白名单字段，无令牌/任意traceback|
|Artifact|artifact_id、node_id、kind、name、relative_path或null、size_bytes或null、sha256或null、available、truncated、missing_reason；只引用授权工件|

actor_id由受信任本机连接配置确定并稳定保存；自报MCP clientInfo不是认证。控制句柄属于同用户授权域，不能跨身份借用。原计划由MCP进程代理独立Runner client_id的双层句柄方案取消：控制权与租约统一由公共服务管理，不在MCP中再保存一套业务租约。

所有公共操作返回同一业务结构：`contract`、`ok`、`operation`、`project_id`、`instance_id`（离线null）、`run_id`（不适用null）、`request_id`（查询null）、`observed_at`、`data`、`error`、`artifacts`。ok=true时error=null；ok=false时data可包含已确认的局部事实，error必有值。查询到FAILED运行本身可ok=true；它表示查询成功，不表示计算成功。

## 3. A1运行控制的十四个公共操作

公共参数P=project_id，I=expected_instance_id，R=run_id，W=request_id+control_handle+I。每项均要求P。所有变更先授权、校验身份、检查幂等记录，再产生副作用。claim例外不需已有句柄。下面的上限是新契约预算，不是现有实现已具备的限制。

|操作|额外必填/可选输入|data与副作用|
|---|---|---|
|inspect_project|可选parameter_cursor、parameter_limit=100|项目元数据、参数表达式分页、可选安装/源工程引用目录、检查点摘要和能力；离线可执行，不启动后台/求解；不一次返回全部参数或原始模型|
|connect_runner|ensure_running=false；true时request_id必填|连接描述、contract、instance、能力；true仅启动后台服务，使用启动所有权锁及启动记录去重，不启动求解|
|get_run_status|R可选；省略明确表示当前运行|状态快照；指定旧R只读对应持久快照，不借用当前状态|
|get_run_events|R可选、PageRequest、level/category可选白名单|events、next_cursor、has_more、source_revision；每页≤1MiB，记录过大以截断摘要+工件引用返回|
|get_command|target_request_id|found、提交状态、原操作/摘要、原回执；敏感控制凭据不回显；found=false不证明从未执行|
|claim_control|request_id、I；可选control_handle表示显式续期|新/续期句柄、expires_at、control_revision；默认有效120s；争用拒绝，不隐式抢占|
|release_control|W|released；仅释放自身控制权，不停止任务；重放返回原事实|
|submit_run|W、submission（第4节）|命令回执、run_id；受理后独立执行，不同步等待CST结束|
|stop_run|W、R|命令回执；合作停止，不承诺当前Solver立即中断；后查状态确认|
|cancel_submission|W、start_request_id|持久取消墓碑及目标run或null；只取消指定提交，不取消当前任意任务|
|recover_project|W、R|恢复操作回执；只对账/处理该run所属会话，不自动resume或清除未知证据|
|shutdown_runner|W、expected_run_id（可null）|退出意图受理；无活动执行且安全可确认才能受理；退出确认另由客户端核对实例进程与所有权释放，不把HTTP断开判成功|
|list_modes|R、PageRequest；首请求revision可省略、后续必须一致；metrics可选≤32个注册键|revision、modes、total、next_cursor、has_more、coverage、source；只返回已采用模式。首次取最新快照，后续更新拒绝RESULT_CHANGED|
|export_diagnostics|W、R|导出操作回执及工件引用；耗时生成由后台执行，使用get_command查询完成/失败，不重复ZIP生成，不自动上传|

命令回执字段：`submission_state=accepted|rejected|unknown`、`execution_state=pending|running|completed|failed|cancelled|unknown`、`effect_ref`（run或artifact）、`accepted_at`、`finished_at`。请求超时由公共客户端生成unknown观察，不伪造服务端受理记录；拒绝为ok=false。命令执行完成仍不等于CST计算成功，例如submit的命令完成仅表示运行启动意图已落实。

## 4. 提交配置

Submission采用带判别字段的联合对象，禁止传入algorithm Python对象或可导入路径。

- 新任务：`mode=new`、`kind=simulation|hom|standard|optimization`、source_ref、installation_ref、worker_count（默认1，1–64且受本机配置上限约束）、postprocess、对应kind配置。引用须来自授权配置/inspect目录，不能注入exe路径。
- 续跑：`mode=resume`、`prior_run_id`、`checkpoint_revision`。配置从持久运行定义恢复；禁止同时传入替换目标频率、源工程、后处理或网格。修改配置作为新的显式功能另设计，不在resume里暗改。
- simulation：绑定已核验且不可变definition_revision，普通单次求解/后处理，必须与实际工程设置读回一致；具体配置见首阶段设计待冻结，不使用HOM窗口策略。
- hom：`start_mhz`、`initial_window_stop_mhz`、`target_stop_mhz`为有限数，满足start < initial_window_stop <= target_stop；`window_width_mhz>0`；requested_modes固定1不对外暴露。恢复策略独立对象：enabled、mesh_retry_factor（>1，默认1.5）、max_probe_expansions（1–8，默认3）。
- mesh：`preprocess=preserve|fixed`；fixed要求cells_per_wavelength正整数；preserve禁止传固定密度。convergence独立可选配置，含start/stop/step正整数及relative_tolerance有限数(0,1]，默认禁用。完整范围检查归共用验证器，不能像旧validate_hom_settings那样只依赖int/bool转换。
- standard：tasks为1–10000项；每项job唯一非空，parameters为参数名到表达式字符串的有界映射，最多1024项、每表达式≤8192字符；不求值、不扁平化。模型参数错误归对应任务阶段。
- optimization：strategy_ref是注册的WTC/TM020等策略ID，options按该策略Schema校验。保留现有优化能力，但不得继续通过base.run_backend直接注入算法对象绕过公共服务。策略源码/Options需后续逐项静态审查；未冻结的策略不宣告可提交，返回UNSUPPORTED_CAPABILITY。
- postprocess：数组≤128项，每项含metric_id、method_id、settings；metric_id唯一，method_id须注册，settings按该方法唯一Schema校验。轴和积分偏移必须有显式单位。不得提供任意VBA字符串；对现有PPS的转换在后台一个位置完成。各算子Schema及资源预算已在[子契约冻结](postprocess-optimization-subschemas.md)定义，不凭方法名字自动生成。

公共请求编码后≤256KiB；超出直接拒绝，不静默截断标准批任务。standard若在10000条上限前达到字节上限，以字节上限为准。批量上传/分片为后续能力，不临时增加第二个提交通道。

## 5. 状态、错误与原子性

状态快照将三类事实分离：connection（online/offline）、run_state（idle/preparing/running/stopping/recovering/interrupted/completed/failed/recovery_required）、execution_active；另给session_safety和recovery_required。UI的READY仅为草稿有效，不属于后台run_state。终态但清理仍活动时execution_active=true；恢复未确认不得提交新任务或退出后台。

session_safety冻结为unknown、running、confirmed-closed、exited-unverified，与当前lifecycle_diagnostics.lifecycle_facts实际输出一致；预处理未确认可将其置unknown，不从业务FAILED猜测。未确认值unknown；单个进程退出不自动confirmed-closed。coverage保留confirmed_frontier_mhz与calculated_upper_mhz，不用最远模式频率替代；progress含stage、stage_percent或null、task/window，不映射为整体扫描百分比。

稳定业务错误：INVALID_ARGUMENT、REQUEST_TOO_LARGE、PATH_NOT_ALLOWED、PROJECT_MISMATCH、CONTRACT_MISMATCH、CONTROL_BUSY、CONTROL_EXPIRED、STALE_INSTANCE、STALE_RUN、REQUEST_CONFLICT、RUN_ACTIVE、RECOVERY_REQUIRED、CHECKPOINT_MISMATCH、RUNNER_UNAVAILABLE、SUBMISSION_UNKNOWN、UNSUPPORTED_CAPABILITY、RESULT_UNAVAILABLE、RESULT_CHANGED、DIAGNOSTIC_EXPORT_FAILED、INTERNAL_ERROR。retryable仅描述能否重新查询/在条件改变后重试，重发计算仍受原ID/内容约束。未知异常记录error_ref及源码位置，不用中文消息反解析错误码。

在服务同一临界区内核验项目/实例/当前run前提、控制权、同ID摘要、取消墓碑及运行活跃性，然后持久写入意图，最后安排副作用。幂等键为(project_id, request_id)，摘要包含actor、操作、业务参数及目标身份；不包含JSON-RPC id、trace id或可轮换control_handle。相同actor同内容重放先授权再返回原脱敏回执；过期句柄不得产生新副作用。不同actor或不同业务内容返回REQUEST_CONFLICT。原实例已消失的未决命令只对账，不自动执行。

控制租约统一120s，GUI/CLI/MCP共享同一服务语义；显式claim续期，不再采用GET状态自动延长10s租约。任务受理后不依赖持有控制权才能继续运行。断开/协议取消不自动停止业务运行。

## 6. 结果revision、来源及实际格式

静态核对现有格式：HomCheckpoint保存schemaVersion、policy、projectFingerprint、coverage、pending、confirmedSnapshot和report；report含modes、adopted_task_ids、completed/empty/probed/failed、solver_calls及recovery状态。ModeResult含mode_index、frequency、values、project_snapshot、task_name、task_id、mesh密度，**没有**逐模式run_id、单位、attempt或全局物理模式ID。HomRunManifest是schema_version=3，Scan checkpoint字段命名和版本独立。RunStore采用日志与attempt索引不是观察日志的替代品。

新查询revision先采用已原子落盘checkpoint的SHA256，不假设已有递增版本；绑定project、扫描身份与该字节快照。模式分页从同一快照解析，客户端后续请求重新确认哈希，变化即RESULT_CHANGED。不靠mtime/size证明内容一致，不长期缓存完整场数据。检查点读取上限暂定16MiB，与当前GUI边界一致；超过返回明确RESULT_UNAVAILABLE，不返回空模式列表冒充完整结果。

旧checkpoint不能独立确定Runner历史run归属。新写入增加明确scan_id及producer_run_id，独立持久run→scan/revision/artifact映射；续跑允许不同run共用scan，但不得将原run结果改写为本run新产出。历史run只查询已登记revision工件，缺记录返回RESULT_UNAVAILABLE；不以当前检查点冒充。一次性迁移无法从证据确定归属时保留unknown并拒绝按run查询，不猜测。

每条模式返回mode_key（scan_id/task_id/mode_index组合）、source_run_id或null、task_id、mode_index、frequency_mhz、metrics及mesh来源。mode_key为结果身份，不代表物理匹配身份；task_id缺失时不伪造。metric包含key/value/unit/status/source；单位从注册算子/明确结果定义取得，无法确定为unknown。场匹配/Artifact缺失明确needs_regeneration，不强制重算已确认覆盖。

result_query必须纯只读；不能调用RunStore._adoption_events，因为它会修复/截断尾日志。读到checkpoint确认而采用索引缺失时可以返回checkpoint-confirmed并标明reconciliation_pending；恢复服务负责补账，查询禁止写入。列表分别标明checkpoint_confirmed与journal_adopted，避免混成一个布尔成功。

## 7. MCP映射与离线边界

具名公共操作映射同名工具；Schema来自同一模型，不维护手写第二份字段定义。业务DTO置structuredContent，content给一致简短文本；isError与ok相反。标准信封和版本字段由所选官方SDK验证，不将业务contract代替协议版本。标准取消仅结束当前协议请求尚可取消的工作；受理后的run需stop_run。

离线inspect/get_run_status/get_run_events/list_modes通过相同公共只读查询组件执行，标记offline和持久观察时间；不能有控制权、实时进程结论或执行副作用。get_command离线只能报告持久事实及unknown，不能据“无文件”宣称未执行。启动器与离线读取是公共客户端边界的一部分，不在GUI/MCP各写一套。服务端仍重做写授权，不信任离线预检。

## 8. 收敛状态

公共操作、身份、幂等、错误、分页及主要提交字段已静态定义；后处理方法/优化策略的子Schema已冻结，见[子契约](postprocess-optimization-subschemas.md)。[官方SDK及宿主静态支持](../knowledge-base/mcp-sdk-host-support-20261028.md)已核实，当前有效配置/真实握手和算法O01–O06缺口仍阻断对应能力。这些是明确子契约，不阻止审查整体结构，也不标为已实现。删除与迁移清单见[统一底层迁移方案](unified-interface-migration.md)。本轮不创建运行Schema或新模块。

范围说明：本文冻结A1运行控制子集及提交类型，不是完整项目接口全集。[COMSOL功能对齐](comsol-mcp-functional-alignment.md)进一步要求工程/文档/对象身份、定义revision、change set和建模/材料/求解/分析操作；这些扩展沿同一公共契约实现，尚未冻结的输入不能宣称已可调用。

A1验收范围更新：新增[对话建模到结果门禁](mcp-first-stage-conversational-gate.md)，普通simulation与最小工程编辑子契约需在首阶段冻结并实现；本文件原14项仅运行控制基础，不构成首阶段全部接口。

A1静态子契约已冻结：[工程创建/参数化建模/配置/single-simulation/结果输出](mcp-first-stage-interface-contract.md)，官方来源和持久化边界见[本轮核查](../knowledge-base/cst-first-stage-api-semantics-20261028.md)。九操作复用公共身份/控制/幂等；不再仅靠14控制操作实现首阶段。partial readback及新创建通道仍是未验实现门禁，不把字段冻结当功能可用。

设置验证器来源与等级以[五项读回设计](cst-settings-verifier-design.md)为准：持久历史/元数据、重开/live及行为不混同；默认未校准不ready。cst_version共享只读组件尚未集成，语义投影不得复制容器解析器；设置报告绑定scope/定义hash及安装profile。
