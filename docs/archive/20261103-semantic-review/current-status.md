> 历史快照：2026-11-03语义复审前原文，基线2705935。仅重定位相对链接，旧“当前/下一步/测试通过”不代表现行状态。原始字节SHA256：`ab7436db6d5b63e08acb4c668b2fd9a92fd1b791cd8f3cdf6181f76eb43bdeb8`。现行入口：[current-status.md](../../current-status.md)。

# CST Tools 当前状态

更新：2026-11-03。本文为现行进度入口；实现查[功能索引](../../feature-index.md)，执行顺序查[TODO](../../minimal-python-vba-todo.md)。旧阶段结论完整保存在[历史归档](../20261102-progress-consolidation/README.md)，不再与现行状态交错。

## 当前结论

GUI/CLI、Runner、Manager与Managed Worker构成现有批量/HOM链。公共single-simulation已复用同一底层，完成定义引用、原生采集、RunStore绑定、ACK核对、结果采用/查询和证据齐全时的恢复补写；没有另建求解队列。旧Worker和队列式Manager入口已删除。

生产G03后端默认注册，登记不启动CST；显式验证在副本完成保存、正常退出、重开及持久设置/表达式和可可靠读回原生值核验。重新验证先撤销旧ready；退出未确认阻止后续单次提交。G03验证会话现已纳入项目生命周期、退出核验和有界恢复，GUI能展示其事实；真实中断矩阵及公开验证操作仍待完成。

G03与G04公共单次链已完成一次真实CST 2022.5小网格Pillbox串行副本验收；**完整MCP首阶段尚未通过**。真实宿主基本调用已验；类型化建模/定义发布与SDK真实链已补；指定桌面整链、跨入口完整迁移及故障扩展仍待完成。

## 能力与证据边界

|范围|当前实现/验收|仍未覆盖|
|---|---|---|
|B1 保存来源|共用cst_version只读内核，scope、编码、CRC/预算/hash校验|任意旧编码、所有历史工程和跨版本矩阵|
|B2 历史投影|51项A1允许表，同scope单位/solver锚点，保留表达式和Decimal精度|任意VBA解释、未知旧模板，不宽松放行|
|B3/B4 原生执行|nonce、attempt/revision及DB双hash绑定；旧库拒绝；正常/失败采集副本证据|数据库不能作为当前live设置；非本轮故障矩阵不能追认|
|G03 持久设置|生产后端及真实保存重开通过|完整Rebuild/故障矩阵、验证会话真实中断矩阵、GUI验证入口|
|G04 公共单次|一次Start、1模式、ACK/采集/采用、标准关闭通过|完整HTTP真实求解/宿主闭环及失败恢复扩展|
|HOM/批量|Managed执行、窄窗扫描、检查点和恢复；保留已有验收记录|新加密/扩窗恢复链等尚有真实验收待办|
|MCP|官方SDK现代stdio子集及当前桌面基本发现/调用已验|完整协议矩阵、公开建模完整流程仍待验|

## 最新验收

- [G03/G04真实记录](../../single-simulation-g04-acceptance.md)：R=L=100mm，500–2000MHz、Tet cell=4、nmodes=1；一次Solver.Start，1模式，1147.42692991921MHz，中心Z轴R/Q223.541439593232Ω；ACK、原生DB匹配、采用和标准关闭核对，无本轮遗留实例。验收工具创建工程不等于公开建模服务已验。
- [公共单次服务](../../single-simulation-service.md)：367项离线/假对端通过（79.689秒，single-acceptance-20261102.xml）。其后G03扩展回归109项；G04最终相关回归40项（25.41秒，g04-final-20261102.xml）。测试集合重叠且代码时点不同，不相加、不当作最新全仓回归。
- B4较早8会话/2求解及B2/B3离线数字保留在对应验收文档和归档，不能代替当前组合或所有分支验收。

