# 统一底层迁移与旧入口删除清单

日期：2026-10-28。静态源码审查；尚未删除代码或迁移数据。目标契约见[统一接口](unified-interface-contract.md)。不考虑旧接口兼容，按批次同步所有入口；本表中的“删除”指实施目标，不是当前已删除。

## 1. 已核实的分叉

- [base.py](../base.py) run_backend直接创建CstApplicationBackend并prepare/execute；不是Runner客户端。[base_WTC.py](../base_WTC.py)和[base_tm020.py](../base_tm020.py)通过它注入算法对象。
- [RunnerController](../GUI/runner_controller.py) _command自动claim，_observe默认可能launch并读取HomDisplayReader；维护stop_after_start及专用停止文件，不能整体搬进新的MCP适配器。
- [RunnerBackend](../GUI/runner_backend.py) restore_last_project自行解析manifest/pps，run_payload生成旧algorithm/installation路径对象。[GUI服务](../GUI/application_service.py)仍有显式进程内执行适配CstApplicationService。
- [HomDisplayReader](../GUI/hom_dashboard.py)解析checkpoint、截最近5000模式，表模型截32指标；mtime/size缓存不是稳定revision。[DiagnosticExportThread](../GUI/diagnostic_export.py)直接调用导出函数，不经过命令去重。
- [RunnerClient](../csttool/runner_client.py)透传旧dict、随机默认client_id、保存pending-ui-stop.json，CLI对变更自动claim；HTTP错误转换为RuntimeError文字。
- [Runner.command](../csttool/runner.py)当前摘要包含全部命令和client_id；10秒控制租约、旧操作名及validate_run_payload是当前契约；服务端尚无新expected_instance前提。不能用“客户端查询过status”替代原子核验。

## 2. 旧入口删除/替代表

|ID|当前入口|实施动作|唯一替代/保留部分|
|---|---|---|---|
|X01|base.run_backend直接执行|删除此执行通路及算法对象注入参数|统一CLI→公共客户端→公共服务→执行端口；base入口是否留文件取决于新启动命令，不留旧flag别名|
|X02|base_WTC/base_tm020各自调用run_backend|删旧包装，策略按注册ID提交|保留WTC/TM020算法实现及PPS，未审查策略Schema时标不支持，不能静默改成HOM|
|X03|GUI.application_service.CstApplicationService、ApplicationBackend执行Protocol、RunRequest重复校验|删除GUI进程内执行适配；测试迁向公共客户端/假执行端口|GUI纯草稿/展示可保留，但使用公共请求类型/校验|
|X04|GUI.RunnerBackend.run_payload和restore_last_project的业务解析|删除旧payload及manifest/pps解析分支|本地项目记忆保留；inspect返回统一配置摘要，草稿不持有执行事实|
|X05|GUI.RunnerController._command自动claim/_observe隐式launch|移除自动控制/启动语义；重构为具名操作调用|QTimer、线程池、Qt信号与旧响应防串线保护属于GUI资源层，可保留|
|X06|GUI.stop_after_start、RunnerClient.save/pending/clear_stop_request及pending-ui-stop.json热路径|删除GUI专用持久意图通路|公共客户端发送前请求记录+服务端cancel_submission墓碑；未决旧停止意图先显式对账，不能直接删文件|
|X07|HomDisplayReader.read的checkpoint解析/cache|删除解析类，迁到result_query；GUI仅页缓存和渲染|HomModeTableModel/仪表盘保留，明确分页/截断；指标单位由公共契约提供|
|X08|DiagnosticExportThread.run直接export_failure_bundle|删除直调；QThread可改为公共异步调用|export_failure_bundle保留为后台组件，仅公共服务协调幂等、预算和工件|
|X09|RunnerClient.command通用旧dict、HTTPError文字、main旧CLI|改成公共具名客户端/错误；删除旧命令格式和CLI flag兼容|底层HTTP/发现/正常退出所有权核验复用可测实现，不另造第二个传输客户端|
|X10|Runner.command/validate_run_payload/旧execution_contract.validate_command|用统一模型/公共服务替换；删重复校验和旧operation别名|Runner持久命令、锁、运行线程、进程归属与正常退出职责保留，按新契约调整|
|X11|CstApplicationBackend的可由前端直接使用的配置→initialize→prepare→execute序列|降为后台执行端口内部；取消前端公开执行通道|现有准备、算法、Manager、Worker及日志清理实现逐步归并，不复制一个新Backend|
|X12|旧error字符串和GUI按缺字段猜状态|删除字符串协议及兼容默认值|公共Error/快照，展示翻译可在GUI，业务分类唯一|
|X14|GUI.main_window构造时uses_runner双分支、GUI.run_controller._BackendRunWorker及进程内执行控制器|删除进程内执行选择分支与执行Worker；测试注入统一假客户端/执行端口|保留必要RunState展示类型，不能因其仍被引用就保留整条直接执行路径|
|X13|此前拟定mcp_service.py独立服务/控制日志|撤销提案，不创建模块|application_service公共服务；协议层仅关联MCP请求与业务request_id|

不因名称含legacy就删除：utils保持不变；测试夹具、离线探针和历史验收工具单独标记用途。实际引用归零及替代测试通过才删除文件，不能按本表盲删整模块。

## 3. 后台、GUI与CLI同步迁移批次

