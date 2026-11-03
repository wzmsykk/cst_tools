# CST Tools 当前状态

更新：2026-11-03；本页只保留现行结论。源码基线为2705935，本批已实施W0–W3的A1受限生成链，新增串行无求解副本验收。逐批原文及旧待办见[复审前快照](archive/20261103-semantic-review/current-status.md)和[更早归档](archive/20261102-progress-consolidation/README.md)。

## 已实现与实际证据

|范围|现行事实|验收边界|
|---|---|---|
|生产GUI/批量/HOM|GUI的RunnerController经Runner分发，后端使用CSTManager及ManagedCSTWorker；根base系列CLI仍直接调用应用后端|GUI关闭、Runner退出、原生会话关闭与任务采用分别核验；不可把所有CLI说成走MCP|
|保存来源与验证|共享cst_version只读来源；B2受限A1历史投影；G03保存重开、表达式/设置和可读回原生值核验|不解释任意VBA；未知编码、复杂历史、多材料/CAD及跨版本矩阵未全覆盖|
|公共类型化单次服务|同一ApplicationService/Runner槽支持create/apply/configure/save/close及单次计算；原生采集和RunStore绑定，采用缺口幂等补写|2026-11-03官方SDK/stdio真实Pillbox纵向链通过，2026-11-03指定Codex桌面Z向Pillbox正常闭环通过；全故障矩阵未完成|
|MCP|源码注册14工具，tools-only，严格Schema、控制句柄/租约及请求幂等|桌面9工具的发现/空工程调用是2026-11-02记录；本轮当前桌面对话发现14工具并完成正常纵向链；不替代N01–N25|
|HOM失败恢复|生产启用加密一次→原密度扩窗→窄窗确认；覆盖和结果采用独立；失败新Worker从processed基准启动|新恢复策略的真实网格生效、原密度恢复及故障矩阵仍待串行副本验收；不以迭代耗尽判空|
|W0–W3语法防线|A1保存已接共享发射、独立检查、源映射、源码版本门禁和会话内历史MacroCheckThis；W23最终23个编译样本及12个无求解会话通过，XYZ/G03/故障拒绝均验|仅Sub-only/首阶段定义构造；不是完整语言、全部宏/初始化/真实求解故障证明；NoUI仍未初始化，ANTLR不替代原生|
|后台窗口策略|公共空工程/类型化构造默认非活动桌面、归属后quiet与窗口观察；无求解正常/语法错误副本通过|G03独立CLI、预处理、Managed/HOM尚未迁为同一隔离策略；不能承诺全链headless或全部异常无弹窗|
|D1–D4开发工具|功能机器映射、生成索引、68项工具范围、21条人工动态关系、文档角色与包边界检查已实现|60项离线/源码包检查属于2026-11-03批次；机械覆盖不等于逐篇语义或真实调用图已证|

现行生成检查与发布门禁见[W23实施](winwrap-w23-implementation.md)；[W01记录](winwrap-w01-implementation.md)保留前阶段证据。新批次没有重算旧求解结果。W23组合271项通过、1项可选SDK跳过，源码包门禁可独立核验；实际XYZ/故障样本和边界见实施页。

## 已有验收入口

- [公开类型化真实链](typed-public-acceptance-20261103.md)：一次Solver.Start、1147.42692991921MHz、中心Z轴R/Q223.541439593232Ω；采用恢复不重复求解。不是XYZ、场型/收敛或指定桌面全门禁证明。
- [Codex桌面完整链](codex-desktop-acceptance-20261103.md)：本轮新建至结果导出和正常退出；一次Start，5个原生会话标准关闭。
- [G01–G08](g01-g08-progress.md)：门禁状态与剩余矩阵；[后台无求解验收](cst-background-acceptance-20261103.md)和[W0](cst-macrocheck-w0-20261103.md)是独立证据层。
- [D4轻量记录](../knowledge-base/project-tooling-d4-20261103.json)：60项通过，源码包编译/哈希/无CST GUI烟雾；临时ZIP和解压副本已删除，检查原包需重建。

历史测试集合重叠且代码时点不同，不相加、不自动用于本批代码。artifacts不保证随Git迁移；原始场/网格或包已清理时按各记录重新生成。本页不再用“当前无残留进程”描述旧现场状态。

## 执行与安全边界

批量/HOM：Runner→CstApplicationBackend/算法→CSTManager→Managed Worker→Task→已加载模型内VBA→Completion→持久接收/ACK→检查点/采用→独立收尾回执与进程核验。公共单次定义/执行使用ApplicationService，复用Managed和RunStore，不另建求解队列。

正常求解没有固定总超时；Managed启动及ACK就绪使用120秒边界，stop共享600秒预算。阻塞Solver期间不能承诺立即中断；原生进程身份未知或证据不齐保持恢复状态。失败新Worker从预处理基准启动；成功HOM任务的快照接力是显式能力，不跨槽借用。

保留表达式；需重建后仍生效的结构/设置进入历史。VBA仍承担复杂运行时后处理；未配置外部Q时对应量缺失不自动代表求解失败。CST2022按用户指定的大版本规则处理，精确安装身份仍留档，不把单机测试扩大到所有安装。

## 文档维护验收

2026-11-03现行专题静态语义复审已收口：226项文档登记，62项现行/设计/维护入口附具体依据，29份完整旧文归档；修正19类旧语义/堆叠问题，剩余22项专题已逐条对照。第二轮核心379项、GUI日志/工作台23项、登记及源码包8项通过；未运行CST。历史原测量/第三方规范不重新认证，证据和边界见[复审报告](documentation-semantic-review.md)。

## 维护入口

[TODO](minimal-python-vba-todo.md)、[功能索引](feature-index.md)、[文档导航](README.md)、[语义复审](documentation-semantic-review.md)。进度变化更新本页结论；逐批过程写验收文档/知识库，不继续追加相互覆盖的“当前”“下一步”。
