# 执行链后续五项实施

更新：2026-11-04，基线e94d5b7。此计划接续[15例真实故障批次](public-fault-injection.md)，不把旧验收追认为新代码全通过。源码与测试入口由project-map登记；本页区分实现、实际验收及未完成范围。

|项|实现与现有证据|验收边界|
|---|---|---|
|1 生产Runner求解中退出|既有真实runner-solver探针完成：第二次求解中只结束本轮Python Runner，重启、显式恢复、续跑；两任务合计两次Start，第一结果/场hash不变|旧父进程退出后不能编造原CST退出码；新增独立桌面链e8e89f33复验通过，两任务两次Start、源/首项hash不变；父进程死亡后的原退出码仍未知|
|2 Start=0/Start自身异常|核对VBA及完整Python帮助，验证精确PID/路径连接后Modeler.abort_solver返回True；宏实际Start仍返回1且无结果|正常中止也未触发这两分支，仍无可靠强制方法；Err.Raise/改返回值不是实测，迭代耗尽/无结果也不自动等同它们|
|3 N01–N25扩展|stdio入口使用官方SDK的显式输入流和消息模型，补前置JSON/ID/现代元数据与在途ID保护；新增原始消息测试|只覆盖首版stdio子集；HTTP/OAuth/Tasks未启用，不能整体宣告N01–N25通过|
|4 HOM实际密度与恢复|新增小网格探针：实际网格4→6→4、真实求解拒绝、扩窗首模、窄窗确认，以及持久检查点阶段中断/重载|实际634→2140→634、扩窗/窄窗确认与四次检查点重载已完成；尾窗一次正常中止后恢复完成；测试几何约束去混杂不是生产默认修改，也不是物理收敛证明|
|5 共用批调用与生成保护|G03、预处理、Managed/HOM复用BatchDesktopLease；背景调用独立桌面、正向归属窗口观察；路径字符串复用typed emitter，写来源hash和行预算清单|没有伪造batch中的quiet全局调用；不等于所有异常无弹窗，生成保护也不是完整Basic编译器|

## 调用与错误边界

BatchDesktopLease只管理CreateProcessW、临时桌面和观察线程，复用既有PrivateDesktop/BackgroundWindowObserver/DesktopProcess；不产生新任务队列、求解后端或配置profile。后台默认隔离，显式前台走原可见调用；隔离失败拒绝启动，不回退用户桌面。正向归属来自PID+创建时间+安装路径及精确项目关联；不按裸PID操作窗口，不回答任何弹窗。

`finish`仅关闭本地观察/桌面句柄，不停止进程，不证明进程退出。Managed的StopAck/收尾回执/快照/原生身份核验保持独立；正常求解仍无固定总超时。Runner突然退出后本地句柄由OS处理，但CST仍需独立恢复和收尾，不根据desktop-lease.json的旧布尔值推断CST活跃/退出。

生成保护覆盖G03/预处理/Managed固定模板的字符串和物理行预算，generation-manifest.json保留最终文本hash及基础模板/生成器来源。动态测试覆写由对应工具源码及登记关系补充，不能声称这个清单是完整源码映射。控制字符在发射前拒绝；有效ASCII和中文编码与既有vb_codec保持一致。A1完整受限检查与源码校准门禁保持原范围。

## 协议扩展与规范依据

