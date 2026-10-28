# CST Tools 当前状态与实施路线

状态日期：2026-10-25
历史提交基线：`3717a04`（P0-1停止恢复、故障验收与文档索引）；后续提交包含场故障验收、共同域、Pillbox双网格与真空腔追踪第一版，准确提交身份以Git日志为准。

本文是项目当前状态的权威入口。历史设计文档仍保留其分析价值；若与本文或[最小 Python/VBA 协议 TODO](./minimal-python-vba-todo.md)冲突，以本文和已经通过的真实 CST Gate 为准。

## 本机生成文件管理（2026-10-28）

补齐缓存、虚拟环境、本机配置及运行/报告产物忽略规则。current.ini 取消索引跟踪但保留本机文件，由 default.ini 自动初始化；默认配置、示例和历史已跟踪验收证据保留。见[忽略范围与迁移说明](local-generated-files.md)。

## 本地修正迁移（2026-10-28）

对照远程与本地分支/stash，已覆盖的无总超时、项目记忆、原生进度及恢复门禁保持当前 Runner 实现；补齐 Worker 递增实例 ID、停止时进度保留、旧会话过滤、兼容控制器停止终态、线程命名、prepared 工程配套目录复制，以及前向优先续扫/有界缺口补算。详见[迁移对照与边界](local-fix-migration-20261028.md)。本轮完整离线913 passed、21 integration deselected（129.70s），文档/日志索引同步，轻量报告见迁移说明。本次不操作真实 CST 或现场项目数据。

## 最新状态与近期TODO（2026-10-25）

- 新增[HOM失败恢复链](hom-solver-failure-recovery.md)：原窄窗求解失败后临时cell×1.5重算一次（4→6），再恢复原密度扩窗2/4/8倍、窄窗确认后继续；按成功首模/确认结果判原区间空，失败不当空。正常任务仍只改3项，需恢复密度时才传cell；探测前沿与确认覆盖分开，checkpoint v4可读旧v3并保持指纹/快照核验。
- HOM可严格退役“已结束且恢复/ACK/快照证据完整”的失败退出1会话，再从processed.cst建新Worker，保留abandoned-dead/standard_closed=false，不全局接受退出1；普通批任务默认不变。Runner补齐顶层恢复原因。核心/假Worker等167 passed，专项58 passed及GUI13 passed（重叠），详见新文；真实Mesh/数值恢复/退役串行副本仍pending。

- 新[261012现场诊断包分析](field-failure-bundle-20261025.md)：当前Solver迭代耗尽，任务撤销仅fmin/fmax两项、5秒完成，原生恢复收尾74秒；Python记录进程已退出1、模型restored-saved，唯一阻断为exit-code-not-accepted，不是600秒超时，因此替换未执行。188项已确认模式/覆盖保持。顶层error为空而lifecycle有阻断原因，列为传播缺口；本轮只读分析，不放宽退出码或启动CST。

- GUI默认改为[HOM扫频工作台](gui-hom-workspace.md)：目标/当前区间、确认覆盖与计算上界、模式及后处理值表；完整日志、Worker/CST局部进度、后台管理/控制权归入详细页，失败导出仍在默认页。通过本地只读缓存观察检查点，不按日志推断模式、不改控制协议。
- 本轮主窗口+工作台43 passed（1.80s），Runner/重开/日志恢复39 passed（39.69s），事件/导出等专项19 passed（1.54s，重叠）；一次合并Qt运行退出1无XML不计通过，独立分组复验及边界见工作台说明。无真实CST/现场视觉验收。

- 新增[一键失败诊断导出](failure-diagnostic-export.md)：GUI日志区按钮异步导出到项目diagnostics，当前run/前次上下文、CST原生输出、Worker失败/协议/收尾/撤销及预处理输出一并映射；不需Runner在线，不启动或停止任务。单文件4MiB/总源内容64MiB/1000记录，缺失/截断/外部路径跳过明确留档，排除模型/场及Runner endpoint。Qt关闭期间保护导出线程。
- 本轮相关回归80 passed（36.70s），追加最终专项12 passed（1.21s，重叠）；已有真实日志实际导出约103KB，60份收录/10份不可用，见artifacts/diagnostic-export-real-files-20261025.json。未启动CST；现场网络盘/锁/视觉尚未验收。

- 参数恢复热路径已改为[任务级撤销](task-parameter-undo.md)：只读任务名字及原表达式，跳过同表达式项，不再启动/成功时全量捕获。失败只批量恢复已尝试修改的原有参数并删除本任务新增项；setter前记意图，保留求解成功后不回滚门禁。旧208项全量验收为历史版本，新版真实副本已通过（artifacts/batch-restore-real-062f861b）：requested5/changed3、恢复2项/删除1项；原表达式/确认快照/processed.cst来源及关闭核验通过，Solver仅2次。离线137 passed（12.69s），索引/恢复6 passed（1.06s）。清理24066340字节原始数据，保留轻量证据，不宣称总收尾墙钟提速；详见任务级撤销文档。

- 真实批量恢复/基准重试/迟到收尾副本验收：[本轮证据与边界](batch-restore-real-acceptance-20261025.md)。Pillbox cell8/nmodes1，208项原表达式批量8秒、删除1项5秒、校验通过，恢复批返回约19秒，严格恢复退出4；新Worker从processed.cst重试，两次503.49464359617MHz，Solver共2次，原确认快照哈希保留。无求解延迟用例0.3秒测试预算下重复stop约0.032秒，迟到退出0可确认；不改变600秒默认。首轮工具汇总参数错误已修正并原证据复核，无重算；不覆盖Start0/exit1或复杂CAD性能。
- 本轮离线专项62 passed（8.88s）；实际同权限CST清单空、源夹具不变，清理约24.3MB原始副本/结果，保留轻量证据和哈希。真实数据已删除，复验需重新生成。

- 专项回归130 passed（10.73s），报告artifacts/batch-close-verified-20261025.xml；覆盖Manager、Worker、假对端、停止恢复、关闭门禁、协议与文档/日志索引。初轮新增测试缺少FileProtocol夹具导致52 passed/1 failed，补夹具后复验；另一次测试文件名错误未收集测试，不计通过。未做真实WinWrap/CST验收。

- 批量表达式恢复与单次收尾预算已实施：[实现及边界](parameter-restore-close-budget.md)。StoreParameters精确数组保留表达式、删除新增参数并核对；阶段begin/returned和有界日志观察。Worker默认600秒，重复stop共用期限，Solver无总超时。失败重试按用户选择从预处理基准新建Worker，确认覆盖/结果保留；旧会话关闭不确认则禁止替换。旧现场分析“未实施”为历史状态，真实CST兼容/性能仍待验收。

- 新增output/close.receipt补证：[原生失败结论](solver-failure-native-analysis-20261025.md)。直接原因是求解最大迭代次数耗尽，nmodes=1、估计频率1165.82MHz，后续模板自动取消；非后处理失败。回执经现有v2解析及session/task身份核对，报告restored-saved、恢复快照1730521字节、无收尾错误；未取得快照本体/StopAck/现场进程证据，仍不接受退出1。下列早期“缺output/回执”保留为历史状态，以本条和补证章节为准。未启动真实CST。

- 现场原生补证已读到：[Start=0与慢收尾](solver-failure-native-analysis-20261025.md)。diagnostics/lifecycle/cst三文件确认Start实际0（调用54分13秒），ACK后到恢复完成316秒，Rebuild56秒、Save7秒，总400秒后batch-return；并非永久卡Save，两个120秒等待均早于完成。CST stdout仍退出1，规则不放宽；求解内部原因仍缺output.txt、实际回执/StopAck和资源采样。官方Project文档支持StoreParameters批量表达式恢复，作为下一步优化/验收方向，未在本轮实施或启动CST。
- 原生补证本轮文档/日志索引与现行VBA源码契约11 passed（0.88s），artifacts/solver-failure-stop-20261025/native-review-tests.xml；仅验证索引/源码，不代表批量方案、退出预算或真实CST补验。轻量三文件副本/SHA/时序分析保留，pytest临时目录清理；本轮未新增生产行为或操作现场工程。

