# Python/VBA生命周期协议：故障范围与修订计划

设计日期：2026-10-20；进度更新：2026-10-24。状态：**L1–L4源码已接入，L5部分真实验收**。Task/Completion/Ack/Stop仍v1，新Managed会话收尾为v2、旧会话不变；真实WinWrap四组及生产/七阶段故障范围见[L5记录](close-v2-l5-acceptance.md)，完整矩阵仍pending。正常saved改用固定.closed.cst Backup token，两端同步。退出0/有条件退出4规则不放宽，不接受退出1，不追认旧Gate。L4当前API见[事实与诊断](runner-lifecycle-l4.md)，以下旧阶段描述保留其历史边界。

2026-10-24进度：L1见[实施边界](session-closure-l1.md)，L2见[v2说明](close-receipt-v2.md)，L3新生产宏接入见[状态与退役](production-close-v2-l3.md)。第4节格式已冻结，第5–6节已部分落地，完整传播/真实故障矩阵仍待L4–L5。

## 1. 为什么扩大范围

原最小协议解决任务交接、结果所有权和原子发布；生产已增加长驻Worker、停止、恢复和独立Runner，生命周期必须纳入契约，而不能依赖日志文字或退出码补丁。只扩展这些有实际需要的边界，不建设通用RPC。

现场同一session 49ab9d3a的用户日志：17:17调用Solver，18:09 Start返回0，失败Completion随后ACK清理；18:11恢复表达式及Rebuild，18:12 Save返回并走到batch-return；Python记录退出码1。证明任务失败与VBA收尾路径均发生，不证明StopAck、恢复产物有效或最终批退出正常。诊断JSON本体尚未取得，不认定退出1由先前求解错误引起。

源码审计另确认：正常stop检查退出码，显式恢复主要检查StopAck及进程消失，两者门禁不一致；会话发现末尾的stopped标记/StopAck存在条件可能排除仍存活或未知进程。只读构造探针已复现后者，不是现场进程实验。

## 2. 范围与不变量

覆盖：启动/应用参数/重建/求解/后处理/Completion/接收与ACK/停止与回滚/保存/批返回/进程退出/控制器重启后的对账。Python负责结果采用及HOM覆盖；VBA负责工程内操作及其回执。

明确不做：远程传输、消息总线、动态插件、任意VBA执行、自动GUI点击、全工程事务回滚、无限重试、求解总时限或通用忽略非零退出码。服务器上其他用户/本用户独立CST实例不在停止范围。

- Task失败可以被接收和ACK；ACK只授权清理，不代表成功、不推进覆盖。
- Python先持久保存接收记录，再发ACK；VBA确认匹配ACK、写接收凭据、完成清理后，才能发布本任务关联的可接收状态。
- 任务状态、模型状态、进程状态、结果采用状态分别保存，不能用一个success或RECOVERY_REQUIRED替代全部事实。
- StopAck仅证明VBA走完已定义的停止处理，绝不证明进程已经退出。batch-return是宏返回意图，不是退出事件。
- 恢复不运行Solver；原参数表达式保留；失败工作副本不能提升为求解成功快照。
- HOM只从已持久确认覆盖恢复。失败/中止区间保持pending；最高已计算上界不替代连续确认前沿。
- 没有可靠模型状态或进程身份时不接新任务、不假定已死、不自动删除会话。

## 3. 四组事实，而非单一状态

|维度|最小事实|谁负责确认|
|---|---|---|
|任务执行|not-started / success / failure / cancelled / unknown，带task/session及失败阶段|VBA Completion；Python核对身份|
|模型状态|prepared / committed / dirty / restored-saved / restore-failed / unknown|VBA操作回执及Python产物校验；committed指本任务快照已形成，不代表被扫描器采用|
|进程安全|running / exited / unknown，带进程身份、原始退出码及分类|Python核验本任务主进程及已登记后代，不由VBA自证|
|结果接收/采用|unreceived / received / acknowledged / adopted；未完成可选分析另记|Python接收记录、ACK凭据和扫描检查点|