报告通常位于artifacts，不保证随Git迁移；[G04轻量JSON](../../../knowledge-base/single-simulation-g04-evidence-20261102.json)可随Git保存。已清理本轮原始场、网格和pytest副本，保留.cst、宏、日志、DB归档和JSON；需要完整场时重算。

## 执行及安全原则

批量/HOM链：Runner → 应用后端/算法 → CSTManager → Managed Worker → 原子Task → 已加载3D Model.run → Completion → 接收/ACK → 检查点/采用 → 收尾回执及进程核验。

公共单次链：ApplicationService冻结定义 → 显式G03 → Runner单次分发 → 同一Managed Worker/原生采集 → RunStore核验 → 发布或证据对账补写。恢复不重复求解同run，不用缺少回执推断未计算。

GUI关闭、任务停止、Runner退出与CST正常关闭是不同事实；A01–A08已有实现和故障测试，见[恢复退出](../../recovery-exit-audit-implementation.md)。未知会话保留恢复状态，不强杀替代正常关闭。正常求解无固定总超时；启动、通信和退出有界。HOM默认窄窗nmodes=1；CST 2022大版本按用户指定共用行为规则，精确安装身份仍留档，实际实测不扩大到所有版本。

参数表达式必须保留；结构/设置需要重建后有效时进入历史。VBA继续承担复杂运行时后处理，结果按能力优先原生/Python读取；外部Q未配置时缺失不自动视为求解失败。

## 入口与历史

- [文档导航](../../README.md)、[功能索引](../../feature-index.md)、[公共服务](../../single-simulation-service.md)、[G01–G08门禁](../../mcp-first-stage-conversational-gate.md)。
- [设置验证器](../../cst-settings-verifier-design.md)、[执行采集](../../native-execution-capture.md)、[运行协议](../../minimal-python-vba-protocol.md)。
- [整理前状态与旧验收记录](../20261102-progress-consolidation/current-status.md)：保留原日期、结论与限制，不能把旧“下一步”当现行工作。

## G01–G08推进补充（2026-11-02）

见[逐门禁状态](../../g01-g08-progress.md)：G03生命周期/恢复接线及离线故障通过；真实采用后发布失败补写通过（一次Start，不重复采用）；JSON/CSV导出实际结果可用。可选mcp==2.3.0薄适配器已过现代SDK/stdio测试，本机Codex验收服务补齐现代协议feature/env后，当前桌面已实际发现并调用，G01基本链通过，完整协议矩阵仍待验。G02类型化定义事务已补；指定桌面整链及扩展故障矩阵仍未完成。

## 当前桌面G01与G02空工程子集

补齐宿主现代协议feature/env后，当前Codex实际加载并调用五工具，连接/状态/claim/shutdown通过、验收Runner退出，G01基本链已有真实证据。完整协议矩阵另验。G02已新增公共空工程创建/检查、Runner异步定义槽、不可变文档与发布缺口补写，官方安装自带Python bootstrap真实通过；新版九工具空工程创建/检查已在当前Codex对话实测通过；typed建模/配置/G03发布、关闭及导出已实现，仍缺真实建模整链和新增五工具桌面调用。见[创建服务](../../project-creation-service.md)及[门禁记录](../../g01-g08-progress.md)。

## 本批类型化定义推进

[类型化服务](../../typed-definition-service.md)已接入同一个ApplicationService/Runner槽及生产G03：草稿apply/configure不打开CST，显式save在专用新3D候选构造并保存重开验证后发布；旧定义/结果不覆盖。当前源码14工具，当前Codex已加载9工具。结果v2冻结积分/能量/算法及实际宏来源，Runner导出命令支持同ID重放。定义记录升级v2把PPS纳入revision；旧v1定义不自动升级ready，须从源显式重新登记验证。