- 现场失败链诊断及局部修正：[求解/停止幂等](solver-failure-stop-idempotency-20261025.md)。旧版汇总报Start returned 0、任务约55分钟后失败并ACK退役，之后两次120秒退出未确认；重复发布stop.request的FileExistsError为独立后续缺陷，已修复同session有效停止请求幂等/并发、统一Worker和恢复入口，冲突/坏文件仍拒绝。VBA原先把非1写成0，改为实际返回值文案，wire/成功门槛/关闭门禁不变。现场F:及后续Desktop原生日志不可读，CST求解原因及收尾卡点仍待补证；无真实求解或现场进程操作。
- 本轮协议/Worker/恢复/假对端/文档与日志索引/VBA源码契约专项115 passed（10.78s），报告artifacts/solver-failure-stop-20261025/tests-final.xml；原JSONL及summary.json轻量保留。初次旧契约固定要求returned 0导致114 passed/1 failed，已改为生产宏实际值契约后复验，不计旧失败为通过。未做全仓/真实WinWrap或CST补验，未提交/打包。

- GUI启动自动找回：[项目/后台恢复](gui-session-restoration.md)。正常入口记忆最后项目至用户AppData，再开窗口自动填充持久设置、连接同一Runner并恢复日志/覆盖/模式/错误；后台已退出时仅启动Runner读取历史，不提交start/recover或求解。已有检查点禁止新扫描；损坏记录/丢失目录手动选择，不新建空项目。发布--smoke-test隔离用户记录；无记录首次需手动选择一次。
- 本轮离线810 passed、21 integration deselected（204.81s），主窗口独立34 passed（1.49s），最终文档/日志索引3 passed（1.05s，重叠）；报告artifacts/gui-reopen-{offline,main,index}-20261025.xml，运行python gui_app.py --smoke-test通过。新增存储/GUI专项11 passed、独立GUI重开进程2 passed（均已包含在全套）：连接同一后台/原run_id、start仍一条、无自动recover；离线只启动Runner回放历史，无temp求解会话。没有真实CST或现场视觉验收；未提交/重打包。
- 本轮测试Runner均已核实结束，pytest临时项目已清理；保留artifacts/gui-reopen-20261025内轻量进程日志、summary.json、cleanup.txt和XML，artifacts不保证随Git迁移。未写用户真实AppData、未修改原工程或结束用户进程。

- 退出逻辑与异常资源修正：[完整退出契约](gui-exit-resource-cleanup.md)。主GUI区分仅关闭界面与停止任务→等待收尾→shutdown Runner→关闭GUI；未知/只读/需要恢复/停止或关闭失败时持续显示原因和恢复方法，仍可明确选择仅关界面。detach等待本地在途通信/release后才让Qt关闭；部分构造和清理异常使用补偿清理，移除HOM无用result.log句柄。Runner快照新增可选runtime.cwd、后台管理显示双方PID/cwd及终端提示。Task/VBA/物理安全门禁不变。
- 本轮最终离线797 passed、21 integration deselected（107.89s），主窗口独立34 passed（1.34s）；包含六组独立Qt GUI/假Runner进程的正常退出及Windows目录重命名/释放，含cmd /c和shutdown响应丢失。报告artifacts/gui-exit-offline-final-20261025.xml、artifacts/exit-main-20261025.xml。初轮旧测试仍假定detach立即接受close，795 passed/1 failed不计整套通过；修正为等待客户端收尾后复验。弹窗提示Qt原生崩溃和初版夹具失败另留知识库边界。本轮没有真实CST或现场视觉验收，未提交/重打包。
- 最终文档/日志索引及资源专项8 passed（2.37s，重叠）；六组退出事实/日志和summary.json保留于artifacts/gui-exit-fix-20261025。已清理本轮pytest临时目录；offscreen字体集合0导致截图无文字，现场视觉仍pending，不把结构/退出测试当视觉通过。

- 退出行为审计（分析/复现，未修改生产逻辑）：[GUI退出与目录占用](gui-exit-and-directory-lock-audit.md)。当前“安全停止后退出”只stop+detach，不shutdown Runner；Runner明确以发布根目录为cwd，控制台也可独立占用目录。Windows受控子进程已复现cwd/日志句柄/线程池三类机制；真实非法INI的LocalExecution部分构造、HOM前置失败均复现未关闭日志。尚未取得用户现场PID/句柄，不认定唯一占用者；无CST求解或进程终止。修正项进入TODO。
- 审计回归28 passed（39.91s）：既有GUI Runner/Runner进程及文档/日志索引，报告artifacts/gui-exit-audit-20261025/regression.xml。未修改生产关闭逻辑，不称为退出缺陷修复验收；探针进程正常返回、日志关闭、临时目录清理，保留轻量记录。

- 2026-10-25真实HOM恢复补验通过：[小网格Pillbox记录](hom-interruption-l5-acceptance.md)。修复HOM检查点相对快照路径被误按cwd解析的问题；采用核验现以项目根目录解析，原路径/身份/SHA256门禁保留。cell=8、nmodes=1、480–530MHz，checkpoint/received/solver三个Runner退出窗口每例Solver均5次，与无中断基线的任务参数顺序一致；两次recover不改确认检查点、旧结果/四场哈希保留、采用事件/CSV无重复。汇总artifacts/hom-interruption-l5-verification-20261025.json，不保证随Git迁移。
- 本轮离线其余套件776 passed、21 integration deselected（154.53s），主窗口34 passed（1.05s），专项79 passed（6.73s，重叠）。初次受限回归假对端ACK读取PermissionError未计通过，正常权限复验不证明偶发问题消失。实际孤立旧CST丢失退出码按abandoned-dead收口、不伪造标准退出；会话均无活跃进程/恢复阻断。基线扩窗存在近频结果漂移，独立物理模式判别仍TODO，未称十模/全复杂后处理/掉电通过。未提交/打包。
- 本轮Runner全部离线、CST清单为空、原工程哈希不变；已清理193296796字节（约184.3MiB）模型/原始场及pytest临时目录，保留轻量报告/宏/日志/标记及cleanup.json哈希。原始模型需重新生成后才能严格复核，不能再直接使用验收目录旧路径恢复。

- L5采用标记补齐：[检查点对账](checkpoint-adoption-l5.md)。标准results与HOM已采用TaskID为权威，先核验身份/参数/后处理及快照哈希，再补齐所属RunStore日志/索引和receipt；普通Manager采用也复用幂等写入，不再因receipt已标记而漏补RunStore。Backend在显式恢复和resume准备的项目锁内对账，检查点/模型/覆盖不改、不新建Task、不导入或求解。
- 真实Pillbox双任务三个Runner退出窗口通过：采用尚未开始、事件已写索引未写、索引已写receipt未写。每例recover两次标记字节稳定、每个所属RunStore对同Task采用事件一条、旧Task不再成为导入候选，原检查点/快照/场不变、Solver总数仍2。汇总artifacts/checkpoint-adoption-l5-verification-20261024.json，不保证随Git迁移。HOM多模式/空任务为离线验证，真实HOM及掉电等仍pending。
- 采用补写本轮最终离线768 passed、21 integration deselected（167.10s），主窗口34 passed（1.28s），采用/日志/恢复/后端/索引专项85 passed（7.99s，含重叠）。报告artifacts/checkpoint-adoption-l5-{offline,window,focused}-20261024.xml。已确认检查点/模型无修改、无强杀CST；未提交/打包。
- 本轮三个测试Runner已离线、正常权限CST清单为空、原Pillbox哈希不变。已清理93488634字节（约89.2MiB）模型/原始场及pytest临时目录，保留标记/检查点/报告/日志/宏和cleanup.json哈希；原始产物需重新生成后才能复核。