派生结果至少区分：干净关闭、恢复保存后关闭、已死但不可信并放弃工作副本、仍活动、未知。任务失败可以与恢复保存后关闭并存；“已死放弃”不是“标准关闭”，也不证明需UI处理的问题从未出现。

## 4. 生命周期消息最小修订（L2格式已实现，生产采集顺序待L3）

Task/Completion/Ack v1保持不变，不往每次任务塞入通用配置。停止请求仍以不可复用session识别、单session单次终止，重复请求幂等；不新增无必要的分布式request世代。

新增原子发布的 `close.receipt`，magic已冻结为 `CST_CLOSE_RECEIPT_V2`，沿用ASCII键/值双行，不要求VBA解析JSON。静态生成清单登记close_protocol=v2，Python与生成宏一起升级；这是静态契约选择，不是动态能力协商。L3已使新生产会话生成v2；旧会话仍按其声明读取，不能热切换。

|字段|含义和校验|
|---|---|
|session_id|匹配工作空间及停止请求；不可复用|
|last_task_id|最后任务UUID；启动即停止时显式none，不能借用其他任务|
|close_origin|stop-request或worker-failure；非法停止请求不能冒充合法停止|
|task_outcome|本次最后已知任务结果；不能替代原Completion|
|close_outcome|saved / restored-saved / failed；failed绝不发布正向StopAck|
|model_state|与第3节一致；dirty/unknown不可声明saved|
|last_completed_phase|可明确已完成的是restore/rebuild/backup/save/receipt，不能把开始阶段当完成|
|snapshot_ref / snapshot_bytes|工作空间内预定义相对路径和文件大小；无快照用none/0。不接受任务传入任意输出路径|
|error_code|成功none；失败使用稳定错误码，长描述/非ASCII消息留在生命周期日志|

成功回执发布顺序：必要的表达式恢复→Rebuild→隔离恢复快照→Save返回→close.receipt原子发布→（存在合法停止请求时）本session StopAck→从Main返回批执行器。无Stop请求的自主失败收尾使用worker-failure来源，只发布收尾回执，不伪造请求或ACK；Python分别核验该分支，不能把请求响应与自主退出混淆。失败尽力写failed回执及诊断，写失败不再尝试覆盖原成功记录或伪造StopAck。成功回执仅代表宏声明完成，Python仍核验身份、大小、结构/表达式与快照可用性，并计算持久哈希；Save无异常返回不能独立证明磁盘内容正确。

VBA回执不能包含最终退出码；退出及回执/快照摘要由Python写入独立关闭核验记录。恢复快照仅限参数及原表达式，不覆盖任意几何/材料/历史/网格setter和外部文件，超范围修改要求丢弃工作副本、从已确认基线建立新session。

READY不再混用：启动就绪和本task ACK清理完成应可区分。改模型后的任务失败，最小策略是ACK保存失败信息后进入retiring，只接受停止、不接下一任务；由关闭恢复/放弃工作副本后新建session。求解后必需后处理失败，先保留已算工程/场及失败记录，不能为了清除dirty而Rebuild销毁唯一可恢复结果。纯Python可选分析失败不撤销已确认求解。

## 5. 按可能情况冻结处理矩阵

