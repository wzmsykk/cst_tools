# 批量表达式恢复与预处理基准重试：真实副本验收

2026-10-25。工具为test/support/validate_batch_restore_close.py，串行、独占探针锁、小网格cell=8、nmodes=1、480–530MHz。原始夹具test/data/Pillbox/Pillbox.cst只读，输出进入artifacts/batch-restore-real-*；artifacts不保证随Git迁移。生产行为见[实现](parameter-restore-close-budget.md)。

初次受限环境启动在许可证检查退出3（FlexNet -63,403），未执行宏，不计功能通过。正常用户权限重试进入预处理/WinWrap并捕获208个参数。200个probe参数通过预处理副本模板中的测试Sub加入，probe001等保留对probe000的表达式依赖；不更改用户工程或生产预处理模板。

故障注入仅在探针首个Worker第二任务中把nmodes改0、probe001改表达式并加probe_added，触发真实Rebuild返回False；不是实际Solver.Start=0或数值不收敛。第一次成功结果及快照应保留，Manager失败退役后应从processed.cst重试原任务。

## 结果与证据

真实CST 2022.5/WinWrap副本的本轮三个目标通过。报告artifacts/batch-restore-real-c0d7b856/acceptance-summary.json及verification.json；report.json保留首轮工具汇总错误，不能仅看其中passed=false而忽略补充核验，也不能把首轮工具称作直接通过。

|检查|实测事实|范围|
|---|---|---|
|批量表达式恢复|208项；restore-batch 12:53:25–12:53:33约8秒|String数组及生产宏实际执行，原表达式文本校验通过|
|新增参数清理|restore-delete约5秒，removed=1|probe_added移除；参数数量恢复208|
|表达式校验|restore-verify begin/returned同秒|probe001从失败任务表达式恢复，原checkpoint不是固定数值替代|
|安全收尾|恢复重建2秒、Backup2秒、Save2秒；恢复入口至batch-return约19秒|v2回执restored-saved、StopAck、快照大小/哈希及进程退出4符合现行严格恢复规则|
|失败后新输入|第二Worker source为processed.cst，输入SHA256与基准一致|没有使用第一项成功快照或失败恢复快照|
|结果保留|首项快照与received记录snapshot_sha256一致；重试前后两次频率均503.49464359617MHz|两项成功、一次REBUILD_FAILED，总Solver调用2次；没有为核验再次求解|
|迟到关闭|真实宏Save前注入2秒暂停；仅测试实例STOP_TIMEOUT=0.3|首次stop约0.359秒，重复stop约0.032秒；期限不变，之后合法回执/进程退出0，再次stop确认关闭|

生产默认600秒未改。迟到用例无Solver调用，预算缩短仅用于测试。两次失败等待诊断为预期输出，不是掩盖异常；日志变化没有重置期限。没有结束任何CST进程或操作原工程。正常用户权限下最终CST进程清单为空；受限环境可能无法看到正常用户进程，清理前使用与实际验收相同权限检查，不能只凭沙箱空清单判断。

预处理基准SHA256=f9d5d4c496d64b1a3b9a1b6795bc6844a4dcc0199c3c1b4a28996e4086b2bbae；原夹具SHA256=7b63939b2dbed3de567aa55a5ff19cb69e7447245882a691be15d28580f1ddfa；首项确认快照SHA256=01a959142e1619b32040b9e4e2ce6f0fbee4fc1e7a44b668deadeb11510d8b59。

## 工具缺陷及复核方式

首轮汇总调用read_close_receipt漏传session_id，真实两次求解/恢复/替换已完成，但工具以TypeError退出，finally完成新Worker正常关闭。修正调用后使用--verify-existing重读回执、StopAck、recorded exit证据哈希、输入与结果哈希；没有重跑这两次求解，再启动单独无求解迟到关闭用例。工具首轮失败与后续复核报告均保留。该入口要求原始证据仍存在；清理后不可直接用旧路径复核，需重新生成。

## 清理与剩余边界

确认进程结束和未跟踪目标后，删除本轮模型/场/结果缓存约24308791字节（包含许可失败副本247080字节），保留轻量报告、宏、参数、日志、协议与cleanup.json文件哈希清单。原始快照/场已删除，需要重新生成，不声称当前仍可直接访问。

本轮不是现场203项复杂CAD与旧逐项方案的同模型对照，不能将8秒/13秒与现场316秒直接相除作为提速倍数。未覆盖零参数实际工程、任意表达式循环/格式归一、数值不收敛Start=0/退出1、长达400秒真实恢复或GUI视觉；已有离线边界及退出1拒绝保持。HOM算法已确认覆盖不被重置由离线/既有HOM Gate支持，本轮仅直接核验Manager确认快照与结果保留，不冒称完整HOM崩溃窗口验收。

离线Worker/Manager/假对端/宏契约回归62 passed（8.88s），artifacts/real-batch-offline-20261025.xml。

最终文档/日志索引3 passed（0.86s），artifacts/real-batch-index-20261025.xml；索引通过只证明链接与符号。pytest本轮临时目录已清理，未提交或推送。