- L5 Controller/GUI真实进程退出补验：[六类记录](controller-exit-l5-acceptance.md)。实际结束本轮GUI/Runner Python（不结束CST），覆盖GUI重连、求解区间、Completion未接收、received未ACK、归档重命名后、检查点确认后。六类均保持首项TaskID/工程哈希，全部两任务只调用Solver两次；后四类额外复核首项四个场/能量文件哈希。汇总artifacts/controller-exit-l5-verification-20261024.json，不保证随Git迁移。
- 本轮修复：新增HTTP快照execution_active，避免IDLE标签先于线程释放导致GUI过早就绪；根据既有同Task/Session归档索引＋原快照哈希修复receipt旧路径，坏证据仍阻断，不改模型/确认检查点、不重算。收尾竞态和归档路径各保留一轮失败证据；不计为通过。检查点确认但采用标记未落盘用例按pending_index=2续跑不重算，receipt仍acknowledged，标记补写/跨算法导入另列TODO。
- 进程退出本轮离线746 passed、21 integration deselected（90.83s），主窗口34 passed（1.27s），退出/GUI/恢复/协议/文档与日志索引专项50 passed（40.24s，含重叠）。报告artifacts/controller-exit-l5-{offline,window,focused}-20261024.xml。六类真实通过不等于完整HOM/掉电/任意指令级故障通过；原工程未改，无强杀CST，所有测试Runner已离线；未提交/打包。
- 本轮六个验收目录已清理249267286字节（约237.7MiB）模型/原始场及pytest临时副本，保留汇总、成功/失败报告、宏、日志、检查点/接收/恢复记录及cleanup.json哈希清单。原始产物需再生成，不能再直接用原模型路径复核。

- L5停止/ACK补验：[十二时点记录](stop-ack-l5-acceptance.md)。真实复现并修复ACK清理后Completion消失但成功received未采用时漏发现恢复：当前任务接收记录也参与发现，新增received-result-not-reconciled，显式恢复绑定received_task_id，物理标准退出与未采用结果分开。Task/Completion/ACK/v2收尾wire不改，旧后台需正常退出后更新。
- 十二个选定停止/ACK时点通过（含错误session/截断ACK）；两种取消后中断快照E/H与活动场哈希相同；已完成任务每例只Solver一次、实际Manager幂等采用一次。汇总artifacts/stop-ack-l5-verification-20261024.json（不保证随Git迁移）。探针误接inbox轮及修复前ack-accepted漏恢复轮保留失败证据，不计通过。OS级Controller/GUI崩溃、任意指令级停止、Start=0/Start异常/退出1等仍pending。
- 本轮离线739 passed、21 integration deselected（145.55s），主窗口34 passed（1.31s），协议/恢复/覆盖/文档专项77 passed（3.96s，含重叠）。报告artifacts/stop-ack-l5-{offline,window,focused}-20261024.xml。所有CST副本正常批退出，原工程未改、未强杀；未提交/打包。
- 停止/ACK本轮六个目录已清理约177.4MiB模型/原始场及pytest临时目录；保留轻量证据、错误ACK及cleanup.json哈希，原始模型/场需重新生成后才能复核。最终正常用户权限进程清单为空，原Pillbox哈希不变。

- L5部分真实验收：[WinWrap/CST串行记录](close-v2-l5-acceptance.md)。发现Save后至批退出活动.cst大小变化，修正正常回执引用独立.closed.cst Backup，双端codec固定允许列表同步，严格长度/身份校验和退出1规则不变。新token要求两端同批更新，不热替换旧会话。
- 已真实通过：启动即关闭、cell=8单模503.605585MHz及退出0；nmodes=0重建失败退役/恢复回执/退出4；open边界Start=1但无数据库判失败、保存与退出0独立成立。七阶段故障日志/错误码/进程/显式恢复核验通过，restore/save为明确入口异常注入，其他为真实非法参数/写入失败。缺回执及无效StopAck仍保留恢复阻断。真正Start=0/Start异常、退出1、全停止时序仍pending，不称L5全量完成。
- L5追加：WinWrap四组golden全部实际读写/幂等/冲突拒绝并退出0；真实求解后后处理入口异常，四个E/H/能量.m3t收尾前后哈希相同、不恢复Rebuild，任务失败与标准退出0分开成立。离线729 passed、21 integration deselected（157.40s），主窗口34 passed（1.42s），最终协议/Worker/文档及日志索引专项132 passed（12.03s，含重叠）。报告artifacts/close-l5-{offline,window,focused}-20261024.xml；不保证随Git迁移。无强杀、原工程哈希不变，未提交/打包。
- 本轮十个L5验收目录的模型/原始场已清理约80.3MiB，保留轻量报告/日志/宏/参数和cleanup.json哈希；现存数据不能再直接重验原快照，需要先重新生成。原工程、测试夹具及此前用户删除改动未动。

- L4源码接入：[Runner/GUI事实传播](runner-lifecycle-l4.md)。进程退出/任务/模型/结果登记独立显示，标准关闭但Completion待对账不再等同unknown进程；异常原因链及源码跨HTTP保留，清理异常单列。进度事件限频采集、最终刷新、重连历史标记；不修改覆盖/采用门禁。L5真实CST/WWB及现场视觉仍pending。

- L4离线回归724 passed、21 integration deselected（155.42s），主窗口独立34 passed（1.29s）；最后增补的事实/GUI/恢复/文档与日志索引专项40 passed（39.47s，含重叠）。全仓报告采集在最后两项故障测试及明细限量测试加入前，增补门禁由专项覆盖，不称最终全仓总数。报告artifacts/close-l4-{offline,window,focused}-20261024.xml，不保证随Git迁移。未启动真实CST、未提交/打包。

- L3已接入源码：[生产状态/失败退役/v2发布](production-close-v2-l3.md)。新Managed会话生成v2，采集task/model状态，失败ACK后retiring不再收任务；求解后的失败保留当前模型/结果不Rebuild，实际Save→v2回执→合法StopAck→批返回。Python匹配task级ACK清理并拒绝复用，关闭证据保留独立失败/保存事实。旧会话不改，退出1不放行。尚未真实WinWrap/CST验收，L4–L5仍pending；下方L2“生产仍v1”为当时状态。

- L3最终离线713 passed、21 integration deselected（142.87s），主窗口独立34 passed，分组747项；最终假对端/恢复/文档专项22 passed（5.74s，含重叠）。报告artifacts/close-l3-{offline,window,focused}-20261024.xml（不保证随Git迁移）。保留未执行的生产宏样本及哈希artifacts/close-v2-l3-production-20261024；无有效模型、未编译运行。受限专项曾有一次假对端PermissionError，未确定权限策略或共享时序根因；提升权限同专项及全量通过，不证明偶发问题消除。临时副本结束后清理；未提交、打包或启动CST。

- L2已实现：[收尾回执v2](close-receipt-v2.md)包含Python/VBA codec、四组golden、静态版本声明、原子/幂等写入及防降级门禁、隔离WWB契约宏生成/产物校验。生产Managed仍显式v1，不启用新CloseSession状态机，退出1不放行；VBA只有源码契约检查、未真实编译执行，L3–L5仍pending。

- L2最终离线695 passed、21 integration deselected（144.78s），主窗口独立34 passed，分组729项；专项123 passed（3.17s，含重叠）。报告artifacts/close-v2-{offline,window,focused}-20261024.xml（不保证随Git迁移）。保留未执行的微型契约工作空间artifacts/close-v2-contract-20261024-startup及宏哈希；其中8字节.cst只是codec夹具，不是模型。临时pytest副本已结束并清理，未真实CST、未提交或打包。

- 2026-10-24实施L1：[统一关闭证据核验](session-closure-l1.md)接入正常stop/发现/显式恢复；活跃或未知进程不能被stopped/StopAck排除，回执需身份校验，历史无退出码的已死会话显式记为放弃而非标准关闭。新增Python退出观测文件；Task/ACK及VBA保持v1，退出1仍拒绝。L2–L5仍pending，以下10月20日“未实施”是当时状态，不覆盖本轮验收。

