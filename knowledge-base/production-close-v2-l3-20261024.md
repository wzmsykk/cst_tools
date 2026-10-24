# L3协议落地中的新增边界

2026-10-24：生产生成器现为新session声明v2、拼接两个库，实际CloseSession采集状态并写回执。旧会话不重写。以下均为源码/离线/假对端发现，不是CST现场新实测。

1. L2严格读取“缺回执”在L3等待收尾时不能立即当损坏：仍活着、尚未完成Save/发布时是pending，在同一退出期限内等待；已死后缺回执则继续阻断，不降级v1。
2. valid failed回执与损坏回执不同。进程确认死亡、结果对账后前者可显式放弃副本；不伪称正常关闭，后者不绕过。
3. last_task_id是VBA最后接收的任务，task-context可能已准备下一Task。以none/not-started或此前本session accepted凭据证明停止边界，不能误把未执行Task认作完成；不能用旧帧掩盖后续已ACK的Task。
4. Start=1不等于模式可用，但应保守保留其工作副本作为失败诊断；不可为清理参数恢复而删掉可能唯一的结果。任务仍需模式数及必需产物门禁，Failure不提升确认快照。
5. committed表示有保存的模型，不等于成功计算/采用；Save失败时保留最后完成阶段和原Err详情，不重复Save、不伪造StopAck。

实现和待验收见[L3说明](../docs/production-close-v2-l3.md)。真实WinWrap编译、CST保存后批返回是否改写文件、场数据与表达式一致性和退出1语义仍待L5。测试报告/artifacts不保证随Git迁移。
