# 六条关键链的可读日志

2026-10-14，仍使用Python logging、现有log/JSONL与事件表，不新增服务或ABI。

## 内容分工

ContextLogger仅合并extra，不拼入消息。GUI和JSONL的message为简短业务摘要；DiagnosticTextFormatter在文本log/console摘要与异常后单独输出context JSON，保留所有扩展字段。DEFAULT_FORMAT中的业务源码、函数、record_id仍保留，AI可按事件和记录身份定位。自定义logging.Formatter不自动附加上下文，需使用DiagnosticTextFormatter或读取record.extra字段。

normalized_context追加worker_id/session_id/task_id规范字段，同时保留worker/session/task旧字段；显式规范字段优先，JSONL schema_version仍为1，加字段不删旧键。job仍为人类任务名称，不当作task_id。ContextLogger的百分号消息仍由标准logging格式化，不把项目路径混进格式模板。

## 六条链

|链|摘要说明|诊断字段与门禁|
|---|---|---|
|预处理|开始副本处理、阶段、参数变化、失败保留、校验后发布|phase/action/target/before/after/status/diagnostics/cst_time/elapsed；其他CST实例基线降为DEBUG|
|提交|任务已提交，等待计算|WORKER_TASK_DISPATCH在atomic_publish成功后记录；worker/session/task/job/fmin/fmax保留|
|求解|等待完成标记；无法确认时先核对协议|CST_WAIT_PROGRESS保留时长、log大小与timeout；CST_COMPLETION只是标记，不宣称可用结果|
|后处理|结果已读，等待接收记录；不可用时不能接收为成功|RESULT_READ_DONE/FAILED、结果数、快照、失败原因；不能将读取失败等同于Solver未运行|
|确认|接收记录保存后发送Ack，Ready后确认完成；失败先恢复|TASK_ACK_PUBLISHED/READY/FAILED；receipt/result_status/recovery_hint；确认失败不无条件声称结果保存成功|
|退出|请求标准退出；校验后关闭；未确认要求恢复|WORKER_STOP_REQUEST/STOPPED/FAILED；PID、退出码、进程存活、时限保留，仍不强杀独立实例|

WORKER_TASK_COMPLETE只有原有结果/Ack/Ready链结束后输出业务结论，成功/失败status和failure保持。此重构不修改CST控制协议或恢复门禁，不增加周期性INFO进度输出。

## 异常传播

log_failure在首个捕获点输出完整traceback，并将record_id作为error_ref；同一异常对象或显式cause向上传播时，上层只记录影响、当前reason/error_type/recovery_hint和error_ref，不重复同一堆栈。上层JSONL error为null代表此次记录没重复堆栈，不代表没有故障；按context.error_ref查首记录。

新的独立异常（例如另一次退出错误）仍有自己的堆栈和身份。隐式context不用于去重复，避免正在处理运行异常时产生的新退出错误被错误折叠；无显式cause的包装可能保守重复。异常类型不允许附加属性时同样保守重复诊断，不丢证据。prepare_run与execute_run接入此机制；安全收尾的独立错误单独保留，不能把error_ref当业务成功标志。

原始文件、参数值和错误信息不因摘要简化被删除。部分启动、可选分析、恢复和旧模块尚未统一，保留现有消息；本批不宣称全仓完成。事件码不再要求出现在message，用event索引检索。旧解析器若只解析消息中的key=value或事件码，应迁移至JSONL字段或文本context行。

## 验收与TODO

覆盖双输出、干净摘要、旧字段兼容、百分号路径、并发隔离、异常因果引用/独立异常、嵌套Adapter源码行以及任务读取/Ack/Ready日志顺序。源码位置仍是业务调用点，不是log_failure内部；事件索引门禁必须同时通过。

本批最终离线528 passed、19 integration deselected；含documentation_index_test与log_event_index_test。报告artifacts/readable-log-20261014.xml（不保证随Git迁移），本批临时目录已清理；未启动真实CST，旧验收数字不作为本次运行门禁证明。

TODO：真实CST串行对照六链日志；逐步统一启动、HOM算法边界、可选场分析与恢复日志；跨进程错误引用需要明确协议，不能从本进程异常属性推断。此机制仅进程内去重复堆栈，不合并不同任务错误事件，不做全局异常缓存。
