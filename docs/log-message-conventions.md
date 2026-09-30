# 运行日志内容约定

同一会话同时输出同名 `.log` 和 `.jsonl`，轮转周期和保留数量一致。每条记录共用 record_id；控制台与 GUI 保留可读文本。JSONL 每行一个 JSON 对象，堆栈中的换行转义保存。

JSONL schema_version=1：timestamp（UTC）、record_id、level、logger、thread、process、message、event、phase、source、code、context、artifacts、error。事件和上下文由业务代码的 extra 显式提供，不解析文本消息；未标注的普通消息 event/phase 为 null，仍有 source。code 在日志会话创建时记录 revision 与 dirty；无 Git 环境时为 null。

源码位置已通过嵌套 LoggerAdapter 测试验证。错误发生位置读取 error.traceback，相关协议文件或快照查看 artifacts。详细事件入口见 [log-event-index.md](log-event-index.md)。

消息格式采用“动作或结果 | key=value”。面向用户的说明使用中文，字段名与已有事件标识保持稳定，便于搜索。

- INFO：运行开始、就绪、任务开始与结束、安全停止、会话恢复、HOM 和 mesh 分析结果。
- DEBUG：资源路径、配置逐项打印、文件存在性检查、Worker 创建、配置保存、重复状态确认。
- WARNING：可恢复异常、采用替代配置、缺失文件恢复、任务失败及重建准备。
- ERROR / exception：执行失败、环境不可用、保存失败、退出失败；保留原因及必要堆栈。

每次 Backend 初始化生成独立 run_id，以不可变日志上下文传递到 Config、Manager、Worker；独立创建 Manager 时自动生成 run_id。字段同时进入 LogRecord.extra 与纯文本输出，并发运行不共用可变上下文。

按日志所属层提供 project、worker、session、task、job、attempt、status、reason 或 elapsed_seconds。Worker 的 task 是协议任务 ID，Manager 的 job 是用户任务名；Worker 派发消息同时记录二者。

恢复开始与恢复成功必须分别记录，不能在尝试之前宣称已成功。Worker 重建包含开始、完成、失败或停止取消；任务放弃记录原因。CST completion、结果读取、Ack 发布、返回 ready 分别记录，只有确认 ready 后才发布任务结束。退出失败记录进程存活状态及超时值，不宣称标准退出成功。

日志避免输出完整参数列表、场数据及重复的检查通过消息。utils 与现有 handler 保持原状，仅通过标准库 LoggerAdapter 绑定上下文。
