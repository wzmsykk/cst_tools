# 本机Runner接口与使用

2026-11-03基础核对；本批冷启动修正见[冷启动就绪与诊断](runner-startup-readiness.md)。当前仅本机执行；[复审前完整原文](archive/20261103-semantic-review/local-runner.md)保留阶段变更/验收。不能把本页HTTP当现代MCP协议，也不能说MCP服务尚不存在。

## 执行与控制

生产GUI为RunnerBackend配置草稿→RunnerController异步客户端→独立Runner。批量/HOM经LocalExecution和应用后端；公共定义/单次经ApplicationService，复用Managed/RunStore。MainWindow也支持注入进程内后端供测试；根base系列CLI为直接后端入口。

Runner持操作系统项目所有权，客户端控制租约另有期限。GUI失联/仅关界面不停止后台；正常断开尝试release，崩溃后可在10秒租约到期后申请控制。连接状态未知不代表CST已停。

GUI正常重开可找回上次项目并连接/必要时启动状态服务，不自动start/recover。启动意图未确认时停止保存原request_id并发cancel_start，不制造第二次启动；切换项目使用连接代次，未确认停止意图不能被切换丢弃。完整退出编排stop→标准收尾→shutdown/所有权核验→本地资源清理；失败可选择仅断开，不强杀制造成功。

## 冷启动与就绪

默认15秒连接预算未加长，初始HTTP探测和就绪等待共用剩余预算。合作客户端经bootstrap.lock协调启动，实际Runner所有权仍由runner.lock保证；已有后台或启动尚未确认时不重复派生/提交。control/bootstrap.json给出阶段、首末探测错误及启动器退出，bootstrap.log保留客户端/子Runner事件。超时不是进程死亡；仅显式重连，迟就绪成功会更新摘要。phase/state和CST关闭、G03、任务采用分别判断。已有GUI/MCP进程需正常重载新Python客户端代码，非热更新验收。

详见[冷启动就绪与诊断](runner-startup-readiness.md)及失败诊断包；不启动CST的受控进程已验证正常、早退、迟就绪和静默端点，原现场唯一根因仍未确认。

## CLI

```powershell
python -m csttool.runner --project D:\projects\example
python -m csttool.runner_client --project D:\projects\example status
python -m csttool.runner_client --project D:\projects\example start --config run.json
python -m csttool.runner_client --project D:\projects\example stop
python -m csttool.runner_client --project D:\projects\example recover
python -m csttool.runner_client --project D:\projects\example shutdown
```

Runner --fake仅用于明确的合成验收。CLI先连接已有Runner；除shutdown的离线核验分支外不自动启动。start配置默认kind=hom，或kind=standard并给tasks；resume、worker_count、source_project、installation、algorithm、postprocess须符合校验。定义/单次JSON由公共契约描述，CLI不自动编造定义revision。默认Worker1、HOM常规nmodes=1。

## 本机HTTP合同

监听127.0.0.1临时端口；control/runner.json保存实例身份/令牌。Authorization: Bearer及X-Client-ID，拒绝Origin，不走系统代理；尚无远程TLS/节点传输能力。项目凭据目录不能公开共享。

|入口|作用|
|---|---|
|GET /status|Runner、项目、当前run、活动事实、lifecycle/error/cleanup诊断及恢复/覆盖摘要；终态标签不等于资源已释放|
|GET /events?cursor=<JSON>|v2分页事件游标，原样回传对象；限字节/事件/长行，截断或轮转有诊断；不是控制器|
|GET /commands/<request_id>|持久接收/幂等记录；未找到不代表迟到启动已取消|
|GET /installations|授权安装引用与显示名，不启动CST|
|GET /definition-result?run_id=...|定义操作结果|
|GET /model?document_id=...&document_revision=...|不可变模型记录检查，不打开原生工程|
|GET /simulation-results?run_id=...|已采用单次结果，可带result_revision|
|POST /commands|claim/release/start/stop/cancel_start/recover/shutdown及export_simulation_results；校验身份、租约、run及payload|

请求schema_version=1，包含request_id/client_id/operation/run_id/payload；同ID同内容返回原结果，异内容拒绝。受理响应不是完成承诺。start可分发hom/standard/simulation/definition，按各自Schema和状态前提执行。导出通过鉴权命令，不增设一个匿名文件下载接口。

MCP已提供可选stdio薄适配器，入口`python -m csttool.mcp_server --project <固定项目>`；依赖/协议及已实现工具见[公共类型化服务](typed-definition-service.md)和[门禁](g01-g08-progress.md)。适配器不持有第二队列或CST对象；EOF不停止独立Runner。

## 停止、恢复与持久事实

StopIntent持久化到control/runs/<run_id>/stop.json，Manager未创建时也可记住。预处理/原生调用返回后检查安全点；正常求解无固定总超时。shutdown等待Runner锁释放，不重新launch，也不强杀。未知物理会话/未闭合意图仍要求恢复；暂停恢复保留证据，下次显式继续。

恢复先核验项目/会话身份、Completion/received/ACK、保存及实际退出，再核验检查点与采用。成功received未采用即使Completion已删仍可能阻断；单次结果采用补写与HOM/标准分别路由。归档路径只按已核身份/hash索引重绑定；不因缺少标记推断没求解。闭合后显式resume，不自动从头覆盖结果。

control存端点/锁/命令/run停止意图/状态/outcome；logs可读目录及application.log/jsonl保存诊断。JSON/INI发布的有界重试只处理同一次文件替换的WinError5/32，不重试求解或ACK语义。收到退出/ACK/日志任何单一信号都不足以证明结果可采用。

## 验收与边界

[恢复退出合同](recovery-exit-audit-implementation.md)、[控制器退出](controller-exit-l5-acceptance.md)、[HOM中断](hom-interruption-l5-acceptance.md)分别保留其批次。指定MCP桌面完整链、完整故障矩阵与远程/分布式不是已通过项；本页语义复审未启动CST。