|情况|必须保留/核对的证据|预期动作与禁止事项|
|---|---|---|
|启动前/初始化中停止|session、合法stop、初始化阶段|未改模型则无需回滚；完成有限收尾；不捏造任务Completion|
|请求格式/参数校验失败且未改模型|失败Completion、失败阶段|接收失败；已知prepared才允许健康复用|
|部分参数已写入、表达式求值或Rebuild失败|原始表达式检查点、Failure|dirty→retiring；停止时恢复；不把失败ACK后的READY当健康|
|Start返回0|Completion SOLVER_FAILED、Solver日志、返回值|不读作成功、不确认空频段；ACK后退出/恢复；不能从Start=0推出退出码含义|
|Start抛异常、返回1但无可用模式|异常/模式查询、Completion|分别记录原因，不能将三种情况合并为已通过真实Gate|
|求解中停止|持久停止意图、当前task|等待支持的安全点，正常求解无固定总超时；不靠超时重启造成重复求解|
|求解已成、必需后处理/快照写失败|求解事实、缺失产物、失败Completion|保留可恢复结果与诊断；无成功采用；不能自动重建破坏结果|
|纯可选分析失败|已确认主结果、分析错误|保留主结果成功，独立标注分析pending/failed，不重算Solver|
|Completion已发布但接收尚未落盘/GUI或Runner消失|匹配Completion、产物、task-context|先校验并持久接收，再授权清理；无证据不能重放当修复|
|接收已落盘、ACK未发或ACK响应丢失|received、同task/session ACK凭据|重复ACK幂等，不重复采用/求解；不可覆盖其他任务ACK|
|ACK接受后清理仅完成一部分|accepted凭据、剩余文件、关联task状态|清理应可恢复且幂等；accepted本身不证明清理完成/可以接新任务|
|ACK等待时停止，已有Completion|Completion/received及合法stop|保留结果后关闭，不必为了停止伪造任务成功或强制删除Completion|
|恢复参数/Rebuild/Backup/Save分别失败|具体阶段、failed回执或日志|无正向StopAck，保留未知/失败；已死后可明确放弃隔离副本，不提为基线|
|快照保存成功但回执发布失败/磁盘满|已有产物及写入失败证据|不能倒推回执成功，不用重跑Solver修补回执；显式恢复核验|
|StopAck存在但主进程/后代仍活着|解析合法回执及本session进程树|仍等待退出，期限后blocked；不能仅按文件存在排除恢复|
|StopAck损坏/其他session/截断或close.receipt不匹配|原文件及身份诊断|协议错误，禁止降级绕过；不接下一任务|
|干净回执＋有效产物＋确认退出0|任务/模型/退出证据|关闭成立；任务仍按自身结果，失败区间仍pending|
|恢复回执＋退出4|当前已验证例外的全部证据|保留任务失败与退出码；v2上线前仍按现行规则，不扩大白名单|
|收尾回执有效但退出1/其他非零|同session回执/产物、退出码、CST日志|记录模型已保存但退出异常未解释；单列待验证，不自动判干净关闭，也不抹掉保存事实|
|退出0但缺回执/缺产物|退出事实、缺失列表|已死不等于标准收尾；可放弃副本但不自动采用未确认结果|
|访问拒绝/PID身份或后代归属未知|权限/进程身份诊断|unknown，不强杀、不当已死；独立CST实例不参与判断|
|控制器重启或GUI连接旧Runner|版本/源码身份、配置、检查点、关闭记录|同一核验函数重对账，保持显式恢复；禁止用GUI版本推断后台版本|

所有“重试”先区分通信/读证据与有副作用操作：有限等待可用于原子文件出现/退出观察；不得盲目重复Solver、Rebuild、Save或发布冲突回执。超时只表示未确认，不能伪造失败/成功事实。

## 6. 统一核验与兼容边界

计划抽取一个纯证据关闭核验入口，由正常stop、会话发现、显式恢复共用。输入为期望session/任务、已声明协议版本、解析后的回执和产物、可信进程观测；输出独立事实、缺失证据和派生处置，而非单bool。

- 会话发现必须解析匹配回执；活跃或未知进程始终不能被stopped标记排除。仅回执文件存在无效。
- 只在已确认本session所有相关进程死亡后允许abandoned-dead，结果接收对账先于任何清理。
- 旧工作空间按其既有v1规则对账；新v2缺失/损坏回执不得静默回落v1。两者都不得将未知进程当已死。
- 不更新正在运行的宏，不热替换旧Runner。一次session的协议版本固定；新工作空间启用v2前必须有两端测试及受控CST验收。
- 退出1不作为本轮协议设计完成后的默认成功值。只有后续受控对照解释其语义并制定证据组合，才能改变判定；不按所有CST版本通用化。

