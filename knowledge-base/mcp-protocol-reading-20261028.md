# MCP官方规范阅读记录与项目适用性

日期：2026-10-28。用途：本项目MCP设计的协议基线；**阅读/设计记录，不是实现符合性认证**。

## 1. 权威来源及完整阅读范围

从[官方规范入口](https://modelcontextprotocol.io/specification)进入，当日跳转到正式日期版本[2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)，以[官方完整目录](https://modelcontextprotocol.io/llms.txt)枚举章节，不再用COMSOL实现或三篇旧版规范替代协议标准。`draft`不是本轮基线。

已逐章读取该版30篇规范正文（包括本项目不采用的可选与已弃用能力），并完整读取消息定义的TypeScript源文件。官方生成的schema.md已获取，但未把其重复生成的所有类型说明再逐行复读；schema.json获取并解析核对，不声称其经过SDK实现级验证。完整指的是选定版本的规范正文与类型定义，不包括所有外链RFC、SEP历史讨论、全部旧版规范或SDK源码。

来源优先级：官方日期版本规范的规范性条款与官方TypeScript消息定义共同构成标准；生成JSON Schema用于自动校验；官方指南用于实现指导；COMSOL MCP只是非规范性实现参考。MUST/SHOULD/MAY按规范使用的BCP14区分，不能把项目自定约束标成协议要求；示例不是优先于正文的规则。

TypeScript/JSON Schema来源固定在官方仓库提交`ccaf9102ec5eb656eab50ca8333ef49dcd259c26`：

- [schema.ts](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/ccaf9102ec5eb656eab50ca8333ef49dcd259c26/schema/2026-07-28/schema.ts)，3197行，SHA256 `742750af0bb8c716e7030c4977c992b55d1adc4407e9e66997db5846baedc2cd`。
- [schema.json](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/ccaf9102ec5eb656eab50ca8333ef49dcd259c26/schema/2026-07-28/schema.json)，SHA256 `ef70b61f99b6d2e5e3b46863822eab08dff6a45bedc7a08914e0e5b133f40203`。

官网30篇正文、生成Schema参考页、原始类型文件及下载SHA256清单保留在`artifacts/mcp-authoritative-reading-20261028`。轻量来源索引见[mcp-protocol-sources-20261028.md](mcp-protocol-sources-20261028.md)，可随Git迁移；artifacts原文快照不保证随Git迁移。清理后可按URL重新获取，并核对哈希，不能把新官网正文当作旧快照。

## 2. 已读章节及本项目取舍

以下路径均相对`https://modelcontextprotocol.io/specification/2026-07-28/`。

|已读正文|阅读结论/本项目取舍|
|---|---|
|index、changelog、deprecated|2026-07-28为本轮规范基线；2025版不能混作同一wire；Roots/Sampling/Logging等弃用状态需单独标注|
|architecture/index、basic/index|无协议会话；请求携带版本/能力；业务句柄每次显式传入；宿主掌握会话/同意|
|basic/versioning|现代版本server/discover与逐请求版本；旧版initialize仅属于兼容路径，不能给现代版强加握手|
|basic/patterns/index、mrtr|服务端不主动发JSON-RPC请求；需要客户端输入以input_required返回；首版不依赖MRTR互动|
|basic/patterns/subscriptions|订阅是subscriptions/listen独立请求；未订阅不可推送；静态工具清单首版不启用listChanged|
|basic/patterns/cancellation、progress|stdio取消与HTTP断流语义不同；进度仅关联活跃请求且单调增加，不可在提交返回后继续推送该token|
|basic/transports/index、stdio、streamable-http|UTF-8/换行JSON-RPC、stdout纯协议、EOF及时退出；HTTP不是现有Runner内部端点|
|basic/authorization/index、authorization-server-discovery、client-registration、security-considerations|HTTP授权体系、资源受众、PKCE/issuer/发现/注册/令牌隔离；首版本机stdio不照搬OAuth，但不等于无本地访问控制|
|client/roots、sampling、elicitation|已阅读全文；Roots非沙箱，前两者已弃用，不新增；elicitation可选，不能以表单收集秘密或假定宿主支持|
|server/index、discover、tools|只声明实际支持能力；discover必须实现；输入/输出Schema、缓存提示、错误分层与业务去重必须独立设计|
|server/prompts、resources|已读但首版不声明；工具返回工件元数据不自动提供resources/read；需要可读资源时再实现相应能力和访问控制|
|server/utilities/caching、pagination|受约束结果含ttlMs/cacheScope，目录排序稳定；cursor不透明，空字符串仍可能是有效cursor；业务模式分页另有快照一致性要求|
|server/utilities/completion、logging|completion可选，首版不实现；协议Logging已弃用，采用stderr与项目log/jsonl|

## 3. 补充完整阅读

- [Tasks扩展概览](https://modelcontextprotocol.io/extensions/tasks/overview)及[扩展正式规范](https://github.com/modelcontextprotocol/ext-tasks/blob/b3d28aceaa6d49f5f92258e3d06b61ad6f111e84/specification/2026-07-28/tasks.md)，全文。后者SHA256 `5fc22b9b5ff248703927c69855f751a061c2d6170f4dc3923204452f859f91a5`。扩展官方提交`b3d28aceaa6d49f5f92258e3d06b61ad6f111e84`；不采纳draft。首次猜测的官网tasks/lifecycle.md返回404，随后按概览链接定位正式仓库，不把404内容当已读。
- [安全最佳实践](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)及[本地服务安全](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/local-server-security)，全文。目录允许列表是协作性防护，不是操作系统沙箱；同一进程/连接不是同一对话或同一授权者。
- [官方SDK目录](https://modelcontextprotocol.io/docs/2026-07-28/sdk)，全文；只确认官方Python SDK入口，尚未安装/验证其具体版本或宿主兼容性。
- [2025-11-25生命周期](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)，全文用于版本对照；**未通读该旧版其他全部章节，因此不承诺完整旧版兼容**。

## 4. 对现有计划的实质修正

1. 旧计划以2025-06-18三篇规范及COMSOL代码作主要依据，覆盖不足；改为本记录的完整日期版本正文/类型。M0新增协议适用性矩阵与SDK/宿主版本门禁，未通过前不进入实现。
2. 现代版删除initialize/initialized，增加必需server/discover；每次请求必需protocolVersion/clientCapabilities元数据。结果必需resultType；不能把complete译为CST完成。旧宿主若需要initialize，应由已验证的官方SDK兼容模式另测，禁止把两版wire手工拼接。
3. 显式project_id/run_id/request_id/control_handle；不能因MCP进程固定就把其控制权隐式共享给所有交错对话。持久Runner client_id由控制句柄映射，与自报clientInfo/serverInfo不同，后两者不提供认证证明。
4. 固定工具清单、确定顺序，提供tools能力；discover/tools-list结果按2026版含非负ttlMs和cacheScope。首版保守private，避免把工程路径或授权后目录公开缓存。
5. 成功/工具执行失败用CallToolResult，业务DTO放structuredContent，content提供一致文本。协议错误保持JSON-RPC error；不得将所有异常套成ok=false，也不得把所有业务失败当JSON-RPC -32603。
6. 业务请求重试复用request_id；协议重试使用新的JSON-RPC id。无Tasks扩展时submit_run快速返回受理结果，run_id只是业务句柄，不是taskId，也不伪造resultType=task。
7. Tasks是可选扩展，2026版不采用旧tasks/result/tasks/list；未来启用须同时声明扩展、持久创建后返回、逐次鉴权、按pollIntervalMs观察。task completed可包含工具isError=true；task failed专指JSON-RPC失败，不能直接映射CST FAILED。
8. 请求取消、业务stop_run和未来tasks/cancel分开。EOF应及时退出适配进程；Runner/CST必须独立，不以强杀CST完成MCP退出。MCP请求超时有界，与正常求解无固定总时限不冲突。
9. 进度必须来自活跃请求token且严格增长；CST阶段重置/进度回退放业务状态字段，不直接转协议progress。提交返回后用get_run_status/events查询，不继续发送旧token或未协商通知。
10. 首版不声明resources/prompts/completions/logging/Tasks及动态listChanged，不代表规范不支持这些功能。非实现能力的RPC返回对应method-not-found，不编造空成功。

## 5. 规范文本中的待核实差异

通读发现官网概览仍出现“extensions negotiated during initialization”的旧措辞，与逐请求versioning正文不同；subscriptions说明推荐完成响应后关闭，而cancellation正文又要求服务端拆订阅时发送cancelled。TypeScript的error-range说明也与basic/index对旧范围新分配的限制措辞不完全一致。

这是**来源文本差异记录**，不是本项目已解决的规范争议。结构字段按固定TypeScript定义；具体行为按适用版本的详细规范核对，保留疑问并在SDK/官方上游确认，不能凭示例或自选一条宣称全面符合。首版不新增自定义JSON-RPC错误数值、不声明动态订阅，可避开这些非必要争议；实现核心版本/字段要求仍必须满足。

## 6. 验证边界

下载、哈希、JSON Schema解析、本地文档索引只证明来源可复核及文档结构；不证明SDK/宿主运行符合、网络授权正确或真实CST成功。M0至M5仍未实施。本记录不会自动授权安装软件、写宿主配置、启动求解或推送。
