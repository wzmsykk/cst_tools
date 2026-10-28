# 独立本机 Runner：API、使用和恢复

2026-10-28：[MCP接入设计](mcp-design-plan.md)仅为计划，以[官方规范阅读及符合性矩阵](mcp-protocol-conformance.md)为标准。拟通过本机stdio适配RunnerClient，不直接暴露当前HTTP为MCP；现代版本不是旧initialize握手。能力探测、结构化错误、显式控制句柄、身份前提和结果分页端点尚未实现。现有GUI/CLI用法与恢复门禁不变，不存在可直接运行的MCP启动命令。

GUI正常重新打开会[自动找回最后项目](gui-session-restoration.md)，连接现有Runner，必要时只启动状态服务读取持久事实，不自动start/recover；当前窗口失联不因此反复重启后台。每用户选择记录不是运行权威；检查点/所有权和显式恢复门禁不变。

2026-10-25：[GUI完整退出](gui-exit-resource-cleanup.md)现编排stop→收尾→shutdown/OS所有权确认→本地GUI清理；仅关界面不停止后台。runtime新增可选cwd诊断，旧服务缺字段按未知显示；停止和RECOVERY_REQUIRED门禁未改变，Task/ACK/VBA wire不变。

L5[采用标记补写](checkpoint-adoption-l5.md)：显式recover和resume准备在项目锁内依据已确认检查点核验并补齐receipt及所属RunStore，不改变覆盖或重算；重复recover不增加同Task采用事件。日志CHECKPOINT_ADOPTION_RECONCILED表示核验/同步数量，非新增导入数量。缺/坏证据保留恢复阻断；wire不变，旧Runner仍须安全重启更新。

L5实际进程退出补验：[六类记录](controller-exit-l5-acceptance.md)。HTTP快照增加execution_active实时线程/执行器状态，终态标签不等于可立即start；GUI保持收尾状态直至释放。归档结果旧路径仅通过身份/哈希匹配的既有索引修复，错误继续阻断，不重复计算。旧后台缺字段沿用旧展示和409门禁，更新需正常退出后重启。

停止/ACK L5实测补充：[十二时点](stop-ack-l5-acceptance.md)。标准退出后即使Completion已清理，当前Task成功接收记录尚未采用也需显式恢复；lifecycle缺证据增加received-result-not-reconciled，结果状态received-unadopted。恢复决定绑定received_task_id，不改变wire或退出码规则。

L5部分真实CST验收修复正常关闭的活动文件失配：新增独立.closed.cst快照，退出/采用策略不变，需Python/VBA同时更新。证据及仍pending见[串行验收](close-v2-l5-acceptance.md)。

2026-10-24 L4：[事实字段与诊断API](runner-lifecycle-l4.md)新增lifecycle/error_diagnostic/cleanup_diagnostic；session_safety增加running、exited-unverified，恢复状态仍独立。旧客户端可忽略新字段，旧后台GUI显示未采集。以下L3“待L4”为当时状态。

2026-10-24 L3：[生产v2状态与退役](production-close-v2-l3.md)已接入新会话源码；Runner控制操作不变。task/model关闭事实更细，失败ACK后不复用同Worker；完整GUI事实展示待L4，真实WinWrap/CST待L5，不把字段存在当运行验收。

2026-10-24：[L1证据核验](session-closure-l1.md)使Backend发现/恢复更保守：未知进程、无可信退出证据或串session回执不再靠stopped标记解除。控制CLI/GUI操作格式不变，不自动重跑任务；close.receipt v2仍未接入。

2026-10-20：[GUI后台管理](gui-runner-management.md)提供当前项目身份、连接与标准退出；快照新增runtime.pid/python/source_root（旧服务无字段时显示未知）。退出必须确认所有权释放，成功后暂停GUI轮询，显式连接不提交计算。现有CLI与安全门禁不变，未实现自动升级/强制退出。

2026-10-20：增加[项目恢复状态对账](project-recovery-state-reconciliation.md)。空闲Runner在启动、查询和命令前核验project.ini；持久恢复门禁不能被FAILED或confirmed-closed掩盖。状态增加project_task_status，触发重对账时保留previous_error并说明recovery_reason；不自动续算。会话安全与项目可续跑性是独立事实。

更新：2026-10-15。当前仅本机，尚不支持远程/分布式执行。

审查修复（2026-10-15）：四项缺陷及配置/执行接口混合已处理；实现、故障验收及剩余边界见[修复记录](runner-audit-fix-20261015.md)。历史源码包不包含本轮修复。

## 执行链与GUI