[当前桌面G02空工程证据](../../../knowledge-base/mcp-codex-g02-public-20261102.json)：创建/检查/重放及Runner退出通过，0次求解。新的SDK真实整链在DesignEnvironment.new阶段超时，未建模/求解；该原身份后来退出并据事实退役，见[现场记录](../../../knowledge-base/cst-native-bootstrap-startup-20261102.md)。完整G01–G08尚未通过。

## 最新收口（2026-11-03）

**公开现代SDK+真实CST纵向链已验；指定Codex桌面完整门禁尚未通过，用户选择稍后验收。** [本次记录](../../typed-public-acceptance-20261103.md)：新建/参数化建模、固定Tet配置、G03保存重开、实际一次Start、中心Z后处理、采用缺口恢复、公开JSON/CSV及正常收尾。频率1147.42692991921MHz、R/Q223.541439593232Ω；恢复0次求解、采用日志不重复。原生几何/材质/体积/盒/六边界另已在两阶段核对；PEC背景保留历史重放证据等级。

154项相关回归、6项SDK/适配和最后41项定向复验分批通过；不汇总成全仓数字。旧超时候选保持abandoned-dead，当前物理pending=0，不将其伪造成标准退出。更广异常矩阵、XYZ实测、远程分布式和复杂CAD仍按各自门禁继续。

生成器还缺统一语法防线：B2/算术解释不是WWB编译证明，0+为已验局部修复；新增[W0–W3方案](../../winwrap-codegen-safety-plan.md)，先于继续扩充动态宏，尚未实施。

[同类源码调研](../../mcp-skill-codegen-practices.md)进一步收敛为固定模块/数据调用＋必要的小型发射器＋宿主门禁；不构建完整VBA编译器，不把Skill说明或Schema校验当作原生语法证明。

2026-11-03 补充[COMSOL MCP 源码对照](../../comsol-mcp-codegen-practices.md)：所查社区建模路径直接调用 Java 对象，减少程序拼接，但属性部分失败、取消与超时仍有边界；仅更新 W0–W3 设计依据，无 COMSOL/CST 新实测。

W0–W3方案已按COMSOL等源码分析修订为可执行分阶段计划：先冻结直接接口/历史边界和调用卡片，再迁移定义生成；明确候选全部成功才发布、身份先解析、求解不隐式重发及停止超时保留事实。阶段验收矩阵见[语法防线方案](../../winwrap-codegen-safety-plan.md)。仅设计更新，各实施项仍未完成。

### W0静态核查（2026-11-03）

[调用/持久化/诊断契约](../../winwrap-w0-contract.md)已核实随CST附带的WinWrap v9文档：存在脚本级MacroCheckThis/MacroCheck候选，不再将原生检查能力视为全无依据；但CST实际暴露、上下文和错误字段/弹框仍未校准。控件SyntaxCheck可能触发初始化，不作为无副作用保证。AddToHistory立即执行且同标题可能合并；参数/历史/结果持久化分别验证。W0静态完成，宿主部分待验，W1–W3未实施，本轮无CST启动或运行代码修改。

2026-11-03 后续：W0真实校准尚未启动，按用户提出的轻量检查方向先完成[开源选型调查](../../winwrap-open-source-checker-options.md)。ANTLR VB6为离线PoC优先候选；Rubberduck/VBA6许可与依赖不同，不直接引入。没有安装解析器、打包WinWrap二进制或获得新的原生编译证据。

### ANTLR离线PoC与本机v9入口（2026-11-03）

[15样本离线PoC](../../antlr-vb6-poc-20261103.md)完成：一般错误可拒绝，但原始Zrange反例、重名和未知CST成员仍接受；不接入生产依赖。SLL短样本可提速，完整历史回退LL。随后[静态类型库核查](../../winwrap-v9-installed-entry.md)找到BasicNoUIObj.Code/SyntaxCheck和ErrorLine等成员；未激活对象、未读许可内容、未启动CST。下一步优先校准文档化NoUI初始化及语法能力，再与CST上下文对照；W0原生执行、W1–W3仍待完成。

