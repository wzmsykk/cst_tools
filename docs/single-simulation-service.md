# 公共single-simulation服务与G03验证

默认ApplicationService现在注册NativeDefinitionVerifier；stage_definition仍不启动CST、ready=false；所有者显式调用verify_definition才启动验证。可信测试端口仍可注入，客户端不能提供验证证明。

后端从冻结definition.cst复制，不复制同名结果目录；两个串行batch会话分别保存、退出，以及从保存后的.cst重新打开、再保存退出。每阶段在已加载3D Model.run中调用Save、GetOwnProject作用域下已有工程的全局身份/单位/频率读回接口，无OpenFile、参数写入、AddToHistory、Rebuild或Solver.Start。核对CST 2022大版本、精确副本路径、HF Eigenmode、mm/MHz、Tet及频率范围。频率读回按已校准六位有效数字容差；有效历史投影及精确表达式/参数JSON必须与冻结定义一致。方法、模式数、目标开关和自适应等以保存重开后的完整允许表历史为定义证明；不将不存在的live getter或旧执行DB伪装为证明，实际执行配置仍由B3独立核验。

公共失败completion已确认时优先保留原协议错误码和failure，未知错误码使用TASK_FAILED；成功结果采集在Start返回及模式可用门禁之后。没有post帧不会将原始求解失败替换为FileNotFoundError，关闭和恢复事实仍独立判断。自动时序与控制器注入见[驱动说明](public-fault-injection.md)。

只有每次完成nonce、无宏错误、退出码0、归属进程全部退出、保存后设置和表达式未变、安装hash及源hash未变，才生成四组G03门禁。验证记录及宏/日志/状态位于定义目录verification-<id>；文件夹ID由definition.json的verification.diagnostics映射。失败不更新ready，不强杀；前次会话退出未确认则禁止重试，需要核实session-status及现场进程后对账。当前验证会话已纳入项目恢复及退出核验，GUI生命周期文本显示G03；恢复仅等待正常退出或记录已退出但未验证成功，不授予ready。GUI验证按钮、HTTP验证命令和真实中断矩阵仍待完成。


## 服务与传输接口

|入口|职责及副作用|
|---|---|
|ApplicationService(project, project_id, installations=..., definition_verifier=..., worker_factory=...)|服务器构造，安装映射为授权引用→路径；默认使用本机发现。两个端口由可信后端注入，不是HTTP/MCP用户字段|
|stage_definition(document_id, source_project, installation_ref)|所有者内部登记，不开放任意路径工具；B1/B2读回、冻结副本及配置、派生revision；默认生产后端不在登记时启动，保存pending。显式可信测试端口可选择登记时验证，不开放客户端注入|
|verify_definition(document_id, revision)|显式所有者验证操作；默认接入生产验证器，原生实现可能有受控副本副作用。冻结候选被修改即STALE_DOCUMENT，不修改旧定义指针|
|inspect_definition / preflight|只读校验完整性、元数据摘要、project/document/revision、安装及G03状态，不启动CST|
|execute_simulation(payload, run_id, stop, update)|仅构造Runner执行适配器；在Runner线程run时获取现有项目锁并启动Managed Worker|
|get_simulation_results(run_id, result_revision=None)|只读已采用结果及稳定内容revision，核对接收记录与快照hash；缺结果RESULT_NOT_READY，旧revision RESULT_CHANGED|
|reconcile_simulation(run_id)|所有者仅补写已ACK/标准关闭/原生匹配的已收取结果，不调用Worker或Solver；首次修复与再次读取均返回含result_revision的公共DTO|

Loopback Runner继续使用Bearer认证、client_id控制租约、request_id幂等和既有命令记录：

```json
{"operation":"start","payload":{"kind":"simulation","document_id":"document-a","definition_revision":"<server revision>"}}
```

