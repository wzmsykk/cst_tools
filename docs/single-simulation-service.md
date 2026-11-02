# 生产G03后端接入（2026-11-02）

默认ApplicationService现在注册NativeDefinitionVerifier；历史下文“未注册”是此前状态。stage_definition仍不启动CST、ready=false；所有者显式调用verify_definition才启动验证。可信测试端口仍可注入，客户端不能提供验证证明。

后端从冻结definition.cst复制，不复制同名结果目录；两个串行batch会话分别保存、退出，以及从保存后的.cst重新打开、再保存退出。每阶段在已加载3D Model.run中调用Save、GetOwnProject作用域下已有工程的全局身份/单位/频率读回接口，无OpenFile、参数写入、AddToHistory、Rebuild或Solver.Start。核对CST 2022大版本、精确副本路径、HF Eigenmode、mm/MHz、Tet及频率范围。频率读回按已校准六位有效数字容差；有效历史投影及精确表达式/参数JSON必须与冻结定义一致。方法、模式数、目标开关和自适应等以保存重开后的完整允许表历史为定义证明；不将不存在的live getter或旧执行DB伪装为证明，实际执行配置仍由B3独立核验。

只有每次完成nonce、无宏错误、退出码0、归属进程全部退出、保存后设置和表达式未变、安装hash及源hash未变，才生成四组G03门禁。验证记录及宏/日志/状态位于定义目录verification-<id>；文件夹ID由definition.json的verification.diagnostics映射。失败不更新ready，不强杀；前次会话退出未确认则禁止重试，需要核实session-status及现场进程后对账。本批没有新增GUI验证按钮、HTTP验证命令或自动恢复验证会话，属后续接线范围。现有项目退出恢复扫描尚不自动采用这些验证会话，不能将关闭GUI当作其已退出。

本批为生产执行代码及离线假对端验证，真实WinWrap语法、保存格式变化和完整组合仍需串行副本验收；不能追认既有B4为本轮验收。

# 公共 single-simulation 服务接入

2026-11-02。实现`csttool/application_service.py`，由现有Runner托管。共享[B1/B2保存读取](settings-history-projection.md)、[B3执行验证](execution-snapshot-verification.md)、[原生采集/RunStore](native-execution-capture.md)及Managed Worker，未增加MCP专属执行框架、第二个Worker或后台队列。

## 当前可用边界

已实现公共定义登记/检查、严格单次提交、Runner分发、Managed可选采集、ACK后结果核验/采用、查询和发布缺口对账。**默认生产G03原生定义验证端口尚未注册**：普通登记只产生ready=false，提交返回DEFINITION_NOT_READY，不因B2解析成功、旧B4样例或客户端自报ready而计算。本批正例使用显式可信假验证端口和假Worker，不证明G03、真实新组合或MCP宿主可用。

首阶段只接受root、mm/MHz、单个XYZ真空圆柱/PEC/electric、Default/Tet、关闭自适应、现代网格Version=1、请求1模式、target=min及仅后处理损耗。结果固定为Mode 1的Frequency和中心全范围beta=1的R/Q。继承当前原生采集ASCII路径限制，在预检拒绝非ASCII项目路径。GUI没有新增仿真模式选择；旧HOM/standard入口保持原路径。

## 服务与传输接口

|入口|职责及副作用|
|---|---|
|ApplicationService(project, project_id, installations=..., definition_verifier=..., worker_factory=...)|服务器构造，安装映射为授权引用→路径；默认使用本机发现。两个端口由可信后端注入，不是HTTP/MCP用户字段|
|stage_definition(document_id, source_project, installation_ref)|所有者内部登记，不开放任意路径工具；B1/B2读回、冻结副本及配置、派生revision，调用已注册验证端口后存储证据。不会在缺端口时伪造证明|
|verify_definition(document_id, revision)|显式所有者验证操作；缺端口SETTING_UNVERIFIED，原生实现可能有受控副本副作用。冻结候选被修改即STALE_DOCUMENT，不修改旧定义指针|
|inspect_definition / preflight|只读校验完整性、元数据摘要、project/document/revision、安装及G03状态，不启动CST|
|execute_simulation(payload, run_id, stop, update)|仅构造Runner执行适配器；在Runner线程run时获取现有项目锁并启动Managed Worker|
|get_simulation_results(run_id, result_revision=None)|只读已采用结果及稳定内容revision，核对接收记录与快照hash；缺结果RESULT_NOT_READY，旧revision RESULT_CHANGED|
|reconcile_simulation(run_id)|所有者仅补写已ACK/标准关闭/原生匹配的已收取结果，不调用Worker或Solver|