### NoUI独立校准（2026-11-03）

[实测记录](../../winwrap-noui-acceptance-20261103.md)：未启动CST，成功激活BasicNoUIObj并设置IgnoreDialogs；Initialize后仍False，用户观察到This eval copy is expired。SyntaxCheck/Zrange样本0次，不能标记原生语法通过。Shutdown=0、Disconnect=True、辅助进程退出0且无新增CST；临时本机二进制副本测试后删除。独立引擎路线等待有效初始化条件，W0原生语法及W1–W3仍待验；不把此结论扩展为CST自身授权过期。

2026-11-03 宿主路径复核：主程序导入/manifest静态检查未确认完整WinWrap初始化链；v9 Initialize不是许可路径接口。此前独立NoUI试的是开发示例token，不代表CST内部初始化失败。后续复用CST需由其宿主运行固定检查驱动，完全独立路线仍待支持接口核实，详见[核查](../../cst-winwrap-host-loading.md)。本轮未启动CST或重试初始化。

### W0核心宿主校准通过（2026-11-03）

[真实14样本](../../cst-macrocheck-w0-20261103.md)：通过批次一副本/一次RunScript/0求解。原始Zrange=10576拒绝，0+与Call语法通过，声明/块错误有ErrObject.Source行与语句。正文标记未出现、参数表达式未变，标准退出0、owned全部退出且无残留CST。首批包装错误已修复并保留旧证据。W0核心可进入W1；Call执行与持久化、数组/ByRef/行长扩展及W3仍待验；独立NoUI未初始化问题不变。

2026-11-03 [后台/headless核查](../../cst-background-headless-boundary.md)：Windows2022的-i/启动最小化与quiet均非全异常无窗口保证；W0 COM包装只隐藏辅助控制台，尚缺显式quiet与完整窗口观察。Python gui_linux是Linux限定。仅静态审计，未改代码或新增真实显示验收。

### 后台调用首批实施与真实验收（2026-11-03）

[验收](../../cst-background-acceptance-20261103.md)：类型化构造默认临时非活动桌面、显式拥有的COM服务器、归属后quiet再放行单次RunScript；公共空工程原生API也在绑定后设置/读回quiet。最终无求解副本14项正常/语法错误通过，用户CST前台事件0、窗口观察无错误/丢失，正常退出0且桌面句柄释放。普通COM曾测到抢焦点，旧失败保留；没有切换用户桌面、强杀或改系统注册。G03独立CLI/预处理/Managed仍原有最小化策略，不扩大全链保证。


## 2026-11-03 文档与定位工具 D1

[实施计划](../../project-documentation-tooling-plan.md)：旧索引136项已全部迁入[机器映射](../../project-map.json)，另加F138工具/迁移门禁，共137项；feature-index.md现由工具生成。旧ID、用途、全部链接标签/目标、符号顺序和纯文本验收说明以迁移前快照逐项对照。

D1功能迁移已完成；Schema、路径/符号和派生一致性纳入索引门禁。文档条目仅登记既有功能引用，未全面复审角色；domains/tools/relations为空，完整全图/工具副作用/动态关系登记仍待完成。D2查询工具专用验收、D3剩余导航维护整合、D4扩展故障测试待办；不据此宣称运行语义或真实CST通过。生产调用链未改变，未重新打包。

D1离线验收（2026-11-03）：`test/documentation_index_test.py` 与 `test/project_map_migration_test.py` 共7项通过，覆盖全136项保留、生成一致性、重复ID、遗漏功能、缺失文件/次级源码符号及hash过期提示；不是完整D2工具或真实CST验收。


### D2工具实现（2026-11-03）