- L1验收（2026-10-24）：提升权限离线639 passed、21 integration deselected（136.91s），主窗口独立34 passed，按两组673项；报告artifacts/lifecycle-l1-{offline,window}-20261024.xml（不保证随Git迁移）。之前受限回归一次事件索引未同步、一次结果目录rename WinError5，均保留边界，不计通过；已同步索引后同套提升权限通过。未启动真实CST，不证明退出1原因或L2–L5完成。

- L1最终证据/文档专项40 passed（1.38s），含最后补充的协议等待＋进程退出共用期限测试；其余与上述分组重叠，不将40再次加总。报告artifacts/lifecycle-l1-focused-20261024.xml；测试临时副本结束后清理，轻量报告保留。

- 协议审计与范围更新（设计，未实施）：增加[生命周期故障矩阵及L1–L5](python-vba-lifecycle-protocol-v2-plan.md)，分开任务结果/模型收尾/进程安全/结果采用；计划close.receipt v2、失败后退役、求解后结果保护及统一关闭核验。当前退出码规则不变，不接受退出1捷径；会话发现活跃/未知进程误排除等列为优先待修复，旧验收不覆盖新范围。协议主体、TODO及知识库同步。

- 范围文档本轮检查31 passed（1.57s）：文档索引、现行Codec/VBA/ACK/停止及会话恢复；报告artifacts/protocol-scope-20261020.xml（不保证随Git迁移）。未实现v2或新故障矩阵，未启动CST，不据此宣称已修复发现/退出漏洞。

- GUI新增当前项目“后台管理”：身份/源码位置、连接/启动、控制权、停止/恢复及确认后正常退出；退出核验OS所有权释放，成功后保持离线，不自动启动。旧Runner身份缺失显示未知，安全门禁不绕过。实现与未完成现场验收见[后台管理](gui-runner-management.md)；本轮不启动真实CST，未提交/打包。

- 后台管理验收：相关链91 passed、主窗口34 passed、主题5 passed，分组130项。组合主窗口/主题此前Qt提前退出不计通过；分开复验不证明该原生退出问题已消除。报告artifacts/runner-management{,-window,-theme}-20261020.xml（不保证随Git迁移）。没有现场桌面或真实CST验收。

- 离线后允许选择其他项目的最后调整：GUI/文档专项12 passed，与上述测试重叠，不另计130项；报告artifacts/runner-management-touchup-20261020.xml。测试临时目录已清理，可重新生成。

- 2026-10-20恢复状态修正：统一持久项目门禁、后端与Runner的恢复判定；会话关闭与项目对账分开表达。显式恢复在同一项目锁内加载配置、收口会话、核验检查点/快照并持久写入INTERRUPTED，之后才报告完成。背景、兼容与现场待办见[恢复状态对账](project-recovery-state-reconciliation.md)。本轮不启动真实CST，以下旧验收数字不代表本次代码。

- 本轮合并专项验收85 passed（43.19s）：后端、Runner/HTTP故障、GUI恢复状态、配置/mesh及文档索引；报告artifacts/recovery-state-20261020.xml（不保证随Git迁移）。未做全仓回归、现场GUI或真实CST恢复；尚未提交/推送/打包。

- 用户application.log补充：确认Collecting features、Creating Tetrahedral Mesh、Eigenmode solver、Post-Processing四种原生Header，补齐前两者及四类步骤的中文显示；样例回放等23 passed、26 deselected。该截段7项HOM模式被采用、末尾第8任务在网格阶段；没有进度百分比时序，不能据此解释100%的内部语义。来源/证据边界见[原生阶段记录](cst-native-progress-observation.md)，未新跑CST，原日志未复制进Git。

- 原生进度显示修正：已知Header归一化到标准阶段键，同时保留native_header和原始Text；样例Post-Processing显示“后处理 / 正在生成参数化1D结果”，原始来源/任务信息在提示中。百分比标明局部读数、非任务完成，不改Completion/Ack门禁。旧保存事件兼容、未知标题保留原文；使用/边界见[原生阶段记录](cst-native-progress-observation.md)。本轮不启动CST。

- 原生阶段显示验收：主窗口30 passed，其余离线578 passed、21 integration deselected，合计608项按两组通过；样例/解析/索引交叉专项15 passed，不重复计数。两次单进程全量在Qt阶段提前退出，无完整报告，不能称为单进程全量通过。证据artifacts/native-progress-display-{gui,rest,core}-20261015.xml（artifacts不保证随Git迁移）；未真实CST/现场视觉验收、未提交/推送/打包。

- GUI新增“自动滚动：开/关”按钮，每次打开默认开启，同时控制事件表与原始日志；关闭后继续接收而不跟随，重新开启返回底部，“回到最新”仅一次跳转。保留拖动/选中暂停和有界缓存。实现/使用见[结构化日志](gui-structured-log.md)，本轮不启动CST、不提交/推送/打包。

- 自动滚动验收：完整离线604 passed、21 integration deselected（50.09s），核心日志/主题/文档检查20 passed；报告artifacts/gui-auto-scroll-all-20261015.xml及gui-auto-scroll-core-20261015.xml（artifacts不保证随Git迁移）。主窗口组合子集此前三次在旧进程内假后端线程收尾附近提前退出、无正常pytest结果，不计通过；完整套件通过不证明Qt原生退出根因已消除，实际桌面体验仍待人工验收。

- GUI日志恢复最终离线验收：602 passed、21 integration deselected；专项86 passed。恢复窗口重复close/detach加幂等保护后全量通过；此前两次Qt测试提前退出不计通过。轻量报告artifacts/gui-log-restore-all-20261015.xml及gui-log-restore-focused-20261015.xml（artifacts不保证随Git迁移）。未真实CST验收、未提交/推送或重打包，现有源码包不含本轮修改。

- GUI日志保留/恢复：移除清空按钮及clear API，Runner重启保留状态/日志位置并分页回放历史，GUI恢复覆盖/模式/任务摘要及原日志时间与源码；只显示、不自动提交计算。5000条有界镜像不变，完整历史仍在文件。API、测试与剩余TODO见[日志恢复](gui-log-restoration.md)；本轮未启动真实CST。

- 假Worker HOM复验（053e4ca）：103 passed，含随机谱/标量后处理、GUI假Worker及可选匹配、独立Runner停止续跑与HTTP故障。5组随机谱每组8/8频率、每mode七项后处理、零失败区间；仅正常返回路线完整找齐。未启动真实CST，报告及边界见[专项记录](fake-hom-acceptance.md)。

- 审计修复最终验收（2026-10-15）：完整离线595 passed、21 integration deselected；故障与文档/日志索引专项27 passed。含真实本机HTTP响应体丢失、socket超时、启动未发送/迟到、取消响应丢失及停止意图恢复；均使用假执行器。报告artifacts/runner-audit-fix-20261015.xml及runner-audit-focused-20261015.xml（artifacts不保证随Git迁移）。真实CST逐窗口崩溃和实际桌面仍待验收，未提交/推送/重打包。

- 2026-10-15审计修复：A1–A4及M1已实施，增加按启动ID取消墓碑/停止对账、持久UI停止意图、只读控制权申请、连接代次隔离和有界日志游标v2；配置草稿/执行端口分离。新增真实回环HTTP响应体丢失与socket超时故障验收，全部使用假执行器，未重跑CST。当前结果、剩余TODO与兼容边界见[本轮修复记录](runner-audit-fix-20261015.md)；下两条为修复前审计历史，旧源码包未更新。

- 2026-10-15审计回应已登记：[实施方逐项回应与修复门禁](runner-audit-response-20261015.md)。四项缺陷和维护性建议全部认可；无CST合成对照再次确认，A2另有Future超时/重连状态机复现但尚无HTTP故障注入。执行实现未修改，E0–E5不得视为完整验收通过；既有源码包仍含缺口。