Loopback Runner继续使用Bearer认证、client_id控制租约、request_id幂等和既有命令记录：

```json
{"operation":"start","payload":{"kind":"simulation","document_id":"document-a","definition_revision":"<server revision>"}}
```

示例省略schema_version/request_id/client_id等既有命令信封字段。simulation payload**恰含这三项**；source_project、installation路径、参数覆盖、algorithm、postprocess、resume、worker_count、ready等都拒绝。模式是明确新执行，重连不得隐式重算。公共D14 submit_run将来映射到此内部传输，不宣称完整九操作或现代MCP信封已经实现。

GET `/simulation-results?run_id=...&result_revision=...`以及`RunnerClient.simulation_results`查询同一服务。业务错误仍通过明确HTTP响应返回，新增code字段；不把DEFINITION_NOT_READY/RESULT_CHANGED当作丢失连接。MCP SDK、server/discover及GUI/CLI完整迁移仍未实施。

## 定义、验证与身份

定义在control/definitions/<document>/<revision>/保存definition.cst与definition.json。revision覆盖document、源hash、配置、安装引用及积分轴；元数据被改、文件变化、跨project或目录逃逸均拒绝。验证端口的proof须绑定同一source_sha256、root和verified状态，具备saved-reopened/identity/settings/standard-close四组门禁。此端口负责真实证据，不能通过客户端JSON注册回调或注入字段。当前没有提供默认真实端口；假端口的测试标签不构成验收。

stage_definition不是完整create_project/apply_model_changes/configure_simulation实现；document_revision编辑与候选发布事务仍待后续。冻结候选只复制.cst，不继承外部同名结果；执行时保存的结构/设置由原有历史重建。参数表达式保留，不传运行中参数覆盖或HOM窗口。

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

## 验收与剩余门禁

[服务测试](../test/single_simulation_service_test.py)覆盖pending拒绝、假端口完整链、原生RunStore真实函数、ACK/采用、严格字段、坏回执/快照/指标/关闭、请求重放、HTTP认证查询、revision变化、发布补写和Runner恢复；Managed测试只检查宏组合与空参数路径，未启动CST。

本轮新服务/新组合未做真实WinWrap/CST验收；此前B4仅证明采集辅助组件，不能追认为本组合通过。下一步实现生产G03定义验证端口、实际保存/重开和新Managed单次链副本验收，再接完整建模操作与MCP宿主；当前生产候选默认不可执行。

## 2026-11-02 本轮验收

公共服务、Managed宏生成、Runner/HTTP、恢复、RunStore、B2/B3及文档索引合计367项通过（79.689秒）；报告：`artifacts/single-acceptance-20261102.xml`。均为离线/假对端验收，本轮未启动真实CST。原生G03定义验证端口仍未注册；缺少该证明的定义不能启动。新Managed组合仍需真实串行副本验收，既有B4记录不能替代。

启动前Worker对复制后的工程再次核对冻结definition SHA256，防止预检后文件变化再启动CST。频率目标与下限用Decimal精确值比较，避免float舍入将不同定义误判相同。本轮pytest临时副本清理后需重新生成；轻量XML报告保留。

G03补充：重新验证先持久化ready=false并撤销旧proof，异常不遗留旧授权。项目目录内任何G03会话退出未确认，preflight返回RECOVERY_REQUIRED，禁止后续单次提交；这不等于现有GUI恢复已能自动处理验证会话。

验收：扩展回归109项通过（25.66秒，g03-accepted-20261102.xml）；最后项目级阻断修改后相关服务/故障与文档索引39项通过（23.95秒，g03-latest-20261102.xml），两组覆盖重叠，不相加。均未启动真实CST。