## 7. 实施切片与验收（L1–L4源码接入，L5待做）

|阶段|范围|门禁|
|---|---|---|
|L1（已实施）|统一事实模型/核验器；修复存活/未知及损坏StopAck发现漏洞|同一证据正常停止/发现/恢复结果一致；具体代码与离线证据见L1实施边界，不覆盖真实CST|
|L2（已实施）|close.receipt v2 Python/VBA codec与原子发布、静态版本选择|四组golden及故障矩阵，禁止降级；只有离线/源码契约证据，真实WWB运行仍待L5，生产不默认启用|
|L3（源码接入）|VBA retiring、求解后结果保护、各关闭阶段回执；生产新会话v2|离线/假对端及源码契约；真实WinWrap和CST故障逐阶段验收仍在L5，不把源码顺序当真实持久性证据|
|L4（源码接入）|正常stop/显式恢复/Runner/GUI统一事实和诊断|收到ACK不等于清理完成、StopAck不等于退出；不中断已确认覆盖，不重复采用；离线证据见L4说明，真实仍待L5|
|L5（部分真实验收）|串行真实副本：正常成功、无结果、重建失败/退出4、七阶段收尾故障及WinWrap四组，十二个停止/ACK时点和六类GUI/Runner实际进程退出|已通过范围见各L5记录；Start=0/Start异常/退出1、整机掉电、索引未发布的rename和任意指令级停止等仍pending；原工程不改、不强杀CST|

L1优先堵安全误判，不以改变退出码规则作为捷径。假Worker只证明状态机，不能证明CST退出语义。启动/通信/退出有界，求解无固定总时限；退出阶段内部预算与后代核验范围在L1测试中明确，不用延长总时限代替证据。

## 8. 实现映射与证据边界

|当前入口|当前职责/需要修订点|
|---|---|
|[close_receipt.py](../csttool/close_receipt.py)：CloseReceipt、decode_close_receipt|L2新codec/版本声明；Task/ACK仍v1|
|[runtime_close_receipt_v2.vb](../data/runtime_close_receipt_v2.vb)：CSTC2_WriteCloseReceipt|L2库与契约宏可用，生产CloseSession调用待L3|
|[Managed VBA](../data/runtime_managed_worker_v1_main.vb)：Main、CSTPMW_CloseSession|任务失败后READY、参数恢复/Save/批返回；L3边界|
|[managed_cstworker.py](../csttool/managed_cstworker.py)：run_task、stop、_stop_exit_is_confirmed|接收/ACK、退出码特殊规则；L1/L4统一核验|
|[project_session_recovery.py](../csttool/project_session_recovery.py)：ManagedSessionRecord.needs_recovery、recover_project_sessions|发现条件及显式恢复判定；L1/L4|
|[managed_session_recovery.py](../csttool/managed_session_recovery.py)：recover_and_stop_session|Completion/StopAck顺序；L4统一核验|

现有测试入口：[ACK/停止契约](../test/ack_shutdown_contract_test.py)、[会话恢复](../test/project_session_recovery_test.py)、[协议恢复](../test/managed_session_recovery_test.py)、[Codec](../test/runtime_protocol_test.py)、[VBA](../test/runtime_protocol_vba_test.py)、[真实停止探针](../test/support/validate_failed_rebuild_stop.py)。它们是增补位置，旧通过数字不覆盖v2矩阵。10月20日仅文档修订；10月24日改动L1 Python核验，不改VBA。用户原始文件在外部环境，不保证随Git迁移。

10月20日协议/文档回归31 passed（1.57s），报告artifacts/protocol-scope-20261020.xml（不保证随Git迁移）。当时只证明现有测试和索引仍通过，不证明缺口修复或v2实现/真实Gate；10月24日证据另列L1实施说明。
