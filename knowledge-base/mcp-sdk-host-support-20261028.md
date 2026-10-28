# MCP官方SDK与Codex宿主支持核查

日期：2026-10-28。只读官方文档/固定提交源码/本机版本与限定配置字段；未安装包、修改配置、注册MCP、运行测试服务或启动CST。目标宿主按当前Codex桌面使用场景选择；CLI可执行文件身份已核实，但没有把CLI版本等同于当前桌面会话内嵌运行时身份。

## 1. 结论分层

|对象|已确认|尚未证明|
|---|---|---|
|官方Python SDK|稳定发布mcp 2.3.0；固定tag包含现代server/discover、逐请求meta、resultType/cache类型和MCPServer入口|本项目尚未安装；实际注册Schema、stdio取消/退出与宿主握手未验|
|官方Codex源码|与本机CLI版本同名tag提供2026-07-28模式；stdio需feature与服务环境标记同时满足|当前桌面会话实际启用、真实工具目录/调用/取消报文未验|
|本机|codex-cli 0.165.0-alpha.1.2；Python3.12.7；无mcp安装；用户config相关features/服务协议选择为空|managed配置、启动参数或远端会话有效配置可能另有覆盖，不能据用户文件为空断言会话关闭或开启|

所以SDK和宿主源码能力已有证据，联调门禁仍pending。继续以2026-07-28为目标，不降级旧协议；后续用无CST的小型符合性服务验证，再实施真实业务服务。

## 2. 官方SDK固定依据