2026-10-15增补：[GUI日志保留/自动恢复](gui-log-restoration.md)。清空按钮/API已移除；连接已有项目会恢复持久状态与日志历史，事件游标v2增加source，多文件分页，不自动重新运行求解。

生产MainWindow默认使用RunnerBackend配置草稿及RunnerController异步客户端；
真实CstApplicationBackend、Manager、Worker只在独立Runner创建。
测试可显式注入进程内假Backend，不属于第二条生产GUI执行链。
GUI选择项目后连接/启动Runner，重开同项目自动重连；运行/恢复未完成时不能重复提交。

关闭窗口可取消、仅关闭界面保持后台、或安全停止后退出。默认取消。
界面断开不表示CST已停止；重连中显示未知并限制修改。控制权与项目运行所有权不同：
GUI正常断开释放控制权，崩溃后其他客户端可在10秒控制权租期失效后申请；不影响运行。
Runner不会因GUI失联自动退出，空闲时可用CLI退出。Runner崩溃后不自动重启/续算，重新连接发现未完成意图进入需要恢复。

## CLI

在源码根目录、同一Python环境执行；Runner工作目录自动固定到资源根目录，诊断在项目control目录。

```powershell
python -m csttool.runner --project D:\projects\example
python -m csttool.runner_client --project D:\projects\example status
python -m csttool.runner_client --project D:\projects\example start --config run.json
python -m csttool.runner_client --project D:\projects\example stop
python -m csttool.runner_client --project D:\projects\example recover
python -m csttool.runner_client --project D:\projects\example shutdown
```

`--fake`只用于明确的合成验收，绝不启动CST；合成结果不能作为物理结果。
run.json为JSON：默认kind=hom，或kind=standard加tasks；包含resume、worker_count、source_project、
installation(version/executable)、algorithm及postprocess。标准tasks每项job唯一，parameters为参数字典。
默认并发1；HOM依然nmodes=1。标准任务列表恢复时必须不变，不替代优化器。
所有路径目前指本机Runner可访问的位置；ArtifactRef仅提供后续节点位置契约，不代表实现跨机文件传输。

## 本机协议

只监听127.0.0.1临时端口，control/runner.json存实例身份及随机令牌，目录限制本用户访问。
请求带Authorization: Bearer及X-Client-ID；禁止Origin请求，不提供任意方法、shell或pickle执行接口。
不使用系统代理访问本机。目录/凭据不要放公开共享目录，未实现远程TLS部署。

- GET /status：实例、run_id、版本、运行状态、会话安全、错误、覆盖/任务摘要、日志位置；owner_client及control_lease_valid、control_lease_remaining（秒）、control_revision。过期心跳不能复活租约；GUI“申请控制权”在只读时仍可达，服务端原子裁决。
- GET /events?cursor=<URL编码的JSON>：响应schema_version=2，cursor包含generation、offset、discarding；首次可传0，后续原样传回。旧整数输入仍接受，但新客户端须认识对象游标。换运行/实例重置；轮转/截断自动重置。单次最多扫描256KiB、200事件；超过64KiB的行生成带原文件/字节位置的跳过提示，跨请求继续跳过，原始文件不改动。普通未完成尾行等待写完，损坏行产生诊断并前进。
- GET /commands/<request_id>：查询持久接收记录（command/digest/result），不存在返回found=false；未找到不代表迟到启动已被取消。
- POST /commands：schema_version=1、request_id、client_id、operation、run_id、payload。
- operation为claim/release/start/stop/cancel_start/recover/shutdown；修改需有效claim；stop核对run_id。cancel_start的payload为start_request_id：未接受启动先登记取消墓碑，已接受启动仅停止其绑定run，已结束目标不作用于后来的run。未闭合目标拒绝并要求恢复。重复旧claim不能夺回转移后的租约。
- 同请求同内容返回原接收结果，同ID异内容拒绝；命令意图持久化后才执行，响应不是完成承诺。
- 连接/请求有界，计算无固定总超时；HTTP线程与计算线程隔离，GUI轮询在独立线程，有界展示。

状态PREPARING/RUNNING/STOPPING/RECOVERING为活动；COMPLETED/INTERRUPTED/FAILED/IDLE为终态；
RECOVERY_REQUIRED须先恢复。终态与后台日志资源释放间可能存在极短间隔，未释放时拒绝新运行/退出。

## 停止与恢复

StopIntent在Manager未创建时也有效，持久化到control/runs/<run_id>/stop.json；
预处理/构造Worker返回后检查，不再启动下一阶段。阻塞CST调用不能即时抢占。
Backend与Runner共用run_id，Runner操作系统文件锁保护唯一控制器，Backend仍持有项目运行锁。
项目锁新增创建时间/主机核对及OS互斥保护；未知或损坏身份不按文件年龄抢占，须核实原运行归属，跨主机锁不受支持。

