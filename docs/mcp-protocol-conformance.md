# MCP协议适用性与验收矩阵

日期：2026-10-28。状态：**规范阅读与设计审查完成，服务端符合性验收未开始**。关联[MCP设计计划](mcp-design-plan.md)、[完整阅读范围/固定来源](../knowledge-base/mcp-protocol-reading-20261028.md)。下列测试编号是拟定用例，不是已经通过的工具测试。

## 1. 标准版本与职责边界

当前规范基线为[2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)，官方TypeScript定义固定至`ccaf9102ec5eb656eab50ca8333ef49dcd259c26`。M0先证明官方SDK与目标宿主支持这一版本；没有支持证据就不得启动“按最新版实现”。旧版需求按具体版本单列，不能把2025-06-18、2025-11-25和2026-07-28混为一个协议。

|规范内容|强度/适用性|首版设计选择|
|---|---|---|
|JSON-RPC、版本、消息模式、类型|核心必须支持|由已验证官方SDK实现，不自造JSON-RPC或初始化状态机|
|server/discover、逐请求版本/能力|2026版MUST|现代模式必须支持；仅旧模式才initialize/initialized|
|Tools|可选能力；声明后对应要求生效|只声明tools，目录静态、有序；业务工具不是协议RPC方法|
|Resources/Prompts/Completions|可选能力|不声明；工件引用先是业务数据，不承诺resources/read可取|
|MRTR/Elicitation|核心消息模式，使用能力可选|SDK需识别正确结果形态；首版业务不主动请求用户输入，不依赖此能力|
|Subscriptions/listChanged|按所用功能触发的要求|不广播动态清单或业务事件；无需为轮询结果自造订阅|
|Roots/Sampling/Logging|此版已Deprecated但未Removed|阅读全文后决定不新增；日志用stderr及现有log/jsonl|
|OAuth/HTTP安全|HTTP授权按采用情况适用|首版stdio不启OAuth；未来HTTP单独实现其规范，不声称现有Bearer回环接口已满足MCP HTTP|
|Tasks扩展|显式双方能力协商后才可使用|首版不声明；受理工具快速返回run_id，后续业务查询|
|Runner所有权、ACK、快照、HOM恢复|本项目业务要求，不是MCP核心规范|保持权威与安全门禁，不由协议结果替代|

stdio可采用固定项目服务配置，但不能把连接身份当对话身份；跨调用状态显式使用project_id/run_id/control_handle，调用者授权每次检查。clientInfo/serverInfo为自报展示信息，不是Runner instance_id或认证凭据。

## 2. 规范→设计→拟定验收用例

标记“必须”只指对应规范范围的强制要求；“本项目要求”不能反向说成MCP标准。未采用能力不必为凑齐工具而实现，但不能声明虚假支持。