- 2026-10-15审查补充：本机分离主链存在控制权过期后GUI仍只读、跨项目启动、超长日志游标三项合成探针复现，以及启动响应丢失时清除排队停止的代码路径问题。相关离线26项通过不覆盖这些缺口；实现尚未修复，详见[审查记录与待办](../knowledge-base/runner-separation-review-20261015.md)。历史571项及真实CST证据保持原范围。

- 2026-10-15实施更新：E0–E5本机主链已接入，生产GUI经独立Runner控制Backend/Manager，不再在GUI创建真实Backend。持久停止意图、OS所有权、命令去重、重连/仅关界面、空区间采用身份、完成未接收导入及标准批次已实现。当前API见[本机Runner](local-runner.md)，阶段与剩余门禁见[统一计划](execution-platform-implementation-plan.md)。最终单进程离线571 passed、21 integration deselected；真实单任务通过并最终复验、R双任务停止/续跑通过，原工程未改、无强杀。不声称真实CST控制器崩溃注入、实际桌面或远程验收已通过。

- 2026-10-15实施前统一计划存档：[独立Runner→远程控制→多节点执行E0–E9](execution-platform-implementation-plan.md)。取代两个设计各自的阶段顺序；当时尚未开始，当前实施状态以上条及该文第8节为准。E6–E9仍未实施。

- 2026-10-15前置设计：[远程/分布式执行边界与L0–R4 TODO](remote-distributed-execution-design.md)。区分远程控制、独立任务分发和CST原生分布式求解；近期仅预留Controller/执行层、身份和工件引用，不启动远程服务，不改变当前本机实现保证。

- 2026-10-15实施前设计存档：[GUI/Runner进程分离方案及P0–P6 TODO](gui-runner-process-separation-design.md)。记录当时拟议所有权、命令去重、结果对账和验收；同进程边界是历史状态，当前生产接口见本机Runner文档。

- 2026-10-15：GUI停止/退出增加默认取消的确认；关闭等待所有后台线程标准收尾，停止异常不可被后续运行返回覆盖，需要恢复时保留窗口及日志。见[停止/退出确认及边界](gui-stop-exit.md)。相关40项、其余509项分批通过（文档索引重复）；完整单进程回归两次Qt原生退出，根因待定位，真实CST退出对照仍待做。

- 新应用日志目录包含时间/HOM频率范围/新运行或续跑/短ID；完整ID仍在元数据。增加summary.md与logs/index.md，Backend/Manager共用目录，HOM检查点实时更新覆盖，旧目录只补索引不改名。本批离线543 passed、19 integration deselected。见[可读日志目录](readable-log-directories.md)，服务器/网络盘验收待做。

- Managed增加协作停止广播与VBA步骤检查；成功求解中断保留interrupted-project.cst，不回滚覆盖它。HOM求解前保存当前pending，空区间参与覆盖账本；已有检查点/扫描清单拒绝非续跑覆盖。本批离线537 passed、19 integration deselected。阻塞CST调用不能即时抢占，启动尚未注册Worker和仅后处理恢复联调待做。见[停止与覆盖续跑](cooperative-stop-and-hom-resume.md)。

- 六链日志可读性重构：摘要与context分离，参数/进程/任务/事件码仍进双输出；ID新增规范别名；首异常堆栈与上层error_ref关联，独立收尾错误仍保留。任务提交日志移至实际发布之后，现有控制门禁不变。本批离线528 passed、19 integration deselected。见[六链日志设计/API](readable-logging.md)，真实CST日志验收待做。

- GUI日志主视图改为事件表、级别/关键词/阶段/任务筛选及详情；保留原始标签和真实.log/JSONL入口。有界批量模型、身份完整的进度更新同一行，错误不合并。离线524 passed、19 integration deselected，离屏预览已检查；实际桌面体验待验收。见[结构化事件使用/API](gui-structured-log.md)。

- GUI长日志追加改为有界队列/批量刷新，拖动暂停追加、向上阅读不强制跟随、长行不换行；仅显示镜像限流，文件日志不变。本批离线518 passed、19 integration deselected。见[日志显示性能](gui-log-performance.md)，实际桌面拖动验收待做。

- 共享服务器预处理改为任务级归属（取代下方基线中间方案）：父子关系/精确副本路径确认的进程才需退出；其他用户及同用户新旧CST实例仅诊断，foreign不再阻塞重提。本批离线514 passed、19 integration deselected；成功标记/产物门禁不变，真实共享服务器验收待做。见[现行归属规则](preprocess-diagnostics.md)。

- 历史中间方案（已被上条任务级归属取代）：启动前PID+创建时间基线仅记录；当时仍拒绝启动后新活跃未知实例，离线510 passed、19 integration deselected。保留此记录说明旧包行为，不作为现行门禁。见[归属门禁演进](preprocess-diagnostics.md)。

- HOM GUI及Python预处理增加可选“不修改mesh”，默认仍固定mesh；策略保存到project.ini与HOM清单，恢复沿用，拒绝策略漂移及与收敛分析冲突。本批全套离线506 passed、19 integration deselected。见[预处理诊断](preprocess-diagnostics.md)；真实设置保留验收待做。

- 预处理新增参数/历史块/阶段明细changes.tsv，实时转发既有日志链；区分requested、参数读取值及未逐项核验的历史返回，不刷周期时长。API和限制见[预处理诊断](preprocess-diagnostics.md)。本次相关离线52项通过，尚未真实CST重跑。

- 工程预处理失败保留副本及诊断，历史执行/重建/保存取消180秒总时限，加载/退出仍有界，不强杀或自动重试。见[预处理诊断与边界](preprocess-diagnostics.md)。本批相关离线50项通过，尚未重跑用户F盘原模型；旧发布包不变。

入口：[功能—源码/函数—工具—文档索引](feature-index.md)。实施变更必须遵守[文档同步要求](../AGENTS.md)，主动同步相关API/设计/用途、状态、TODO与知识库，不等待另行要求。

- Managed与预处理已使用`-m -b 副本.cst`，执行工程内Model/3D/Model.run；保留参数表达式，使用RestoreDoubleParameter读取参数值。
- 缺失模式后处理失败与同Worker恢复、重建失败及求解器拒绝后恢复已真实通过。Start返回1但无结果的门禁已通过；返回0和Start本身抛异常仍未实测。
- 直接边界setter会被重建覆盖，进入历史后完整/部分更新保留；项目参数与Global Data存储不同，Global Data不自动失效旧结果。见[持久性及求解失败对照](cst-history-persistence-and-solver-failure.md)。
- P0-1坏重建立即停止：已实现最后良好参数表达式恢复、无Solver重放、恢复快照/回执及StopAck检查；最新真实结果以[停止验收](failed-rebuild-stop-recovery.md)为准。恢复后CST可能保留任务错误码4，不能改称任务成功，也不允许仅凭非零进程退出判安全关闭。
- 默认Worker场匹配仍为可选ROI诊断；另有[封闭PEC/真空腔固定参考追踪第一版](vacuum-mode-tracking-v1.md)，支持显式全域掩码和已保存场批量分析。物理身份/阈值未完成校准，不自动删并模式或跳过区间。
- 最新GUI登记/匹配假Worker流程六场景通过（含默认关闭、未确认、回收、拒绝与窗口关闭），全套离线494 passed、19 deselected；仅逻辑/模拟工件验收，不增加真实CST或生产应用Backend的验收声明。见[GUI假Worker验收](managed-vacuum-domain-gui.md)。
- 最新[HOM假Worker专项](fake-hom-acceptance.md)57项通过：五个随机模型正常扫描找齐生成频率及七项标量，异常/重试/检查点恢复通过；持续异常仍保留未确认区间，不将该结果冒称真实CST或完整场身份追踪验收。