GUI启动前固定request_id及深复制配置；不因HTTP超时产生新启动ID。启动未返回/结果未知时选择停止，会先保存control/pending-ui-stop.json，重连后按原启动ID发cancel_start，直到Runner确认接收才清除客户端意图。该文件可由重开的GUI接续；若其他GUI持权须先申请，不能绕过有效租约。尚未交付Runner且再无GUI连接时，不保证自动送达停止。磁盘写失败明确拒绝“已请求停止”，不宣称已安全退出。

切换项目使用递增连接代次，重置实例、运行、日志游标和控制状态，丢弃旧成功和旧异常（包括A→B→A）；旧控制权使用捕获的旧client释放，不自动停止旧任务。尚未确认的停止意图不允许被切换连接丢弃。

生产GUI使用ConfigurationService/ConfigurationDraft，仅持配置；ExecutionControl与RunnerSnapshot描述客户端控制及后台事实。RunnerBackend不再伪造execute/stop/recovery方法。CstApplicationService仅为显式进程内Backend注入适配，默认真实Backend延迟导入。默认HOM设置与mesh校验来自scan_settings；不改变参数表达式或HOM覆盖语义。

HOM求解前登记pending，成功包括空区间时把task_id写入检查点再标记采用；旧检查点缺少新字段可读取。
标准批次在save/standard_batch_checkpoint.json记录原任务签名、pending_index和已接受结果。
Worker发布任务前保存task-context.json，恢复时可核对已完成结果、重读后处理并保存received，再标准收尾。
旧会话没有task-context不能凭空补接收；丢失/损坏快照或不符合身份的完成不作为成功接收。
可选场分析尚未完成时拒绝直接复用为完整结果；保留工件和接收记录，不为补分析而重放Solver。
模型.cst不能替代同名场目录；并非所有中断后的复杂后处理都可无求解恢复，缺必要工件时明确失败。

Runner启动发现旧活动状态或未完成持久启动意图，不重放命令，而进入恢复状态。
先标准恢复残留会话并核对结果，再明确resume提交，不能从头覆盖旧HOM/标准检查点。
死会话与活跃/未知会话区分，停止失败保留诊断；不通过强杀CST使门禁通过。

## 持久化、日志和错误

control包含端点/锁、status.json、命令记录、run级停止意图和outcome；logs仍使用可读目录与双输出。
状态覆盖摘要由计算侧检查点保存后发布，HTTP不反复读取活跃检查点，减少Windows替换冲突。
JSON读取先取得独立文本快照再解码，JSON/INI写入flush/fsync后原子替换；Windows仅同一次文件发布遇WinError5/32
做至多5次短重试，总退避150毫秒，最后失败仍上抛；不重试求解、Ack或协议语义。
这不是断电不丢数据或多机一致性保证。关键写失败不得继续新派发。

可读目录里的中文路径会进入VBA，quote_vb_string用ChrW的UTF-16单元表达，宏源码仍为ASCII。
首次真实验收曾因该编码边界失败，不能把预处理完成当Worker成功，详见统一计划验收记录。

## 入口与验收

实现：csttool/runner.py、runner_client.py、runner_ownership.py、execution_contract.py、standard_batch.py；
GUI/runner_backend.py、runner_controller.py。功能映射见[功能索引](feature-index.md)。
测试：test/runner_test.py、runner_recovery_test.py、gui_runner_test.py、runner_cst_integration_test.py。
阶段与剩余门禁统一见[实施计划](execution-platform-implementation-plan.md)，旧设计的拟议接口不取代本页当前接口。

新实测边界见[Runner/路径知识库](../knowledge-base/runner-process-and-path-boundaries.md)。

## 2026-10-25 HOM真实副本验收入口

生产HOM链的checkpoint/received/solver中断对照见[小网格HOM](hom-interruption-l5-acceptance.md)。恢复继续使用既有显式recover和resume；HOM模式快照的项目相对路径由采用核验正确解析，不按Runner cwd解析。不改变HTTP命令、Task/ACK或VBA wire；旧Runner需正常停止并更新，不能靠替换文件热修复已导入模块。

2026-10-25新增[一键导出失败诊断](failure-diagnostic-export.md)：日志区按钮直接生成项目diagnostics ZIP，即使Runner离线也可收集本地证据；不发控制指令，不读取endpoint认证文件，不是新增HTTP接口。
