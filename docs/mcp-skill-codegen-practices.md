# 成熟MCP与Skill的执行、生成和校验实践

调研日期：2026-11-03。读取维护方源码及Skill原文，固定[commit/blob清单](../knowledge-base/mcp-skill-practice-sources-20261103.json)。没有安装或运行第三方项目；以下是源码观察，不是其全面可靠性/安全性认证。外部Skill内容仅作研究材料，不作为本项目操作授权。

## 1. Microsoft Playwright：直接执行与代码生成分开

在所查backend中，坐标点击工具以Zod定义坐标/按钮等参数，实际执行`page.mouse.click`；同时生成展示代码，并不是把展示代码再执行一次。需输出不同语言时复用Playwright的语言生成器。[mouse.ts](https://github.com/microsoft/playwright/blob/6117130d63434286287a50c6ea8d32050a818b36/packages/playwright-core/src/tools/backend/mouse.ts#L110-L140)、[codegen.ts](https://github.com/microsoft/playwright/blob/6117130d63434286287a50c6ea8d32050a818b36/packages/playwright-core/src/tools/backend/codegen.ts#L17-L47)。

它也提供run-code通道：先把用户函数单独交给Node VM编译/求值，之后由固定包装调用，避免把函数文本拼进另一段模板导致反引号转义问题；异常和异步拒绝用于结束等待。源码明确把这个工具描述为任意代码执行，不将VM上下文称为安全保证。[runCode.ts](https://github.com/microsoft/playwright/blob/6117130d63434286287a50c6ea8d32050a818b36/packages/playwright-core/src/tools/backend/runCode.ts#L32-L94)。

**本项目可用的做法**：模型操作首先是类型化业务调用；有可靠官方直接接口就使用，必须生成历史代码时才走共享发射器。诊断用代码与需要执行的程序分别标记，不能因生成了“看起来正确”的代码就当实际操作成功。Playwright已有成熟运行库和语言生成器，CST不能据此假设存在等价WinWrap工具。

本次同时读了playwright-mcp包装仓的package.json；它固定的Playwright alpha依赖与上面backend main源码不是同一个构建快照。因此这里只比较源码模式，不宣称某个已安装MCP版本必然包含这些最新实现。

## 2. MCP Filesystem参考服务器：参数校验后调用实现

官方参考服务器的write_file定义输入Schema，先核对允许目录，再调用writeFileContent；后者使用实际文件操作，而不是生成并执行一段shell。路径/符号链接等边界由可测试的实现处理。[server.ts](https://github.com/modelcontextprotocol/servers/blob/194cc86e3ae6400958555bd4116849d822d69263/src/filesystem/server.ts#L434-L459)、[lib.ts](https://github.com/modelcontextprotocol/servers/blob/194cc86e3ae6400958555bd4116849d822d69263/src/filesystem/lib.ts#L563-L578)。

**本项目可用的做法**：普通任务参数应是数据，路径与权限是工具端规则；不要为一次设置重复生成完整程序。Schema只约束其声明的字段：若字段本身是代码字符串，它不能自动证明字符串里的程序合法。

## 3. Blender MCP：允许代码，但使用Python解析和诊断

社区项目ahujasid/mcp-for-blender不是Blender官方服务器。所查版本提供代码执行：addon把代码交给Python exec，捕获stdout；异常回传类型、消息与完整traceback，便于定位提交代码的行。[addon.py](https://github.com/ahujasid/mcp-for-blender/blob/992233bb258975a05eec8b5691465c50c2831e34/addon.py#L2323-L2349)。

其可选safe mode使用ast.parse、大小/深度预算及允许表，SyntaxError转为带行号的拒绝。源码明确它默认未开启，且只保护MCP路径，不包围addon socket，也不是Blender安全沙箱。[safe_mode.py](https://github.com/ahujasid/mcp-for-blender/blob/992233bb258975a05eec8b5691465c50c2831e34/src/blender_mcp/safe_mode.py#L1-L21)、[解析及校验](https://github.com/ahujasid/mcp-for-blender/blob/992233bb258975a05eec8b5691465c50c2831e34/src/blender_mcp/safe_mode.py#L894-L946)。

它还提供API/属性/类型查询辅助，源码说明这是为了减少猜测接口后靠失败尝试发现属性。[introspection说明](https://github.com/ahujasid/mcp-for-blender/blob/992233bb258975a05eec8b5691465c50c2831e34/addon.py#L2351-L2359)。

**本项目可用的做法**：优先返回可查询的调用签名、适用scope和错误位置。不能把Python AST换成Python解析VBA；Python能使用自己的解析/执行引擎，而WinWrap原生编译接口仍须核实。exec捕获异常也不表示所有运行时修改可回滚，不能照搬为CST的事务或恢复保证。

## 4. Anthropic DOCX Skill：说明、辅助脚本与产物验证分层

Skill提供生成库使用方式和具体易错点，要求转换/渲染后查看结果；编辑已有文档时另调用Office校验脚本。该脚本针对DOCX/PPTX调用相应Schema validator，并可进行修订检查；不是通用的“所有Office文件均已验证”。[DOCX Skill](https://github.com/anthropics/skills/blob/ca45fc496a3436251f191354091d557da31c15b5/skills/docx/SKILL.md)、[validate.py](https://github.com/anthropics/skills/blob/ca45fc496a3436251f191354091d557da31c15b5/skills/docx/scripts/office/validate.py#L124-L161)。

**本项目可用的做法**：Skill记录CST版本、调用步骤、已知陷阱和验收命令；工具负责强制前提及验证，实际工程/结果再独立核对。SKILL.md里的要求本身不能使生成的代码通过编译。渲染成功也不自动等于内容正确，类比到CST就是保存成功不等于物理模型正确。

## 5. Anthropic mcp-builder Skill：Schema＋构建＋客户端测试

指南要求用Zod/Pydantic约束输入、定义结构化输出、共用基础设施；分别执行TypeScript构建或Python py_compile，再用客户端/Inspector检查MCP。其v2参考进一步给出真实启动服务器并调用成功/失败工具的self-check。[SKILL.md](https://github.com/anthropics/skills/blob/ca45fc496a3436251f191354091d557da31c15b5/skills/mcp-builder/SKILL.md#L96-L158)、[v2验证示例](https://github.com/anthropics/skills/blob/ca45fc496a3436251f191354091d557da31c15b5/skills/mcp-builder/reference/node_mcp_server_v2.md#L630-L690)。

**本项目可用的做法**：MCP服务器编译、MCP协议调用、生成的WinWrap宏、CST设置/结果是不同检查层。py_compile通过只能证明Python服务器这一层，不能证明内层历史；还需要宿主侧门禁。

## 对现有方案的收敛

1. 优先固定已验运行模块并传结构化数据，不为每次业务操作再生成程序；CST确实需要历史代码的地方保留小型共享发射器。
2. 不自研完整WinWrap编译器，也不引入通用VBA远程执行工具或新的一套任务语言。受限检查器只检查所承诺的生成规则，不能授予原生编译通过状态。
3. 生成器复用一个调用规范与字符串/声明/表达式辅助，不由不同业务函数分别处理括号和转义。
4. 给出CST调用卡片：真实签名、scope、参数/返回值、持久化与副作用、文档及版本校准来源。Skill按这些信息选择工具，不按方法名字猜测。
5. 由WinWrap/CST证明原生语法和内层历史，保留无求解副本门禁；错误分层并回传行/语句/输入映射，不能退化为人工点错误框的生产流程。

这是本项目的设计推论，不是上述项目共同承诺的实现保证。对应[W0–W3计划](winwrap-codegen-safety-plan.md)，本轮仅更新研究/设计文档，无运行代码变更。

## COMSOL MCP 补充

两项社区实现的直接 Java 对象调用、属性部分失败及异步求解边界，另见[COMSOL MCP 源码对照](comsol-mcp-codegen-practices.md)。它们支持减少源码拼接的方向，但不提供可直接移植的 WinWrap 编译保证或 CST 收尾协议。
