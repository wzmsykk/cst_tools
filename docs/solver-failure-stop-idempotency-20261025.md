# 现场求解失败后的停止链：证据与幂等修正

2026-10-25，来源为用户提供的59条JSONL记录，发布源码基线b4a2a6d；run_id=018cc7916f2e4b9aacdaf8330af874c5，失败会话110caff3-2113-49c3-8e95-79bde944091d。本文不等于真实CST修复验收，不更改现场工程或进程。

## 已确认时间线（UTC+8）

- 10:37：188个检查点采用TaskID核验通过，续跑读取原mesh=4、worker=1及700–2500MHz设置。
- 10:39：从1165.823184MHz对应的已确认CST快照恢复，提交1165.82–1215.82MHz任务。没有从700MHz重新开始的记录。
- 11:34:52：任务耗时3313.6秒（约55分钟14秒），返回SOLVER_FAILED；ACK清理成功，Worker进入retiring。
- 首次标准关闭等待120秒后，进程仍被观测为running、无StopAck、无可用close.receipt、模型状态unknown；Manager取消替换，不创建第二个Worker继续计算。
- Manager广播停止时再次发布既有stop.request，发生FileExistsError。这是Python停止请求非幂等的独立缺陷，发生在求解失败及首次退出超时之后，不能作为前两者原因。
- 最终关闭又等待120秒仍未确认；HOM保留188模式和1个pending，持久项目状态为RECOVERY_REQUIRED，未声称安全关闭。solver_calls=191是检查点累计调用数，不等同188模式全部被重算。

资源报告peak_private_bytes=60788281344（约56.6GiB），仅证明统计到该峰值，不证明发生OOM、内存泄漏或达到系统极限。日志中的十分钟等待摘要不是总求解超时。

## 两个代码层修正

1. [FileProtocol.request_stop](../csttool/runtime_protocol.py)现在将同一路径、同session的有效停止请求视为已有停止意图，保留字节和时间戳，不重复写入。进程内不同FileProtocol实例按规范路径共享短时发布锁；不取活动任务锁。跨session/损坏内容/残留临时文件继续拒绝、保留证据，不用盲目重试或覆盖修复。跨Controller仍依赖现有项目所有权，未新增分布式写入协议。
2. [Managed Worker](../csttool/managed_cstworker.py)及[显式会话恢复](../csttool/managed_session_recovery.py)共用该入口，去除exists再写的竞态。StopAck/回执/进程退出仍独立核验，停止意图存在不代表标准关闭成功。

另修正[生产VBA](../data/runtime_managed_worker_v1_main.vb)诊断文案：原先所有solverReturn<>1都写成“returned 0”；新文案拼接实际Long返回值，成功门槛和错误码不变。因此仅凭此次旧版Python汇总，严格来说只能确认返回非1，实际是否0还需原生lifecycle中的returned=行。已有运行宏不会被热替换。

## 尚不能确认

**后续补证（同日）**：现已成功读取Desktop的diagnostics.json、lifecycle.log、cst.log，三者会话ID匹配。下面“不可读取”是首轮状态；当前结论与新增待办见[原生日志对照](solver-failure-native-analysis-20261025.md)。实际Start=0、恢复重建/Save及batch-return已确认；仍缺output.txt及实际收尾回执/StopAck。

现场F:目录在执行环境不可访问；后续提到的三个Desktop文件也没有实际出现在本地/附件目录。尚未取得原生lifecycle.log、cst.log、Result/output.txt及failures/346fe20eb03248f78cbd2d6a427a58e4.json。

必须区分：CST为何非成功返回；之后关闭停在参数恢复/Rebuild/Backup/Save还是其他阶段；大模型正常收尾是否超过120秒；是否有界面提示。缺原生证据不能选定根因、放宽退出门禁、增加总求解超时或强杀。两次退出等待的合并/进度化应另行设计，不以加大期限代替定位。

## 验收入口

[协议测试](../test/runtime_protocol_test.py)：重复发送字节/时间戳稳定、8实例并发、异session/截断/临时文件不覆盖。
[假对端测试](../test/production_close_v2_test.py)：求解失败ACK退役后重复request_stop，再标准close，Solver仍一次、原场字节不变；VBA实际返回值文案有源码契约门禁，未真实WinWrap重新编译运行。

测试数字、轻量报告及清理状态见current-status；没有据此宣称现场CST求解或收尾卡点已修复。用户原始JSONL只在artifacts保留，默认不随Git迁移。

最终专项115 passed（10.78s），artifacts/solver-failure-stop-20261025/tests-final.xml；覆盖协议/Worker/恢复/假对端及文档/VBA源码契约，包含求解失败退役后重复stop的完整假对端收尾。旧契约要求固定0的首轮114 passed/1 failed保留，不算完整通过。本轮临时pytest副本结束后清理，不更改现场工程/结果；未提交或打包。