示例省略schema_version/request_id/client_id等既有命令信封字段。simulation payload**恰含这三项**；source_project、installation路径、参数覆盖、algorithm、postprocess、resume、worker_count、ready等都拒绝。模式是明确新执行，重连不得隐式重算。现有MCP submit_run已映射到此内部传输；该内部HTTP信封仍不等于MCP wire format。

GET `/simulation-results?run_id=...&result_revision=...`以及`RunnerClient.simulation_results`查询同一服务。业务错误仍通过明确HTTP响应返回，新增code字段；不把DEFINITION_NOT_READY/RESULT_CHANGED当作丢失连接。2026-11-02记录了九工具桌面子集通过，本次未重新盘点宿主；新增五个typed/导出工具的SDK真实链已验，桌面完整调用和GUI/CLI完整迁移尚未完成。

## 定义、验证与身份

定义在control/definitions/<document>/<revision>/保存definition.cst与definition.json。revision覆盖document、源hash、配置、安装引用及积分轴；元数据被改、文件变化、跨project或目录逃逸均拒绝。验证端口的proof须绑定同一source_sha256、root和verified状态，具备saved-reopened/identity/settings/standard-close四组门禁。此端口负责真实证据，不能通过客户端JSON注册回调或注入字段。默认提供NativeDefinitionVerifier；可信假端口仅用于测试，不构成真实验收。

stage_definition不是完整create_project/apply_model_changes/configure_simulation实现；document_revision编辑与候选发布事务已在definition_editing和公共typed工具接入，见typed-definition-service.md。冻结候选只复制.cst，不继承外部同名结果；执行时保存的结构/设置由原有历史重建。参数表达式保留，不传运行中参数覆盖或HOM窗口。

公共definition_revision现在贯穿提交、Managed配置、RunStore采集binding及结果。Native prepare接受所有者的明确revision，另外保存configuration_digest核对源hash/config/批准历史；独立B4没有公共定义时继续以配置摘要建立身份，不能混淆两种摘要。task/session/nonce仍由服务端创建，客户端不能指定。

## 单次执行链

1. Runner在控制锁之外做大文件预检，再在锁内核对owner/control_revision/run代际，写命令意图后才执行；响应丢失重复同request_id返回原run，不再次调用Worker。
2. 获取现有ProjectRunLock，在control/runs/<run>/写simulation-intent。任何旧意图/结果均阻止再次run；失败后只能对账或明确新请求，不能复用run_id从头算。
3. 使用现有ManagedCSTWorker，运行目录为项目runtime/worker_single_<run>/<session>，可由现有worker_*恢复扫描发现。WorkerConfig.execution_config/project_id/definition_revision是所有者字段，不从旧字典适配器或客户端开启。
4. constructor在副本准备后预分配唯一空参数Task，冻结RunStore nonce并生成捕获辅助函数。仍用已加载Model.run和原completion/ACK、存档及v2收尾，不另起CST通道。单次Worker禁止第二任务及任何参数覆盖，在等待ready前即拒绝。
5. 最后一次before-solver停止检查之后，先采集pre并验证无旧库，再记录实际Start调用。post采集失败独立标为native-capture-post，不能冒充求解失败；Start=1的事实在写帧前保留，避免后处理/记录失败触发破坏结果的重建。
6. 空参数单次任务不需要恢复参数；Start前明确解除本次参数恢复标志，失败收尾不额外Rebuild清掉新生DB。正常HOM/standard模板逻辑不变。真实失败/非标准退出仍不放宽：worker.stop无法确认时RECOVERY_REQUIRED，不强杀或自动退役。
7. run_task返回后，服务检查独立的acknowledged接收回执、task/session、后处理数据和原快照hash，写simulation-received；finally始终按现有Worker.stop，确认后写simulation-closure。
8. 确认进程退出才finalize原生RunStore；匹配task/project/definition，必须配置匹配、求解成功、两项有限正指标和真实快照，才ensure_adopted并原子发布simulation-result。配置匹配、退出0单独都不足。

