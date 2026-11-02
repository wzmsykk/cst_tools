# G01–G08推进记录

更新：2026-11-03。本轮按近期清单补生命周期、真实故障和现代协议入口；不将部分子链当完整首阶段通过。宿主由用户指定为Codex桌面应用。

|门禁|当前事实|尚需完成|
|---|---|---|
|G01 宿主/协议|Codex九工具实际发现/创建/检查/重发/退出已验；源码14工具及现代SDK/stdio通过|用户选择稍后做新增五工具的桌面整链；完整N01–N25仍待验|
|G02 新建/建模|公开create/apply/configure构造参数化真空Pillbox；保存表达式/说明；新对象单脚本归属门禁；原生材质/体积/盒读回通过|桌面完整调用、真实XYZ扩展和其它几何另验|
|G03 持久设置|生产保存重开核验及原生单位/solver/mesh/频率、实体/六边界通过；背景PEC按持久历史/重放证据|全异常/控制器退出矩阵、更多版本/材料仍待验|
|G04 实际计算|公开定义实际一次Start，ACK/原生DB/采用和标准关闭；采用回执缺口真实修复、恢复不求解|求解失败/ACK其它时点及宿主异常矩阵未全部覆盖|
|G05 后处理|1147.42692991921MHz、223.541439593232Ω；中心Z/beta1/full/能量/公式、算法和实际宏hash随结果冻结|指定桌面对话交付待做；其它算子、位置/轴不据此扩展实测|
|G06 物理合理性|与理想TM010相对误差约0.000144%，通过5%；原生几何证据独立核对|不是场型追踪或R/Q收敛证明|
|G07 输出工件|公开MCP/Runner JSON/CSV导出，重复请求一致，hash/路径/大小核对；采用日志不重复|桌面引用交付、远程资源下载未验/未实现|
|G08 资源/归属|本次求解Worker标准关闭、Runner退出、物理pending=0；旧失败候选按退出事实退役，不伪造退出0|旧abandoned-dead保留不确定退出记录；全故障/桌面矩阵待补|

## 验证会话恢复语义

`definition_sessions.definition_session_facts`读取定义目录verification-*/<phase>/session-status.json，核对已保存的PID+创建时间，并检查精确副本路径进程。PID复用不等待新实例；身份缺失/无权限保持unknown，阻断退出；退出未确认的活实例只等待正常batch返回，等待有界、可暂停。发现进程已退出但缺少成功回执时仅写abandoned-dead，无退出码伪造、不授予ready、不重新运行验证或Solver。完整重新验证仍须显式调用。

较早G03生产器把退出码保存在verification.json.sessions，而不是每阶段状态；现仅在已确认退出时读取其对应phase的唯一原记录，不按文件存在推断0。生命周期读回不写ready。Runner退出核验、项目恢复和GUI生命周期文本复用该事实；单次执行与恢复适配器也提供生命周期探针。

## 本轮真实故障证据

验收目录artifacts/single-recovery-e819a0d9；只读取前轮已保存source.cst，在新项目目录登记并进行生产G03。对最终simulation-result.json写入注入一次OSError，发生在ensure_adopted之后；Worker先按协议关闭并保存原生采集。随后reconcile两次：结果恢复，Solver总调用仍1，events.jsonl字节未变化，未重复采用，源SHA256不变。物理结果与前轮相同。

[可迁移轻量JSON](../knowledge-base/single-simulation-recovery-evidence-20261102.json)含结果binding/hash和导出工件。artifacts中的日志、宏、帧和数据库归档保留；原始场/网格及pytest副本清理后需重算，不保证随Git迁移。

## MCP适配范围与安装

Python3.11+安装可选依赖：`pip install -e ".[mcp]"`；非MCP GUI/Runner不导入SDK。`python -m csttool.mcp_server --project <固定授权项目>`运行stdio。首批当时注册5个工具：get_project_status、connect_project、control_project、submit_run、get_simulation_results。无公开建模/导出工具时不冒充已支持。

读取状态/结果不启动Runner或CST。连接需显式launch=true才能启动独立Runner；写请求带control_handle和request_id，实际授权/租约/幂等由既有Runner执行。句柄仅当前适配进程有效，重启须重新连接；EOF不停止独立任务。工具输入使用严格JSON Schema拒绝未知字段，读操作标read_only，结果为structuredContent和现代resultType。适配器不持有CST对象或第二调度队列。

本机临时独立SDK环境为artifacts/mcp-runtime（与系统site-packages隔离，pip check通过）；它是验收依赖环境，不能当原始场垃圾目录删除后还期望宿主服务启动。全球Codex配置新增cst-tools-acceptance，固定绑定artifacts/mcp-host-acceptance；配置启用不等于G01通过。不修改其他服务或启动CST，后续可迁到正式独立环境。

