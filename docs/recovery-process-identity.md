# 恢复进程身份与恢复进度

2026-11-02。修复针对历史PID复用可能误等，不宣称已证明261020现场的唯一根因。原始分析见 [现场证据](recovery-bundle-261020-20261102.md)。

## 进程归属和旧数据

ManagedCSTWorker启动后写process-identity.json：schema1、session_id、PID、psutil创建时间、实际程序绝对路径及worker-input.cst绝对路径。启动时核对程序，记录只属于该会话；恢复核对session/PID/project和实际创建时间/程序。创建时间比较容差1毫秒，仅处理API浮点，不接受不同创建实例。非同一进程不发送该会话停止请求，也不对这个PID执行20分钟等待，更不终止无关进程。

匹配且仍活着才进入正常协议恢复；进入前及等待轮询重新核验。PID被复用、元数据损坏、AccessDenied或工程不符为unknown，立即报告身份原因并保留RECOVERY_REQUIRED。不存在的原启动进程若还有无法归属的子进程则unknown；无子进程才可认为进程树消失。无法归属的孤儿子进程不通过裸parent PID自动接管。

旧会话没有process-identity.json：若PID及子进程均消失可走既有abandoned-dead；若裸PID仍活着，不猜归属，直接需人工核实。已有close-verification的退出记录须经原session/PID和固定路径保存/协议hash完整复验；这个持久退出证明可排除当前同号新进程，无需等待它。仅worker.state=stopped、文件存在或未经核实的退出码都不够。

这不是放宽成功、结果或收尾门禁。abandoned-dead不冒充正常关闭；退出1仍非标准成功。缺少证据保留原结果、检查点和协议数据，不自动重算、不强杀。旧记录无法证明退出且PID仍活着时需核实现场进程/工程和证据，不能手填身份元数据或删除检查点绕过。

## Runner、GUI和日志

Runner status新增可选recovery_progress：stage、session_id/task_id、reason、current/total、timeout_seconds（出现等待时的本会话预算，不是实时倒计时）。新控制操作清除旧progress。GUI在RECOVERING显示读取配置、预处理核验、逐会话发现/恢复、等待正常收尾、检查点校验、结果核验和采用同步；显示当前会话、任务、原因及计数。恢复完成仍需用户明确继续计算，不自动发起求解。

Backend的RECOVERY_PROGRESS事件提供阶段与当前会话；逐任务采用回调写Runner快照。lifecycle会话事实附process_identity_reason。等待仍有每会话1200秒上限，正常求解无固定总超时。本次没有给磁盘/网络文件调用加硬超时；慢读模型时显示所在阶段/任务，不能保证不可响应的文件系统调用能被立即取消。

## 诊断包

先为control与当前/最近历史run的application.log/jsonl、run.json、summary.json分配候选名额，再枚举历史worker；写ZIP时这些核心文件优先于原生历史日志使用总字节预算。新增收录process-identity.json。1000候选、4MiB单文件、64MiB总内容及截尾/缺失记录仍生效，极小自定义预算不保证所有核心文件同时入包。原包已漏掉的内容无法凭空补回，需在升级版本上重新导出。

## 验收范围

离线模拟PID复用、旧记录、权限/工程不符、原进程消失但子进程未知；验证不进入协议等待、不生成stop.request。正常假对端恢复仍通过；回调/GUI状态与小预算日志收录有回归。没有启动真实CST、未触碰现场F盘或结束任何用户进程。当前已运行的旧Runner不会热更新，需按正常退出流程切换到新代码后使用；不以强制关闭控制台替代标准退出。


最终离线证据：核心136 passed（69.98s），报告artifacts/recovery-final-20261102.xml；随后补充协议ACK阶段回调/身份/Backend/导出/采用及索引76 passed（7.39s，与核心重叠），报告artifacts/recovery-supplement-20261102.xml。GUI恢复相关5 passed（0.45s），artifacts/recovery-gui-focused-20261102.xml。整组主窗口测试一次Qt中途退出1且无XML，不能计为整组通过；独立新显示测试及相关5项复验通过，不作为完整GUI或现场视觉验收。首轮核心77 passed/1 failed是旧假对端没有身份模拟，改为明确matched假身份后复验通过，未放宽生产核验。磁盘约11.49GiB空余，本轮不产生CST/原始场；清理本轮pytest目录，保留轻量报告。没有提交、推送或现场恢复操作。

2026-11-02后续：[A01–A08实施合同](recovery-exit-audit-implementation.md)补齐停止意图/历史意图、恢复暂停、已离线退出核验及导出取消。连接未知时允许明确请求核验退出，真正退出仍由物理证据决定；导出按钮不再禁用而是可取消。旧文对应禁止/等待描述属于先前版本，当前以该合同为准。