依据[JSON-RPC 2.0错误对象](https://www.jsonrpc.org/specification#error_object)及本仓固定的[MCP规范映射](mcp-protocol-conformance.md)。标准SDK继续负责消息类型、调用分发、结果序列化及EOF；本项目只在stdio边界补SDK归一化前的严格检查，不新增业务分发器或旧协议兼容层。

非法JSON/UTF-8和非有限JSON常量返回解析错误；非法请求形状/ID返回请求错误。空/布尔ID不能被SDK的宽松notification分支吞掉。缺版本、旧initialize和不支持版本在进入SDK era选择前拒绝，错误后仍可用正确现代请求继续。重复在途ID拒绝且不替换原处理；这是无效客户端的两条关联响应（重复项错误、原项后续结果），不是两次业务成功。活动请求取消后不再发送迟到响应；独立受理任务依然需要Runner stop，协议取消不等同停止CST。

本批源码核查发现SDK的两个具体边界：JSONRPCNotification模型丢弃非法id字段；无现代元数据的首请求会选择旧握手era。SDK dispatcher源码还保留重复入站ID覆盖的待办，因此前置保护不能只放在业务函数内。新增测试分别验证错误后的同连接恢复、原请求不被覆盖及零二次派发。

## 本批发现与校准要求

HOM预处理历史不自动属于公共A1允许集合：保持SETTING_UNVERIFIED，不靠放宽历史解释器让测试通过。G03使用已验证A1原模型，HOM使用独立预处理副本。

新增网格探针曾遗漏局部句柄声明，随后又错误引用预处理模块自己的ParameterExpression辅助函数。对照真实MacroCheckThis：已成功宏被接受，辅助函数反例被拒绝；正确RestoreParameterExpression版本被接受。被检查正文没有执行，实例正常关闭。不能因为名字相似就推定CST全局接口；新模板应先做这种无求解编译校准。初次失败的退出0/无ready仍判失败，不追认为成功。

原模型的StepsPerBoxNear=10导致几何步长20mm，小于2000MHz下4/6波长密度对应步长；实测参数4→6而网格均4284个单元。依已有V05方法，测试副本才将StepsPerBoxNear/Far设为2/1，分离验证波长密度；生产保留用户几何约束。密度恢复不承诺网格二进制完全一致，读回参数并独立比较实际网格。

本批轻量证据及最终统计完成后同步知识库；artifacts不保证随Git迁移。清理只针对已结束且路径核实的本轮副本和pytest目录，保留宏、日志、参数、网格输入及hash。

## 2026-11-04正常中止校准

完整安装帮助`Online Help/Python/source/cst.interface.html`记录`DesignEnvironment.connect(pid)`、`get_open_project(path)`及`Modeler.abort_solver`。本轮按PID+创建时间及精确副本路径连接成功，abort返回True；不使用任意活动工程，也未连接其它实例。安装缺少wmic不代表当前connect必然失败，本轮实际连接成功。

尾窗网格初始化长时间无进展，经官方正常中止后，VBA Start返回1，模式读取失败；随后ACK清理、保存、close.receipt、stop.ack和batch-return均写入。该观察证明Start返回值不能独立充当结果成功证据，不证明Start=0或Start自身异常。没有新增生产自动中止/总超时逻辑。

## 本批已完成验收

`artifacts/hom-recovery-native-da01c6ed/report.json`已完成：before-mesh/before-probe/before-confirm/after-confirm四次落盘中断并重载，源和processed哈希不变，确认前恢复的首调用仍为confirm。尾窗最终覆盖至1150MHz，实际计算上界1786.43526518917MHz。驱动正常结束，无本轮CST残留，清理40个伴随目录，保留轻量证据。

该报告的passed是恢复驱动断言通过，并非模式身份认证：1147.5612、1147.7017、1147.7590MHz均进入结果；小网格频率漂移/同模重算不能仅靠频率证明互异。后续需结合场匹配和收敛标准独立验收，不调大容差来美化本轮结果。尾窗官方中止是额外人工注入时点，保留独立intent/result及生命周期，不宣称全自动故障时序。

离线：固定SDK环境22项stdio/SDK测试通过；普通环境核心48项通过、两SDK模块跳过（另行已验）。这些集合和旧80/59项有重叠，不相加。

功能索引的D1冻结内容继续按原顺序/原链接/原符号保留，后续允许增加来源、测试和文档。迁移测试改为有序保留检查，并用缺失/重排反例防止放宽成仅数量检查；没有重写冻结夹具或忽略旧信息。

轻量原始报告、检查点、正常中止事实和生产Runner新链复验已归入[知识记录](../knowledge-base/execution-hardening-five-steps-20261104.json)。

最终登记/源码包边界63项通过；G03/启动/窗口/文档语义26项通过、1项可选跳过。修正中间发现的派生索引陈旧、未限定类方法符号及迁移测试禁止新增信息的问题后重跑通过；早期失败XML保留，不混作最终结果。大副本除本轮HOM已清理40个外，额外清理29个伴随目录；原始场/网格需重生成。