|优先级|下一工作|
|---|---|
|P0-1已通过|基线/已有成功快照恢复及恢复重建、快照/回执写入失败三项真实注入通过；不伪造StopAck、不重放Solver。死会话abandoned-dead收口，活跃/未知进程拒绝；最新离线441通过|
|P0部分通过|[缺结果目录场导出及四类HDF5工件故障恢复](field-failure-recovery-acceptance.md)通过，分析恢复无求解重放；仍补Start返回0/Start异常、部分场/原生网格缺失、加载失败及退出卡住门禁|
|P1部分通过|[共同域/掩码/权重及理想Pillbox全域双模](physical-domain-pillbox-acceptance.md)及cell20/30第二mesh全域对照通过；继续多材料复杂CAD、三层网格收敛、阈值校准及自动登记/GUI/连续追踪|
|P1|冷/热缓存全流程性能、路线独立资源峰值与重复性|
|P1第一版小网格真实验收通过|封闭PEC/真空腔固定参考匹配；cell8/10自动工程预检、掩码登记及Tracker/CLI恢复通过，Normal背景/开放边界真实拒绝。[Managed可选开关与GUI](managed-vacuum-domain-gui.md)已接入，默认关闭、单Worker、标准退出后登记；JSON matching配置支持first-valid/外部固定参考、报告与日志输出。下一步候选请求与GUI报告浏览，不把连续追踪等同于逐频枚举|
|P2|GUI场匹配入口及目标Project多版本调用；不阻塞现有Managed/ROI路线|

下文阶段表、旧日期Pending及扩展项保留历史证据，不使用旧测试数量作为当前代码验收；近期顺序以本节和[六阶段验收](mode-field-selection-implementation-status.md)为准。

## 1. 当前结论

项目不再以“先建设完整 Python/VBA Operation ABI”为近期目标。当前方案是：

1. 保留 Warm CST，用于结构不变、主要改变频率范围的批量 HOM 任务；
2. 优先读取 CST 原生 `.rd0` 结果；
3. Python 负责结果读取、严格校验、任务身份和调度；
4. VBA 只保留 CST 内必须执行的状态变化和复杂运行时后处理；
5. Project Profile 声明 prepared 工程、允许修改的参数、注册模板和结果能力；
6. 不把 CST Result Template GUI 操作包装成运行期 ABI。

GUI、默认 CLI、生产 `CSTManager` 和算法执行链均已切换到 Managed Worker 与结构化任务 API。旧 `local_cstworker/worker.vb` 路径已经删除。

## 2. 当前执行链

```text
Python Task
  -> 原子提交 Task v1
  -> -m -b 加载临时工程副本后执行工程内Model.run
  -> Profile 预检注册模板
  -> 应用允许的参数
  -> Rebuild / Solver
  -> CST Result Template / 原生 .rd0
  -> Completion
  -> Python 读取并校验结果
  -> Ack
  -> 继续下一任务，或必要参数恢复 / Save / StopAck / 返回批执行器
  -> Python核对退出及恢复证据
```

结果选择顺序固定为：

```text
native CST result -> Python-derived result -> optional runtime VBA
```

## 3. 已完成阶段

| 阶段 | 已验证内容 | 真实 CST 证据 |
|---|---|---|
| P2.5 | Python/VBA v1 Codec、Completion/Ack、标准生命周期 | Contract Gate 通过 |
| P3 | Pillbox 临时副本、literal/expression、Rebuild/Solve/Flush、一个 `.rd0` | `503.782 MHz` |
| P4 | 同一 CST 进程串行双任务、独立结果、Ack 栅栏、Stop | 双任务 Gate 通过 |
| P4.5 | HOM 固定结构、仅变频率范围的 Cold/Warm 对照 | Warm 总墙钟约 `1.563x`；P5 扩展 Gate 约 `1.445x` |
| P5 | 五个 HOM 原生标量严格读取及 Cold/Warm 一致性 | Frequency、Q、R/Q 0/5/10 mm 一致 |
| P5.5 | x/y/z 任意积分轴运行时 R/Q；固定模板与动态 VBA 路由 | z 轴 5 mm 与原生模板一致 |
| P5.6 | CST 官方 iterator 盘点注册模板；`EvaluateResultTemplates` 当前 Run 评估 | 5 个 M0D 模板，评估前后 `765.981 MHz` |
| P6 | `hom-2022-v1` 最小 Profile；求解前能力预检和 fail-fast | 正负两个 Gate 均通过 |
| P6.5 I | Profile 接入有界 HOM Warm Worker；会话级单次预检 | 五项结果一致，Warm `1.379x`；缺模板在首个 Solver 前失败 |
| P6.5 II | 同一 Profile 驱动原生读取、结果分类和 R/Q 路由 | 变体 Profile 测试通过；真实多轴 Gate 保持一致 |
| P7 | Profile、严格标量读取、Provider 选择抽成通用核心 | 基础 `ProjectProfile` Worker、fail-fast、多轴 Gate 均通过 |
| GUI P0 | offscreen Qt 安全网、启动条件、线程信号和按钮锁定 | GUI `8 passed`；完整默认测试通过 |
| GUI P1 | 显式 RunState、组合式 Worker、后台准备和集中状态渲染 | GUI `10 passed`；失败可重试、重复启动被拒绝 |
| GUI P2 | 标准停止、非阻塞受控关闭、阶段与进度显示 | GUI `13 passed`；关闭等待全部线程结束 |
| GUI P2.5 | 真实 GUI/Controller/Manager 配合 Fake Worker 的全流程 Gate | 成功、失败、运行中关闭三条流程通过 |
| GUI P2.6 | GUI 可调 Worker 并发数，运行请求冻结配置并传入 Manager | 默认为 1；用户可按本机资源和许可证显式调高 |
| GUI P3 | 类型化算法/PPS 设置、稳定 method key、正确 Qt 模型通知、版本化 JSON | 新旧 JSON 兼容；P3 与 GUI 定向测试通过 |
| GUI P4 | 统一浅色工程工作台主题、语义操作样式和运行状态反馈 | 离屏渲染成功；主题与既有 GUI Gate 通过 |
| GUI P5 | 固定坐标主窗口改为响应式双栏工作台 | 缩放布局与 UI 源文件编译 Gate 通过 |
| GUI P6 | 对话框事务、运行期冻结、已有项编辑、父子生命周期和明确源码命名 | GUI 功能 Gate 36 passed |
| GUI P6.5 | 真实后端启动、可移植 PyInstaller 配置与独立目录打包 smoke | 打包程序退出码 0，无 CST/UI 残留 |
| GUI P7–P9 | Application Service、生产后端和生命周期收口 | GUI/CLI/测试替身均直接使用现代后端协议；旧 Engine 适配器和 `cst_tools_main` 门面已删除 |
| P10 | 生产算法替换旧 Manager API | 默认、TM020、WTC 使用 `CSTManager`、`SimulationTask`、`execute/run_batch` |
| P11 | HOM 扫描完整性修复 | 窄区间逐个求解 Mode 1、微小容差推进、有限重试和原子 checkpoint |
| P12 | GUI 生产 Worker 迁移 | 默认后端使用长驻版本化文件协议 Worker；Completion/Ack 栅栏，标准 Save/Quit，保留声明式运行时 VBA 后处理 |
| GUI P13 | 现代运行工作台 | 可调整双栏、状态徽标、阶段摘要、显式安全停止、日志治理与键盘焦点反馈；GUI Gate 45 passed |
| P13.5 | CST 工程参数预处理 | 在独立工作副本中添加 `fmin/fmax/nmodes/cell`，项目初始化时通过原子 History 步骤固定四面体 Mesh 并关闭自适应，显式完成标记、Save/Quit，源工程保持不变 |
| P14 | 可恢复 HOM 扫描会话 | 不可变 `scan_manifest.json`、协作式停止、禁止停止期派发/Worker 轮换、ACK 阶段 Stop、独立 Windows 进程组、`INTERRUPTED` 状态、残留会话自动发现及 GUI 恢复 | Pillbox“运行中停止→Save/Quit→新会话恢复完成”Gate 通过，`1 passed in 84.90s` |
| P14.5 | CST 后台进度 | 增量 tail 每个 Worker 的 `cst.log`，解析 Mesh、Refinement、Eigenmode Pass 和局部百分比，经 Worker/Manager/Backend/Qt signal 显示；不使用 PIPE，不把 Pass 百分比称为总进度 | 真实 Pillbox 日志、频段身份、局部百分比及安全退出 Gate 通过，`1 passed in 56.95s` |
| P15 | CST 后端版本切换 | 自动发现本机全部 CST 安装、GUI 显式选择并持久化、运行期冻结；Manifest 绑定版本和可执行文件 | 多版本发现/校验、后端状态门和 GUI 切换测试通过 |
| P15.5 | HOM 多阶段异常恢复 | 真实 HOM 顺序求解 10 个 Mode 1 窄窗口结果；Mode 3 后安全暂停、Mode 7 控制器丢失、Mode 9 CST 进程树死亡并从 Mode 8 快照重算 | 10 个频率严格递增、7 项后处理齐全、两类恢复凭据正确、无交互式 CST 残留 |
| P15.6 | 确认快照生产接力 | 成功结果发布 `ProjectSnapshot`；仅顺序 HOM 任务显式请求同槽快照接力；标准批量任务保持独立；HOM checkpoint schema 3 持久化并校验快照，续跑前由快照重建 Worker 池 | 单元 Gate 覆盖 Mode 8→9 轮换、标准批处理隔离、显式恢复、快照篡改拒绝和生产算法续跑 |
| 标准模式解析 Gate | 四 Worker 批量改变 Pillbox 半径，按 TM010 解析模型优化至 500 MHz；注入 Worker 异常、Solver Failure 和重试耗尽后恢复 | 54 次任务、6 轮；229.48730469 mm、499.99509991 MHz；轮换始终回到基础工程，不启用快照接力 |
| 标准模式真实 CST Gate | Gate 固定使用 1 个 Managed Worker；按真实 Frequency 优化 Pillbox 半径 | CST 2022 单 Worker：3 次求解、1 轮；230.8125 mm、499.792534459 MHz；标准退出且无残留进程 |

