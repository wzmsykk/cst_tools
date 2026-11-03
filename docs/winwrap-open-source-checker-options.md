# WinWrap轻量语法门禁：开源候选

> 适用性复审（2026-11-03）：按原日期/样本/固定来源保留的研究，不是通用格式规范、现行运行合同或新实测。现行实现见[当前状态](current-status.md)、[功能索引](feature-index.md)及对应API；不重算或追认旧证据。

2026-11-03。静态源码与官方资料检索；未安装解析器、未复制CST二进制、未启动CST。本次检索未找到经确认兼容WinWrap v9的开源编译器；这不是不存在任何实现的证明。候选是相近语言的解析器，不是CST原生语言引擎。

## 候选对照

|候选|核实的实现与许可证边界|适用判断|
|---|---|---|
|ANTLR grammars-v4 / vb6|固定commit `b96e04db9d54bb313e542cc3e6ee913900a21520`，独立lexer/parser；VisualBasic6Parser.g4头部标明MIT；仍需逐个核对lexer、生成产物及runtime许可|优先做小规模离线PoC；可生成Python解析器，不必把完整IDE引入项目。ANTLR生成步骤和测试运行依赖分别组织，具体Python目标可用性仍需实测|
|同仓 / vba/vba6|vba.g4头部明确GPLv3-or-later，自述近似grammar及预处理限制|不能因为与VB6同仓就当MIT；暂不直接引入|
|Rubberduck|固定commit `fae50adab188126a5e7d2a1cefc3328cc18af482`，VBAParser.g4标GPLv3-or-later，并依赖VBABaseParser/VBABaseParserRuleContext；整体解析流程还包含预处理、声明和引用解析|适合参考调用/声明诊断设计；移植不等于复制一个g4文件，当前不引入完整VBE插件栈|
|同仓 / vba/vba7_1|基于MS-VBAL7.1；README说明不处理条件编译，需另用vba_cc；parser要求Attribute VB_Name模块头|可作为第二候选；语言代际不同，需包装/行号映射且许可证尚未逐文件确认，不因文件未写license就推定可自由分发|
|ViperMonkey|固定commit `73547cef7f82dbcb10e22e36b84b558a07f7d21d`；面向恶意宏分析的Python解析/仿真引擎；README仍要求Python2.7并提示性能限制|用途和依赖不适合当前现代Python轻量语法门禁，不引入仿真执行能力|

固定源码：[ANTLR VB6 parser](https://github.com/antlr/grammars-v4/blob/b96e04db9d54bb313e542cc3e6ee913900a21520/vb6/VisualBasic6Parser.g4)、[VBA6](https://github.com/antlr/grammars-v4/blob/b96e04db9d54bb313e542cc3e6ee913900a21520/vba/vba6/vba.g4)、[VBA7.1说明](https://github.com/antlr/grammars-v4/blob/b96e04db9d54bb313e542cc3e6ee913900a21520/vba/vba7_1/README.md)、[Rubberduck parser](https://github.com/rubberduck-vba/Rubberduck/blob/fae50adab188126a5e7d2a1cefc3328cc18af482/Rubberduck.Parsing/Grammar/VBAParser.g4)、[解析流程](https://github.com/rubberduck-vba/Rubberduck/wiki/The-Parsing-Process)、[ViperMonkey README](https://github.com/decalage2/ViperMonkey/blob/73547cef7f82dbcb10e22e36b84b558a07f7d21d/README.md)。不以项目名称、星数或README功能描述证明WinWrap兼容性。

## 为什么不能直接授予“编译通过”

VB6 grammar中的裸成员调用接受argsCall，argCall接受valueStmt，后者含括号表达式分支。静态读规则无法保证它会拒绝本项目实际失败的Zrange首实参样本；可能比WinWrap宽松，必须用原始反例验证。此处没有实际运行parser，不报告反例已被接受或拒绝。

无论采用哪一项，基础语法树均不能独立证明变量类型/重名、CST参数注入、COM ByRef、对象作用域、AddToHistory顶层语义、历史持久性或表达式求值。即使不做代码执行，也必须防止parser错误恢复后仍返回树被当作成功：PoC应收集lexer/parser错误、要求消费EOF，并拒绝未支持构造。

## 推荐的最小路径

1. 先以ANTLR VB6候选做隔离PoC，不加入生产依赖、不执行宏。逐文件确认许可证并固定grammar/runtime版本；生成Python目标的命令与版本留档。
2. 使用原始失败Zrange、0+已验版本、Call候选、缺引号/End With、中文/续行、数组/ByRef和工程参数重名等共同样本。分别报告通用parser、项目受限规则和CST原生结果，未知结果留空。
3. 原始反例若被通用parser接受，只补本项目已经有文档/实测依据的调用形态规则，不扩展为完整WinWrap编译器。检查结果称“离线语法预检”，不称原生编译通过。
4. 保留少量真实CST的MacroCheckThis校准与构造/重放门禁；只在生成器、模板、调用profile变化时运行相关宿主验收，不为每个HOM窗口重复启动CST。
5. 是否采用由启动/解析耗时、依赖体积、诊断准确性、误拒/漏报和维护差异决定；本轮无测量，暂不承诺性能数字。不新增MCP工具、任务语言或独立服务。

## 自带官方引擎的区别

本机CST安装含WB9ENT64.OCX与wwb9_64.dll，文件版本均为9.21.027。这只证明文件存在，不证明项目有独立使用/再分发权，也未证明这些组件能在本项目宿主中激活。未读取或复制许可内容，未注册OCX。

官方公开的[v10证书说明](https://www.winwrap.com/web2/license-certs)和[v10分发协议](https://www.winwrap.com/web2/asset/doc/all/distrib2022.pdf)表明官方引擎分发有专门授权要求；这些是v10资料，不能拿来直接裁定本机v9合同。若采用官方轻量宿主，须先明确目标版本、授权、CST扩展声明和与原宿主的一致性。默认方案不把CST安装中的OCX/DLL打进源码发布包。

当前原先请求的W0真实宿主校准尚未启动；按用户最新方向先完成开源选型调查。W0原生可用性/无正文执行/退出仍为待验；不会用本次检索结果勾选通过。

## PoC后续（2026-11-03）

[ANTLR实际PoC](antlr-vb6-poc-20261103.md)已完成：原始Zrange反例被接受，一般语法错误可诊断，SLL短样本快但完整历史回退LL。尚未纳入生产依赖。随后[本机v9类型库](winwrap-v9-installed-entry.md)找到了BasicNoUIObj.SyntaxCheck及诊断入口，优先核实轻量原生初始化和方言一致性；未创建对象或执行检查。