|批次|后台|GUI/CLI/MCP|完成门禁|
|---|---|---|---|
|S0 静态冻结|核对操作、状态、安全枚举、方法/策略Schema与磁盘归属|列出所有入口及交互映射；核实官方SDK/宿主|本文/契约评审完成，未冻结能力显式禁用；不运行CST|
|S1 唯一模型与服务|公共请求/响应/Error，Runner托管服务；迁命令原子前提、控制、幂等|公共客户端和CLI一起更新；GUI操作一起切换；MCP按唯一模型生成Schema|旧契约拒绝、各入口相同校验/副作用；旧模块引用清零；不是先发布新后台再保留旧GUI|
|S2 查询与配置|公共inspect/result_query/事件读取；run→scan/revision来源|移除GUI文件解析；MCP/CLI相同分页；GUI显示仅已确认覆盖和结果|更新/被删快照、缺单位/归属、超预算、只读无修复写入测试|
|S3 生命周期与诊断|公共取消墓碑/导出幂等、失败收尾事实|停止/恢复/退出调用统一；仅关界面与停止后退出仍明确分开|假Worker独立进程响应丢失、跨入口争用、断连/退出、停止/采用对账|
|S4 删除与交付|删除X表旧入口/别名/重复校验，锁定唯一启动链|更新帮助、打包脚本、安装/操作文档、源码映射|包内CLI/GUI/MCP身份一致；无旧入口残留；离线与文档测试|
|S5 真实串行副本|现有CST执行链按新契约验证|同run跨入口查询/停止/恢复|另行授权；核对Solver次数、唯一采用、表达式、快照/结果及标准收尾|

批次是实现审查单元，不要求各批次可与旧版本混用。内部可一次完成多个批次再发布；不得用兼容层维持半迁移状态。每批次实际实现后再更新状态/索引/TODO并测试，是否提交推送仍需用户指令。

## 4. 故障分支与静态修改落点

|触发点|现行代码落点|新契约要求/待修改|
|---|---|---|
|HTTP响应丢失/超时|RunnerClient.request；Runner.command持久意图先于执行|公共请求先记ID，查原命令，不生成新start；同ID不同内容冲突|
|实例替换/控制过期|RunnerClient.status校验；Runner.command内10s租约|公共服务命令锁内校验expected_instance/run；统一120s显式续期，不把查询当续租|
|start未知时停止|GUI.request_stop、pending-ui-stop；Runner.cancel_start|发送方统一保存意图，服务端墓碑与start在同锁竞争；结果未知继续对账|
|Controller/GUI意外退出|Runner独立线程/进程，GUI.detach|协议取消/关闭界面不停止run；释放控制与资源，恢复原请求身份|
|求解失败/后处理异常|LocalExecution.run、生产宏solver-result及Worker收尾|保留阶段/结果事实；失败不等空窗，安全未知阻断新提交|
|ACK后、采用写入前崩溃|RunStore.ensure_adopted、后端_reconcile_checkpoint_adoptions|恢复服务核对检查点/receipt再补写；result_query禁止调用会修复日志的reader|
|退出期间重复清理|Runner._execute finally、Backend.close_logging、Worker.stop|一个所有者负责每个资源关闭；传播cleanup error，状态终态与execution_active分离|
|历史run查询|control/runs/*/outcome.json与滚动checkpoint|增加run→scan/revision/工件映射；不存在返回不可用，不借最新结果冒充|

## 5. 数据与切换边界

1. 先正常停止旧后台、确认相关CST会话及目录占用已处理；不能在活跃求解上直接替换二进制/协议或强制清锁。
2. 分开配置、命令/控制记录、扫描检查点、RunStore及结果工件。命令格式升级不自动改写历史日志/结果；过期控制凭据不迁移复活。
3. 一次性迁移工具默认dry-run，输出源哈希、能证明的身份、缺失证据及计划目标；验证成功后写新目录，再原子切换指针。冲突/未知不覆盖，不启动Solver；原始证据保留。
4. 旧run_id与scan归属不能从单个checkpoint推导。没有证据就标unknown，只允许离线检查或等待人工提供证据，不编造task/单位/物理模式ID。是否允许继续扫描由恢复校验决定。
5. 旧pending-ui-stop意图先对账；不得因“不兼容”删除用户已表达但未落实的停止请求。旧日志可直接留作证据，禁止热路径加入永久双格式业务reader。

## 6. 实施验收清单（本轮未执行）

- 每个公共操作：正确、缺字段、额外字段、错类型、非有限数、越权路径、旧contract拒绝。
- 三入口交叉：同request去重、异内容冲突、控制争用、实例切换、响应丢失；一次Solver/一次采用由执行计数与日志共同验证。
- 查询：相同revision分页无遗漏/重复，更新明确RESULT_CHANGED，缺历史映射不套当前数据，读取不改RunStore日志。
- 生命周期：GUI仅关闭、MCP EOF、CLI退出、停止后安全退出后台均各自明确；失败和收尾未确认保留可恢复事实。
- 打包：移除旧入口帮助/文档指令，Qt与MCP依赖不污染无GUI后台启动；源码身份可对应报告。

本轮只读取源码并记录迁移设计，没有执行删除、生成运行Schema或新增依赖。参数表达式、已确认结果、物理覆盖和CST归属安全是迁移不变量，不作为旧API兼容问题处理。

S0补充证据：后处理与优化子契约已冻结，见[子Schema及O01–O06](postprocess-optimization-subschemas.md)；旧参数转换不能直接作为严格验证器，优化策略在缺口修复前不开放。官方SDK/宿主固定来源已核实，但实际桌面现代协议配置/握手仍pending。X02迁移必须处理自动载旧种群、目标维数和候选失败事实，不只改提交包装。