P11 已移除大区间多模饱和二分方案；默认 PPS 恢复为 `iModeNumber=1` 的非 `_All` 方法。严格同频简并模态仍需要专门的局部多模 Gate，当前不能宣称已覆盖。P11 尚未执行完整频段的真实 CST 找全验收。P12 Managed Worker 双任务真实 Gate 已通过：同一 CST 会话连续完成两个任务，Completion/Ack 和 Stop Ack 正常，进程以退出码 0 结束且未强制清场。P14 已验证 Pillbox 的安全停止和新会话恢复生命周期，但不等同于复杂 HOM 工程 500–1000 MHz 全频段验收。

P14 的普通“安全停止”在 Stop Ack 超时时只返回 `RECOVERY_REQUIRED`，不再自动终止 CST。GUI 的“恢复会话”会扫描项目运行目录中的 Managed Session，补齐遗留 Completion 的 ACK，并通过 Stop Request/Ack 完成 Save/Quit。强制结束已拆为显式 `emergency_terminate()`，调用后工程必须保持 `RECOVERY_REQUIRED`。

异常恢复进一步区分两类会话：仍存活的 CST 必须完成 Stop Request → Completion ACK → StopAck → 进程退出；PID 已明确死亡的隔离 Worker 会话写入 `abandoned-dead` 恢复凭据，并从最后一个原子 checkpoint 重算未确认区间。所有会话收口后，`project.ini` 才从 `RECOVERY_REQUIRED` 持久化为 `INTERRUPTED`。存活但无响应的进程不会被恢复流程自动强杀。

真实十模式 Gate 同时证明：安全暂停后应以最近一次成功任务生成的 `project.cst` 快照作为恢复输入，而不是重新复制最初 clean 工程；异常死亡后的 Worker 工程不可信，必须回退到死亡前最后一个已确认快照。该规则现已进入生产 Manager 和 HOM checkpoint，而不再只存在于 Gate 驱动代码。空窗口以 `frequency=-1` 明确识别并推进，不得作为模式写入 checkpoint。

## 4. `hom-2022-v1` Profile

Profile 当前仅覆盖一个经过验证的 HOM 工程：

- CST：2022；
- prepared 工程：`project/HOM analysis/HOM analysis_clean.cst`；
- Warm 任务只允许修改：`fmin`、`fmax`；`cell` 在项目初始化时固定，运行期不再修改；
- 必需模板：Frequency、Q-Factor、R/Q 轴上、R/Q 5 mm、R/Q 10 mm；
- 原生结果：上述五个 `Mode 1.rd0` 标量；
- 动态 VBA：任意轴/任意位置 R/Q、Shunt Impedance、Total Loss、Voltage。

Profile 验证使用 CST 官方 `ResetTemplateIterator/GetNextTemplate`，比较 result name、template type、template name 和 folder。缺失能力返回 `PROFILE_CAPABILITY_MISSING`，且必须在参数更新、Rebuild 和 Solver 之前终止。

## 5. Result Template 边界

- `.r0d/.r1d` 是模板定义 artifact，不是物理结果；
- `.rd0` 是当前运行产生的标量结果；
- CST 2022 公开 VBA API 支持模板枚举和 `EvaluateResultTemplates`；
- CST 2022 没有公开的模板新增、复制或删除 VBA API；
- 官方旧 `Import Result Templates` 宏已废弃，复制/粘贴由 GUI 提供；
- 直接生成或修改 `.r0d` 不能证明模板已注册；
- 模板安装属于 Profile 制备/发布，不属于每任务运行协议。

官方 `3D Eigenmode Result` 模板本身支持 x/y/z 积分轴，但当前 prepared HOM 工程只注册了 z 轴 0/5/10 mm 三条 R/Q 积分线。未注册的轴或位置继续由 `EigenResult_Complex` 在同一次求解结果上计算；求解后禁止通过工程参数变化驱动模板，因为 `Update Params` 会使结果失效。

GUI 的复杂后处理设置可为 R/Q 和 Shunt Impedance 分别选择 X、Y、Z 积分轴，并输入三个坐标偏移。积分轴自身的偏移固定为 0，另外两个横向坐标可配置；旧 PPS 未声明轴时继续按 Z 轴解释。

GUI 暴露 HOM 四面体固定网格的 `mesh_cells_per_wavelength`。该值只在新项目预处理阶段写入 `cell`，History 同时设置 `MeshSettings.StepsPerWaveNear` 并关闭 `EigenmodeSolver.SetMeshAdaptationTet`；运行期任务不提交 mesh 参数。该值写入 `project.ini` 与 `scan_manifest.json`，恢复时变化会被拒绝，改 mesh 必须创建新项目。

CST 工程预处理与正式 Warm Worker 均以不抢占焦点的最小化方式启动；预处理器可通过 `run_in_background=False` 显式切换为交互启动，默认保持后台。

Mesh 收敛分析是新项目启动前的可选阶段。默认按 `10, 15, 20, 25, 30 cells/λ` 逐级建立临时工程，对同一频段的单模标量后处理结果计算相邻级别相对变化；所有结果低于默认 `1%` 容差且连续两个级别稳定时提前停止，并把该级 Mesh 自动用于正式项目。分析结果输出到项目目录下的 `mesh_convergence/mesh_convergence.json` 与 `.csv`；未在上限内收敛时不启动正式扫描，并保留报告供调整范围。

配置层主类已采用 `GlobalConfigManager` 与 `ProjectConfigManager` 命名，旧名称仅作为兼容别名。运行时以不可变 `GlobalSettings`/`ProjectSettings` 为主接口，`ConfigParser` 仅保留在序列化边界。配置 schema 当前为 3，canonical INI 全部使用小写 snake_case，并按 `paths/cst/execution/artifacts/mesh/task` 分区；无版本旧配置按 schema 1 迁移，高于当前版本的配置会被拒绝。新工程摘要统一使用 SHA-256，旧 MD5 配置仍可读取。全局 INI、项目 INI 和后处理 JSON 使用统一的同目录原子替换；全局默认配置位于所选 `current.ini` 的同级目录，并作为缺失字段的默认层加载。详见 `configuration-design.md`。