服务未设求解总超时，启动/通信/退出沿现有有界策略。无论预写意图、Worker构造、读结果、关闭、采集或发布失败，都释放本控制器锁及日志句柄；已启动但归属/关闭不明的会话仍保留恢复状态，不因Python对象构造失败就宣称CST已退出。

## 恢复与日志

服务保留simulation-intent、simulation-received、simulation-closure、RunStore任务/采集和采用记录。仅当ACK、标准关闭、冻结定义/原生binding、归档DB与接收快照均核对通过，才补最终结果。采用已经写入而最终结果没写时，ensure_adopted不会重复写采用事件。

Runner的simulation恢复分支先调用现有recover_project_sessions，再对单次记录做上述对账，最后核对全项目会话安全；不依赖旧HOM预处理或项目配置初始化。已明确“未提交任务＋安全关闭”的中断终态可以跳过；不根据缺post帧推断没有计算。缺少收取/采集回执、收尾未确认、坏指标、求解失败等仍保留RECOVERY_REQUIRED，不启动Solver重试。此次没有实现Solver内部续算或所有早期发布缺口的自动推断。

复用ApplicationLogSession双输出和RunOverview；SIMULATION_START/ADOPTED/FAILED包含run、document、definition上下文与源码映射。可读日志目录中的execution-index.json指向control/runs的RunStore。单次摘要不读取旧HOM检查点或展示其覆盖统计；GUI仍可从既有日志入口查看。

回归发现既有停止线程发布竞态：_stop_run在锁内赋值后start，而执行线程原先无锁读取并join，可能出现“cannot join thread before it is started”。现使用同一锁取得已启动线程，再在锁外join，防止与停止线程状态更新死锁；新增确定性故障测试。

## 当前验收与剩余范围

生产G03及公共单次Managed链已经通过一次真实串行Pillbox验收，见[G04记录](single-simulation-g04-acceptance.md)。该次1个模式、一次Start、ACK/DB/采用/标准关闭通过；不推广为全部失败矩阵、所有旧工程或完整MCP宿主闭环。

367项公共服务离线回归、109项G03扩展回归和40项G04最终相关回归分别属于不同批次且有重叠，详情见各报告，不相加。真实校准修正语言声明为带前导单引号的WWB注释；启动前模型SHA256、Decimal范围精度和项目级未知验证会话阻断保持有效。

未完成：验证会话真实中断矩阵/GUI显式操作入口、MCP桌面完整调用及剩余真实故障扩展；公开类型化建模和定义发布已实现并通过SDK真实链。重新验证开始先撤销旧ready并落盘，失败不保留旧证明；退出未知返回RECOVERY_REQUIRED。

[旧阶段全文及原测试数字](archive/20261102-progress-consolidation/single-simulation-service.md)保留供追溯，已经替代的“未注册/未验收”不再作为当前结论。

新增所有者入口export_simulation_results(run_id,result_revision,formats)：只导出已采用结果，受控目录result/exports/<run>/<revision>，格式仅json/csv，CSV保留原始数值、单位和来源ID；重复请求内容一致，有坏工件或旧revision明确拒绝，不重新求解。现已开放Runner鉴权命令及MCP写操作，见[G01–G08记录](g01-g08-progress.md)。

G02新建/检查空文档子集参见[创建服务](project-creation-service.md)，不与已验证仿真definition_revision混用；空document_revision不会自动ready。

## 结果/定义v2与公开导出

新定义schema_version=2将postprocess列表与metric_id纳入definition_revision；旧v1不自动提升/兼容为ready，须从源重新登记并显式G03，旧验收按原日期保留。新结果schema_version=2在派发前冻结参数模型hash、中心积分线端点/轴/beta、能量/公式、算法和实际宏证据，metrics保留请求的metric_id，供JSON/CSV一致输出。查询验证冻结文件，篡改返回RESULT_INVALID。Runner命令export_simulation_results及MCP同名工具已接线，写请求需claim/request_id；不启动CST，不宣称远程工件下载。详见[类型化服务](typed-definition-service.md)。