官方依据：[Python SDK v2变更](https://py.sdk.modelcontextprotocol.io/whats-new/)、[Codex MCP配置](https://learn.chatgpt.com/docs/extend/mcp)、[2026-07-28规范](https://modelcontextprotocol.io/specification/2026-07-28)。SDK支持与本机宿主支持分开验证。

## 前批验收与当时下一依赖（下文有后续实测）

生命周期/公共服务/Runner/故障与文档索引110 passed（82.85秒，artifacts/gates-acceptance-20261102.xml）；官方SDK现代stdio及适配5 passed（3.14秒，artifacts/mcp-accepted-20261102.xml）。集合/环境不同，不相加为全仓回归。后续小幅事实返回清理另有定向复验。

SDK验收期间发现MCPServer默认会声明prompts/resources/listChanged，即使业务未注册对应能力；本项目通过官方middleware把discover声明收敛到固定tools={}，不声明订阅/资源/提示词。默认函数参数校验可能忽略额外键，现严格JSON Schema预检并声明additionalProperties=false。SDK负责协议与帧；本项目只约束能力和业务输入。

已在独立环境安装完整.[mcp]依赖，未修改系统环境；pip check再次核对。下一主依赖仍是公开建模/定义事务与真实宿主调用。当前聊天工具清单未热加载新服务器；用户已启用的事实不能代替实际调用，需宿主刷新到能看到这5个工具后继续G01。不得为凑验收启动另一个AI聊天冒充当前宿主对话。

最终补充：事实返回与导出输入收口后39项定向复验通过（17.27秒，gates-final-check-20261102.xml）；G03将启动时PID/创建时间传入公共wait_probe，防止首轮观察前PID复用，补确定性回归。最后相关身份/验证/索引37项通过，见gates-identity-20261102.xml。此额外身份保护为离线验证，未重跑真实CST。

## 重启后的G01定位与G02推进

桌面日志确认旧握手被modern-only以-32022拒绝。此前注册遗漏了宿主feature mcp_2026_07_28及服务env CODEX_MCP_PROTOCOL_VERSION=2026-07-28；查本机features和[官方源码/测试](https://github.com/openai/codex/blob/main/codex-rs/rmcp-client/src/protocol_mode.rs)后补齐。未静默降级服务协议。随后当前桌面实际加载5个工具，成功connect/status/claim/shutdown并观察验收Runner PID18920退出，未启动CST；无效句柄实际被拒绝。[脱敏证据](../knowledge-base/mcp-codex-g01-host-20261102.json)。这是G01基本宿主链通过，不是N01–N25全通过。

实际错误拒绝最初只显示通用错误，现用官方SDK ToolError传播已知业务原因并加SDK断言；这项修正还需新版宿主调用复核。新加入4个工具需要刷新该服务，不能将旧控制句柄用于新适配器实例。用户询问其他会话影响后，尚未擅自刷新共享连接；独立Runner不随适配器退出。

G02空工程子集已实施：[公共API及边界](project-creation-service.md)。原生CST2022自带Python的bootstrap真实通过；typed建模/完整定义发布仍未完成。旧文“只有开发者创建工具”由该子集替代，不等于公开完整建模通过。

用户询问共享会话影响后，新版9工具服务未擅自刷新：刷新可能使同名服务其他聊天的连接/控制句柄失效，但不会主动停止独立Runner/CST；其他名称服务配置不改。G02最后96项扩展回归、22项阶段诊断及5项官方SDK测试分别通过，见对应XML，不汇总为全仓回归。

## 最新：九工具桌面与14工具类型化事务

当前Codex重启后实际发现9工具，显式连接启动Runner60284，create_project生成新空工程；状态COMPLETED/confirmed-closed，get_operation_result/inspect一致，同请求返回同run，shutdown后Runner退出。新增五个编辑/配置/保存/关闭/导出工具在源码/官方SDK可见，当前桌面仍需重载才能调用；没有擅自刷新共享连接。

G02–G03：已实现类型化草稿与CAS、完整A1副本构造、批量表达式和分段宏、现有G03后端发布；G05把PPS、积分轴/端点/beta/归一化及宏hash冻结到结果v2；G07新增Runner/MCP鉴权幂等导出。见[当前接口](typed-definition-service.md)。G01目录按名称排序、private/ttl=0、tools-only拒绝其他RPC，控制句柄和并发有界，SDK测试另记。

真实14工具SDK场景typed-public-74b38a64在new环境阶段超时，没执行new_mws、typed模型或Solver。退出保持待恢复；官方按PID接管又暴露wmic缺失，不能据此断言最初超时的唯一原因。见[知识库](../knowledge-base/cst-native-bootstrap-startup-20261102.md)。截至本批记录，该实例未正常退出，不继续并行真实验收。

相关分批测试：79项Runner/生命周期/G03/草稿等回归通过（58.19s，gates-regression.xml）；52项服务/草稿/来源通过（28.63s，gates-final-service.xml）；6项SDK/适配通过（5.40s，gates-sdk3.xml）。后续对渲染/PPS绑定/诊断的修改另复验，这些数字不能当作后续代码的全仓验收。

## 2026-11-03 收口

[公开真实验收](typed-public-acceptance-20261103.md)和[轻量JSON](../knowledge-base/mcp-typed-public-acceptance-20261103.json)为最新证据。SDK公开构造→G03→实际求解→恢复采用回执→JSON/CSV→逻辑关闭/Runner退出已验；源码14工具，用户明确将指定桌面新增工具验收留待之后，未标全门禁完成。

新增原生实体材质/体积/结构盒/计算盒/六边界在生产G03保存重开各核对一次；布尔原始CStr=-1按CST2022/WinWrap严格规则识别，参数JSON的descr核对请求说明。154项相关回归、6项官方SDK/适配以及最后41项定向测试分别通过，具体日期/时点见报告，不相加。

单次结果曾RunStore已采用而Worker接收回执仍acknowledged；现先提交结果，再补采用回执，显式恢复在物理会话退出后优先对账单次结果，避免被当作未消费HOM/批量任务。真实恢复保持一次Start、结果revision和采用日志不变。