- [稳定发布v2.3.0](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.3.0)，发布时间2026-10-02T22:02:27Z，tag解析为`2118f14f8a19bc158d8a1cf90af58d85d187f849`。
- [固定pyproject](https://github.com/modelcontextprotocol/python-sdk/blob/2118f14f8a19bc158d8a1cf90af58d85d187f849/pyproject.toml)：requires-python>=3.10；mcp-types同版本，pydantic>=2.12.0，httpx2>=2.10.0等。只读PyPI元数据版本2.3.0及requires_python>=3.10相符。
- [固定低层Server](https://github.com/modelcontextprotocol/python-sdk/blob/2118f14f8a19bc158d8a1cf90af58d85d187f849/src/mcp/server/lowlevel/server.py)：默认注册server/discover及现代能力输出。
- [固定MCPServer](https://github.com/modelcontextprotocol/python-sdk/blob/2118f14f8a19bc158d8a1cf90af58d85d187f849/src/mcp/server/mcpserver/server.py)：高层装配、middleware、schema注册；不再照搬旧FastMCP导入。
- [固定类型](https://github.com/modelcontextprotocol/python-sdk/blob/2118f14f8a19bc158d8a1cf90af58d85d187f849/src/mcp-types/mcp_types/_types.py)：现代保留meta、result_type及cache字段；SDK包含多个协议时代的类型，模型默认值不能代替实际wire格式验收。
- [协议版本说明](https://py.sdk.modelcontextprotocol.io/protocol-versions/)与[2.x变化](https://py.sdk.modelcontextprotocol.io/whats-new/)明确现代请求无initialize，默认Client会探测/可能回退；指定现代mode不是发现验证，不能只打印protocol_version就证明对端支持。

版本选择冻结：首轮实施候选精确固定mcp==2.3.0，使用Python3.12环境，普通业务层不导入SDK；不是无限mcp>=2。官网概览当前写Python3.11+，与2.3.0固定包元数据>=3.10不一致，记录差异而不擅自裁定；选择3.12避开该下界冲突。实际依赖锁定和解压安装仍待实施验收，当前pyproject不变。

SDK本身默认同时服务旧版与现代版，不等于本项目要兼容旧版。项目层拟使用SDK支持的middleware/能力策略限制业务请求只接收现代版本；旧initialize和缺失现代meta须按标准错误拒绝，不能手写第二个JSON-RPC解析器。具体SDK拦截点/错误报文在无CST符合性测试中固定，未完成前不得声称服务已是modern-only。

首版使用MCPServer，关闭subscriptions、无Resources/Prompts/Tasks/旧roots/sampling/logging能力；构造参数、自动目录能力和cache提示须逐项检查真实输出，不能以“没有注册函数”推断discover未声明能力。2.3.0发布记录确有subscriptions=False选项，其余限制需要基于实际输出做精确配置。

## 3. 目标宿主固定源码与开关

本机命令解析到`C:\Users\ykk48\AppData\Local\OpenAI\Codex\bin\08d187884f2330d1\codex.exe`，`--version`返回0.165.0-alpha.1.2（附带arg0临时目录权限警告，未为此放宽权限）。官方同名tag `rust-v0.165.0-alpha.1.2`解析为`720fec862a608ae1e5878d1eecb04fb93192e93c`；tag与版本相符不构成二进制可复现构建证明。

核查三个实际文件：

- [features定义](https://github.com/openai/codex/blob/720fec862a608ae1e5878d1eecb04fb93192e93c/codex-rs/features/src/lib.rs)：mcp_2026_07_28为UnderDevelopment且默认false；codex_apps_mcp_2026_07_28是另一个host-owned Apps开关，不能代替普通外部服务开关。
- [McpProtocolMode::stdio_mode](https://github.com/openai/codex/blob/720fec862a608ae1e5878d1eecb04fb93192e93c/codex-rs/rmcp-client/src/protocol_mode.rs)：默认Legacy；现代feature模式仍需所选服务`CODEX_MCP_PROTOCOL_VERSION=2026-07-28`，否则stdio继续Legacy。未知版本标记拒绝。现代生命周期内部有legacy fallback能力，本项目服务不实现对应旧路径。
- [实际stdio创建](https://github.com/openai/codex/blob/720fec862a608ae1e5878d1eecb04fb93192e93c/codex-rs/rmcp-client/src/rmcp_client.rs)：创建前从服务env取出并移除CODEX_MCP_PROTOCOL_VERSION，再调用stdio_mode；该变量是宿主消费的选择标记，不保证传给子进程，服务端不能靠读取它证明协议版本。协议应核对实际每请求meta。
- [上层连接与观测](https://github.com/openai/codex/blob/720fec862a608ae1e5878d1eecb04fb93192e93c/codex-rs/codex-mcp/src/rmcp_client.rs)：连接接收protocol_mode并记录实际result.protocol_version；只有实际结果才能区分modern/legacy，不凭工具出现在目录就宣称现代握手。

本机用户config只提取相关features及协议选项，未复制令牌/完整配置；相关显式条目为空。尚无本项目MCP服务配置，当前会话不能通过这一检查宣称完成现代连接。

后续授权联调时配置草案（本轮未写入用户配置）：

```toml
[features]
mcp_2026_07_28 = true

[mcp_servers.cst_tools]
command = "<Python3.12绝对路径>"
args = ["-m", "csttool.mcp_server", "--project", "<已授权项目路径>"]

[mcp_servers.cst_tools.env]
CODEX_MCP_PROTOCOL_VERSION = "2026-07-28"
```

参数和模块尚未实现；这是目标配置说明，不是可直接运行的交付。正式启动器还需明确工作目录、环境与日志，避免占用发布目录。修改feature涉及重建宿主会话，不能假定当前对话立即生效。

官方当前通用[MCP连接文档](https://learn.chatgpt.com/docs/extend/mcp)证明stdio/HTTP及配置支持，但未给该日期版本支持表，且仍叙述initialize；日期版本结论来自上述固定官方源码。该文档不是现代wire行为的替代证据。

同时核对官方main `bea47c06dfac12ecce362090418e12a6faeedbf9`时发现新增DiscoverLocalStdio路径；**不能**拿main的自动发现行为解释本机alpha tag，两者在无版本标记时的分支不同。最终宿主设计以实际部署版本为准。

## 4. 无CST联调门禁设计

1. 先固定实际桌面宿主/内嵌CLI版本、有效feature和服务配置；不把另一个终端CLI或其他机器的通过算当前宿主通过。
2. 用官方SDK 2.3.0构建无CST只读测试服务，捕获脱敏报文：server/discover、逐请求协议meta/capabilities、tools/list、tools/call、structuredContent/resultType及cache；校验固定官方Schema。
3. 注入缺meta、旧initialize、错版本、非法Schema/业务错误、协议取消/EOF；检查modern-only拒绝、stdout仅协议、退出无资源占用，且没有启动Runner/CST。
4. 再接入统一业务契约与假Worker，验证跨GUI/CLI/MCP唯一命令及结果采用；真实CST是后续独立门禁。

这些用例本轮未运行。官方仓库已有符合性测试脚本，只读查看不代表本机执行通过；可复用其方法和官方SDK，不自造兼容框架。

## 5. 证据与抓取限制

轻量源快照/版本元数据/哈希在`artifacts/mcp-sdk-host-static-20261028/`，包括retrieval.json、summary.json和本地源码哈希。此目录约数MiB，不含模型/场，不保证随Git迁移；关键固定提交及结论已在本文保存。404的猜测路径（src/mcp/types.py、旧features.rs等）被记录为失败，随后通过实际tree定位；不能把404文件算已读。官方Markdown页面web抓取失败后改读实际HTML/固定源码；未改任何上游内容。