|编号|官方章节/规范要求|本项目实现边界及拟定测试|
|---|---|---|
|N01|[基础](https://modelcontextprotocol.io/specification/2026-07-28/basic)：JSON-RPC2.0、合法ID、通知无ID且无回复|SDK处理；非法JSON/nullID/重复在途ID/通知响应测试；新RPC重试换JSON-RPC id，业务request_id不换|
|N02|[版本](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)：请求带version/clientCapabilities，未知版本-32022|缺字段-32602；缺必需客户端能力-32021；交错请求不同能力不得串用前次能力|
|N03|[discover](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)：必须提供发现|server/discover无需先initialize，返回实际supportedVersions/capabilities；不能只改服务名称冒充新版|
|N04|基础/Schema：现代结果有resultType|响应不漏complete；不把Runner run_id映射成未经协商的task；不保留旧版无resultType兼容路径|
|N05|[stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)：UTF-8、单行消息、stdout纯协议|启动/调用/错误/退出无print污染；中文路径与转义换行正常；stderr普通日志不被误判成求解失败|
|N06|stdio EOF及时退出|stdin关闭/宿主结束/Job Object清理，适配进程释放自身资源但不连带停止独立Runner/CST；不靠等待40分钟Solver返回退出|
|N07|[Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)：声明工具能力并列出目录|tools/list确定排序，未claim或上一个调用不改变同授权目录；只读/写权限由服务配置和每次授权决定|
|N08|[缓存](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching)：指定结果ttlMs/cacheScope必需|discover/tools-list含非负ttlMs，目录/项目可识别信息首版private；不缓存业务命令为成功；TTL不代替权限或自动轮询策略|
|N09|[JSON Schema](https://modelcontextprotocol.io/specification/2026-07-28/basic#json-schema-usage)：默认2020-12、禁止默认网络解引用|输入根object；outputSchema合法；拒绝网络$ref、限制深度/组合复杂度；没有必要只支持自造Schema子集|
|N10|工具结构化结果及outputSchema一致|业务DTO在structuredContent，content提供一致文本；成功和isError失败都符合输出Schema；NaN/Infinity不入JSON|
|N11|协议错误与工具执行错误分层|未知method/tool/坏封装返回协议error；CONTROL_BUSY/错误频率顺序/CST失败以isError=true返回可行动说明；不滥用MCP保留码|
|N12|[取消](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/cancellation)：stdio通知、HTTP断流|请求可取消部分尽快停止且取消后无响应/进度；已经独立受理的业务任务需stop_run，不因协议断线自动取消；前后竞态对账|
|N13|[进度](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/progress)：需活跃token，严格增加，完成后停止|不发送无token/已完成token进度；CST局部百分比重置不直接映射协议progress；读状态与实际覆盖分离|
|N14|[分页](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/pagination)：cursor不透明，空字符串可有效|tools-list分页正确终止；业务list_modes游标另绑定检查点版本/快照，更新明确RESULT_CHANGED，限大小/条数|
|N15|能力/状态独立于连接；有状态工具显式句柄|两组交错工具调用不共享“当前run/控制者”；项目/实例/句柄串用被拒；重启不隐式复活控制权|
|N16|工具访问控制、限流和输出清理为Tools必须要求|路径逃逸、Windows junction、伪造ID/外部URL/可执行路径注入、并发过量调用受控；无任意代码/磁盘读取入口|
|N17|Annotations仅提示，不是权限|只读工具readOnlyHint=true；写工具不虚标只读/幂等；客户端无审批UI也不越过服务端授权和项目锁|
|N18|MRTR规则：新ID重试、能力声明、requestState完整性|首版不主动产生input_required；SDK相关类型支持验证；若未来启用必须校验签名/期限/主体/业务摘要且不重复写入|
|N19|订阅需显式opt-in，ack在前，带subscriptionId|首版不声明listChanged/资源订阅，不发送未订阅通知；新增时再验证乱序、重连、拆订阅规范差异|
|N20|资源/提示/补全/弃用能力按实际声明|首版不支持的RPC返回method-not-found；工件local-only/missing/truncated清楚，不能返回不可读取URI还宣称支持下载|
|N21|[HTTP传输](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)：新端点/header/Origin/断流|非首版；未来必须单POST端点，检查version/method/name头与body一致、Origin及认证，不用旧GET/session-id/Last-Event-ID假装2026行为|
|N22|[授权](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)：受众/PKCE/资源/发现等|非首版；stdio保留OS/配置边界，现有Runner token只在内部使用；未来HTTP不能透传宿主token到Runner或第三方|
|N23|[Tasks](https://github.com/modelcontextprotocol/ext-tasks/blob/b3d28aceaa6d49f5f92258e3d06b61ad6f111e84/specification/2026-07-28/tasks.md)：可选扩展，必须声明后使用|首版无task结果；未来应先持久创建、get/update/cancel、期限与逐请求鉴权；tool isError可task completed，禁止把CST FAILED直接当协议Task failed|
|N24|业务可靠性（本项目要求）|丢提交回执、重复RPC、新旧实例、租约争用/过期、未知start取消、MCP退出和恢复均不重复Solver/采用；N01重试换RPC id不改变业务ID|
|N25|业务完成证据（本项目要求）|受理≠Solver完成；状态终态≠安全关闭；ACK/回执/快照/模式产物及前沿核验沿现行门禁，不省略恢复或覆盖缺口|

## 3. 标准消息与业务数据分层示例

以下是按2026版本设计的静态示例，不证明已存在服务端。请求的`request_id`是业务参数，外层`id`是协议ID。

```json
{
  "jsonrpc": "2.0",
  "id": 41,
  "method": "tools/call",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    },
    "name": "submit_run",
    "arguments": {
      "project_id": "project-example",
      "control_handle": "control-example",
      "request_id": "scan-start-example",
      "resume": false,
      "start_mhz": 500,
      "initial_window_stop_mhz": 550,
      "target_stop_mhz": 1000
    }
  }
}
```

```json
{
  "jsonrpc": "2.0",
  "id": 41,
  "result": {
    "resultType": "complete",
    "isError": false,
    "content": [{"type": "text", "text": "命令已受理；仿真尚未完成，请按run_id查询状态。"}],
    "structuredContent": {
      "schema_version": 1,
      "ok": true,
      "operation": "submit_run",
      "request_id": "scan-start-example",
      "project_id": "project-example",
      "instance_id": "runner-example",
      "run_id": "run-example",
      "accepted": true,
      "state": "PREPARING",
      "execution_active": true,
      "session_safety": "unknown",
      "recovery_required": false,
      "data": null,
      "error": null,
      "artifact_refs": []
    }
  }
}
```

如果稍后CST求解失败，get_run_status仍可成功返回状态查询结果（isError=false），data中的业务state可为FAILED；不能因为运行失败就说“查询协议失败”。如果submit_run因CONTROL_BUSY未受理，才是该次工具业务失败（isError=true、ok=false）。未知方法或缺必需元数据则是JSON-RPC error，不返回上述业务成功壳。

## 4. 现代协议支持及进入实施的条件

1. 固定官方SDK发布版本、协议版本、宿主版本及支持矩阵；检查实际导出的消息，不凭SDK名称/官网SDK等级或参考代码导入路径推断兼容。
2. 首先测试所选现代基线的server/discover及逐请求元数据。目标宿主/SDK仅支持旧版则记录阻塞，升级或更换支持组合；不实现旧版握手、自动降级或双协议栈。
3. 对新版规范现存措辞差异见阅读记录，暂不采用动态订阅/自定义协议错误码；不掩盖冲突也不自行宣布协议裁定。
4. 首版静态工具列表与业务受理轮询可不依赖Tasks扩展。将来只有明确需要标准任务互操作时再加扩展，不先做第二套调度/完成持久层。
5. M0包含本矩阵和阅读成果，但不能因此勾选M0全部完成；SDK/宿主适配证据、具体Schema与故障测试尚缺。M1–M5均pending，不用本次文档测试替代协议客户端、宿主或真实CST验收。

## 5. 本轮静态核查（2026-10-28）

文档索引2 passed（0.66s），报告artifacts/mcp-standard-docs-20261028.xml。上文两份消息示例通过固定官方2020-12 JSON Schema（155个定义）校验；去除请求_meta、去除响应resultType的两个反例均被拒绝；相关本地链接有效。详情artifacts/mcp-authoritative-reading-20261028/static-checks.json，不保证随Git迁移。

首轮校验脚本错误地把官方$defs搬到definitions导致本地引用失败，修正脚本保留原Schema后通过；官方Schema未修改。该结果只证明静态示例及文档约定，不证明本项目服务或SDK已符合N01–N25。阅读/设计文件尚未提交，未启动CST、安装SDK或变更宿主配置。

最终文档修订后复验：documentation_index_test.py 2 passed（0.64s），artifacts/mcp-standard-final-docs-20261028.xml；新增文档本地引用逐一核实通过，diff空白检查通过。

2026-10-28 SDK/宿主静态补核：固定mcp 2.3.0及Codex rust-v0.165.0-alpha.1.2源码现代路径，见[支持记录](../knowledge-base/mcp-sdk-host-support-20261028.md)。本机CLI版本已核实但非当前桌面runtime可复现身份/已开启证明；N01–N25仍未执行。SDK默认兼容行为必须在本项目modern-only门禁中限制，不能因版本支持自动勾选符合性。
