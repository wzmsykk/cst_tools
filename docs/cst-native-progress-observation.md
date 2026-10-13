# CST 原生阶段记录

阶段4后，生产留档目录集中到 `logs/<run_id>/workers/<worker_id>/<session_id>/native_progress/<task_id>/`；原生源文件仍在temp工作副本的Result内，不改变CST工程文件布局。

Managed Worker 在提交任务前建立观察基线，求解等待期间每 0.2 秒检查 `<会话>/worker-input/Result/progress.log`。它是可覆盖的状态文件，不按 stdout 日志的追加文件方式读取。

读取 Header / Text / Progress，保留原始大小写、字段类型、未知字段和未知阶段，不预先假定完整阶段枚举。只接受三个字段完整且百分比在 0–100 的状态；读取前后文件指纹变化时跳过，重试下一次观察。启动时已有旧文件不归入新任务，等待文件更新后才记录。

输出位于 `<会话>/native_progress/<task_id>/`：

- `events.jsonl`：阶段、文本或百分比发生变化时追加；含 UTC、相对时长、worker/session/task、参数、源路径、源修改时间和原始文本。阶段回退及再次出现不会丢失。
- `stages.json`：本任务观察到的 Header，按首次出现顺序去重。用于后续建立真实阶段词典，不是已认证的状态机。

普通日志只在第一次观察到某个阶段时提示，不逐百分比刷屏。相同内容重写不重复留档，但有效文件更新仍作为活动证据，避免仅因 stdout 延迟误判内存保护中的日志停滞。

记录失败不终止求解。GUI 现在优先显示 progress.log 的阶段、文本（提示信息）与局部百分比，并标明来源；本任务未观察到有效原生状态时使用 stdout 后备。无百分比时显示不确定进度；停止与终态不接受进度事件，同任务原生进度不被迟到 stdout 覆盖。

另每秒观察同目录 output.txt，提取求解设置、线程数、估计频率、Pass 模态频率和 Accuracy、细化计数及成功/警告/错误消息。保存 output-observed.txt 原始副本与 solver-output.json 最新结构化观察，结束时额外刷新一次。未知内容保留在原始副本，不将 Accuracy 当成网格间频率变化，不将 solver_success_observed 当作任务成功。Model.log 尚未接入；Completion/Ack 仍是完成判据。

限制：文件没有协议 task_id，因此绑定是按串行提交时间观察推断，无法证明迟到内容属于当前任务；轮询可能遗漏 0.2 秒以内被覆盖的状态，不能声称收集了所有阶段。文件更新间隔和实际时效性仍需真实 CST 验证。