## Pending（2026-10-07）

- [x] 2026-10-08 HOM 扫描返回频率 -1：已将频率查询从电场树选择和 QFactor 计算中独立；模式缺失、非正频率及场树缺失返回明确 VBA 错误。扫描拒绝非正频率并记录 HOM_SOLVE_INVALID_RESULT，保留有限重试，不按空窗口跳过。新增 -1/0 无效频率与重试恢复测试；默认测试 287 passed、17 integration deselected。尚未启动真实 CST 验证；现场具体模式缺失原因仍需原始日志确认。Worker 重新初始化不在本次修正范围内。
- [ ] 运行阶段显示与实际不一致：已静态检查 `GUI/run_controller.py`、`GUI/main_window.py`、`csttool/cst_progress.py`。当前 GUI 固定的 1/4–4/4 生命周期进度与 CST 单阶段百分比共用进度条；CST 事件没有百分比时保留上一阶段数值；日志解析器跨任务保留 stage/pass，且用读取时的当前任务上下文标记日志，存在延迟日志归属错误风险；停止或结束后未过滤迟到的 CST 事件，失败时阶段标签也未统一重置。待运行结束后修正：由后台生命周期/任务协议驱动权威状态，日志仅补充求解细节；按 run/session/task 区分事件并在新任务重置解析状态；阶段无百分比时显示不确定进度；终态和停止状态优先于日志；分开显示扫描总体进度与当前 CST 阶段进度，多 Worker 分别维护状态。验证跨区间、窗口扩大重算、网格/求解/后处理切换、停止/失败/完成及迟到事件。当前仅记录方案，尚未修改代码；具体现场错位需结合 CST 原始日志核验。
- [ ] 日志线程命名：Qt 创建的后台线程被 Python `threading` 识别为外部线程，默认显示为 `Dummy-1` 等。为 GUI 主线程、运行、停止及恢复线程设置明确名称，例如 `GUI/MAIN`、`GUI/RUN`、`GUI/STOP`、`GUI/RECOVERY`，并验证日志输出。用户要求当前运算期间不修改代码；待运行结束后再实施。本项尚未实施。

## 6. 尚未完成

- 旧 Worker、Pattern 和队列式 Manager API 已删除；生产只通过显式 Worker 工厂创建 Managed Worker；
- GUI 和默认 CLI 已不再提供旧 Engine 兼容入口；
- 当前暂不扩展到 default、TM020、WTC、Pillbox 或复合 Enlarged/HOM Profile；
- 没有自动安装 Result Template；
- 已有 HOM 运行 Manifest；没有通用 Profile Schema、动态 capability negotiation 或多 Transport；
- 没有完成 `cst_version` 只读核心的仓内提取和跨版本矩阵；
- 没有建立 20–30 点以上的 Warm 性能、内存增长和失败率统计；
- Shunt Impedance、Total Loss、Voltage 仍缺少原生/Python 派生等价性证明；
- 运行时复杂后处理 VBA 仍按能力边界保留；旧 Worker、Pattern、队列式 Manager API 和旧 PPS 列表格式已经删除。

这些项目不是 P6 的隐含组成部分。下一阶段只抽取已经由 HOM Gate 证明的通用核心，不以第二个 Profile 为前置条件，也不扩大为通用 ABI。

## 7. 历史扩展顺序（非当前近期TODO）

1. 用真实 CST 分别验证默认、TM020 和 WTC 的 `SimulationTask` 生产调用；
2. 将 Profile/Warm Worker 泛化为可接受任意任务数的生产候选 Worker，再通过 `worker_factory` 接入 `CSTManager`；
3. 将 WTC/TM020 独立优化入口收口为同一现代 Backend 工厂；
4. 保留 HOM 专属 R/Q 薄适配层，不把物理量语义下沉到通用核心；
5. 暂不做 Profile 序列化、Manifest、动态 capability negotiation、插件 ABI 或多 Profile 注册表。

## 8. 文档导航

- AI定位入口：[功能索引](./feature-index.md)
- 文档同步约定：[AGENTS.md](../AGENTS.md)
- 最新停止恢复：[P0-1验收](./failed-rebuild-stop-recovery.md)
- 近期门禁：[场匹配实施与验收](./mode-field-selection-implementation-status.md)

- 当前实施记录：[最小 Python/VBA 协议 TODO](./minimal-python-vba-todo.md)
- 测试命令与 Gate：[测试指南](./testing-guide.md)
- GUI 重构路线：[GUI 重构 TODO](./gui-refactor-todo.md)
- 运行协议：[Python/VBA Runtime Protocol](./python-vba-runtime-protocol.md)
- 原生结果路线：[CST 原生结果优先 TODO](./cst-native-results-todo.md)
- 工程格式知识：[CST 项目文件知识库](./cst-project-file-knowledge-base.md)
- Result Template 格式：[Result Template 文件结构](./cst-result-template-format.md)
- CSTManager 公共接口：[CSTManager API](./cstmanager-api.md)
- CSTManager 设计：[CSTManager 设计文档](./cstmanager-design.md)
- 应用后端 API 与生命周期：[CST Application Backend](./application-backend.md)
- HOM 扫描算法：[HOM 自适应区间扫描](./hom-scan-algorithm.md)
- 历史完整 ABI 提案：[现代跨语言 ABI 设计](./modern-cross-language-abi-design.md)

### 2026-10-25 最终离线复验补充

正常用户权限的无CST协议/Runner回归92 passed（12.49s），扫描与恢复检查点73 passed（6.44s），GUI及假Worker流程15 passed（1.62s），诊断导出与索引27 passed（3.19s）；各组重叠，不相加。报告分别为artifacts/hom-recovery-native-final-20261025.xml、hom-recovery-closeout-20261025.xml、hom-recovery-gui-final-20261025.xml、hom-recovery-bundle-20261025.xml。此前受限环境协议夹具读文件出现PermissionError，88 passed/4 failed/4 errors；保留失败记录，不用重试掩盖原因，正常权限通过也不证明现场不存在瞬时文件访问异常。

最终审计将生产接口的空后处理列表视为输出缺失，禁止据此确认空区间；通用扫描器的明确空结果契约保留。相关测试首次52 passed/2 failed：密度测试夹具以空后处理结束尾窗，更新为含终点模式的夹具后54 passed（3.10s），报告artifacts/hom-recovery-final-audit2-20261025.xml。未启动真实CST，临时加密是否实际生效及现场扩窗恢复仍待串行副本验收。轻量报告保留，临时测试副本清理；artifacts不保证随Git迁移。

### 2026-10-25 扫描频率命名澄清

扫描与算法设置中，fmin显示为“扫描目标下限”，fmax显示为“首个求解窗口上限”，endfreq显示为“扫描目标上限”。例如500/700/1000表示目标500–1000 MHz，首次求解500–700 MHz；fmax不是整体终点。标签、占位提示、无障碍名称及校验消息保持一致，附用途说明；长标签换行并沿用可滚动布局。要求fmin < fmax <= endfreq。失败恢复探测可以暂时超出目标上限，结果准入仍受目标上限限制。

本次仅调整GUI文案，不改配置键、持久化格式、扫描/错误恢复行为；续跑仍以检查点目标为准，无须迁移旧项目。GUI配置、HOM工作台和文档索引39 passed（1.87s），artifacts/gui-frequency-labels-20261025.xml。包含标签/提示/控件关联、数值传递及跨字段错误测试；offscreen测试不证明现场DPI和字体显示效果，无真实CST求解。轻量报告保留，临时目录清理，artifacts不保证随Git迁移。
