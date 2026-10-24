# L1安全边界修正（2026-10-24）

此前源码探针证明StopAck＋stopped可能排除活跃/未知进程，正常stop与显式恢复判定不同。现将Python判断收敛到session_closure.evaluate_closure，退出1不接受，模型恢复凭据仍单独保留；没有修改CST/VBA API或求解行为。

明确记录兼容变化：没有PID的历史会话不再自动当作关闭；丢失原Popen退出码时，进程死亡＋StopAck仍不能证明退出0。显式确认已死并对账后记abandoned-dead；补充recovery-l1.json保留旧恢复文件，正常stop的close-verification.json是Python观测而非VBA回执。

权限/快照枚举失败为unknown，不声称是死亡；Windows句柄类型修正以避免64位快照句柄截断。PID及可枚举父子链仍有历史证据边界，不具备任意脱离父链进程的追溯能力，不据此杀独立实例。

实施、测试入口和剩余L2–L5见[L1说明](../docs/session-closure-l1.md)。真实CST副本及现场退出1尚未重验；不能把离线模型/构造探针写成CST实测。测试报告在artifacts，不保证随Git迁移。