已实现功能/路径/符号/字面问题查询、必读和验证候选、全范围文件清单、AST正反向候选、变更影响、删除预检及显式索引生成；UTF-8输出，解析/未知/缺失/截断均保留。测试覆盖只读、错误路径、动态回调、符号歧义、未登记VBA、源码包范围及暂存/删除/未跟踪变更。详情见[工具指南](../../project-map-guide.md)。D1/D2的职责登记仍不完整：完整文档角色、工具副作用清单及人工动态关系继续待办；D3剩余整合和D4扩展验收未完成。无生产执行链变更，无真实CST验收。

D2组合离线验收：2026-11-03，定位工具24项加迁移/索引7项，共31项通过（15.92秒）；与旧批次不相加，不作为全仓或真实CST验收。

D2最终性能修正后同组31项通过（19.87秒）。本仓库7类命令试运行均退出0：query、symbol query、graph、inventory、changes、delete、validate；当时范围1575文件，264有显式功能映射、1311未映射（包含第三方/资源/历史资料，不是功能缺失数）。符号全扫的2项解析问题被显式报告。模块解析改用单次文件清单，最终F138查询约2.80秒。计数/耗时仅对应本工作树与环境，不是固定性能承诺。


### D3登记与维护整合（2026-11-03，当前）

已补齐明确范围的66个工具入口/支持模块（含4个shell入口）、18条人工动态关系、14个目录责任类别及194篇Markdown角色条目。上方D1/D2“待登记”是当批历史状态，现由此记录更新。唯一登记来源project-map.json；未核文档角色和传递副作用保留unreviewed/unknown，不把完整清单当完整语义审计。

人工关系覆盖生产RunnerController与另一注入Qt路径、MCP/HTTP分发、执行器/editor/worker工厂、Manager线程池、ACK/收尾/采用、跨语言COM/WinEvent/logging资源和发布链。所有source/targets/consumers校验符号和路径，工具入口/字面参数/Markdown范围纳入结构门禁。导航、指南及AGENTS维护步骤已同步；不自动补关系、刷新hash或执行登记对象。

D3实现与静态登记完成，组合离线验收37项通过（65.72秒）；本仓库tools/query/graph/validate只读检查通过，66项工具清单无漏项/过期/解析问题，validate无错误及警告。D4仍需扩展目录重命名/过期章节/截断等故障矩阵及选定源码包的边界验收；逐篇文档语义审计、未核工具传递副作用和真实CST/宿主验收保持明确待办。没有改生产算法、utils或原工程，没有启动CST/发布/提交。


### D4扩展故障与源码包边界（2026-11-03，当前）

已增加目录重命名、过期/代码块伪章节、零截断、坏JSON/manifest/路径、内容ID/文件hash/已列文件缺失、解析后路径逃逸及包/仓库范围故障矩阵。修复清单信任与路径保护、重命名遗漏和章节误识别；源码包补齐离线文本夹具、base系列CLI、根知识库JSON。新增validate --scope package，严格核对包内字节/契约并显式报告省略项，不冒充全仓；默认validate保持全仓语义。

首轮真实ZIP/编译/无CST GUI烟雾通过后，包角色门禁发现生成README漏登；已新增package-only角色及“在包中必须存在”门禁，保留首轮失败。文档登记现在含194篇仓库Markdown及1项生成包README，共195项。D4组合验收60项通过（86.17秒），含21项扩展故障和2项源码包边界；ZIP/全文件hash、编译/Runner无Qt导入、无CST GUI烟雾及包内命令通过，完整仓库校验按预期拒绝部分包。原D3证据不追认。生产算法/协议未改，utils和原工程保持不变；不启动CST、不提交或推送。D1–D4完成范围仍是机械契约/定位工具；逐篇语义复审、工具传递副作用和真实宿主验收另列长期边界。

D4本批完成；[轻量证据](../../../knowledge-base/project-tooling-d4-20261103.json)及artifacts/d4-tooling-evidence保留初次失败、最终receipt/manifest/JUnit。测试ZIP、解压和pytest临时目录在结束后清理；原始包需重建，不承诺随Git迁移。验收包为报告前源码快照，非正式发布包。
