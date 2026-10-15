# CST 原生阶段记录

阶段4后，生产留档目录集中到 `logs/<run_id>/workers/<worker_id>/<session_id>/native_progress/<task_id>/`；原生源文件仍在temp工作副本的Result内，不改变CST工程文件布局。

Managed Worker 在提交任务前建立观察基线，求解等待期间每 0.2 秒检查 `<会话>/worker-input/Result/progress.log`。它是可覆盖的状态文件，不按 stdout 日志的追加文件方式读取。

读取 Header / Text / Progress，保留原始大小写、字段类型、未知字段和未知阶段，不预先假定完整阶段枚举。只接受三个字段完整且百分比在 0–100 的状态；读取前后文件指纹变化时跳过，重试下一次观察。启动时已有旧文件不归入新任务，等待文件更新后才记录。

输出位于 `<会话>/native_progress/<task_id>/`：

- `events.jsonl`：阶段、文本或百分比发生变化时追加；含 UTC、相对时长、worker/session/task、参数、源路径、源修改时间和原始文本。阶段回退及再次出现不会丢失。
- `stages.json`：本任务观察到的 Header，按首次出现顺序去重。用于后续建立真实阶段词典，不是已认证的状态机。

普通日志只在第一次观察到某个阶段时提示，不逐百分比刷屏。相同内容重写不重复留档，但有效文件更新仍作为活动证据，避免仅因 stdout 延迟误判内存保护中的日志停滞。

记录失败不终止求解。GUI优先显示progress.log的阶段与步骤，来源放在提示信息中；本任务未观察到有效原生状态时使用stdout后备。无百分比时显示不确定进度；停止与终态不接受进度事件，同任务原生进度不被迟到stdout覆盖。

## 2026-10-15：原生阶段格式与局部读数修正

### 后续用户application.log补充

来源为用户桌面application.log（118412字节，SHA256 `42b591ac5243eb44fd5012eaa2d1c1d748b470aae3aca12fd168da8027a99265`），未复制/提交原日志。源代码路径表明运行包为053e4ca-working-facdc8aa，不包含本轮工作区修复。

|原始Header|首次出现时的原始Text|记录次数|显示|
|---|---|---|---|
|Collecting features:|Collecting all features|8|收集模型特征 / 正在收集模型特征|
|Creating Tetrahedral Mesh:|Mesher initialization|8|四面体网格生成 / 正在初始化网格生成器|
|Eigenmode solver:|Calculating eigenmode solution.|7|本征模求解 / 正在计算本征模|
|Post-Processing:|Creating parametric 1D results.|7|后处理 / 正在生成参数化1D结果|

补齐feature-collection和tetrahedral-mesh两个已观察标题的显示键，未知标题仍保留原文；这里的“收集特征”是CST内部阶段，不是Python/VBA工程预处理。

日志窗口14:33:34–16:17:06，有7条HOM_MODE_ACCEPTED和相应后处理值，末尾第8个任务处于网格阶段；没有WARNING/ERROR/CRITICAL级别行。这只是该截段记录，不证明整个扫描完成，也不独立验证原结果文件。
截图任务b67a0ca7-1afb-4752-9ecb-3a482c36f386在16:13:42.696观察到后处理，16:15:40.911读取7项结果，16:15:41.117完成Ack就绪，16:15:41.244被HOM采用。后处理观察至Ack约118.4秒，不能把阶段标题或图中的100%当作任务完成。

该application.log只在本任务Header首次出现时提示，没有百分比或Text全部变化；30条阶段记录不等于完整阶段轨迹，不能由这些时间戳精确计算每阶段耗时，亦不能判断100%是否残留。进一步判断读数需原native_progress/events.jsonl或progress.log时序样本。

此次补充四阶段样例解析/GUI及相关检查23 passed、26 deselected，报告artifacts/native-progress-log-samples-20261015.xml（不保证随Git迁移）。测试阶段标题/Text来自用户日志，测试百分比为合成0或未知，不冒充现场读数；未运行CST，旧608项分组数字不是本补充代码的全量验收。

### 原始截图修正记录

用户样例Header=`Post-Processing:`、Text=`Creating parametric 1D results.`，截图显示未翻译阶段且百分比为100。源码核对：Tracker直接把原生Header传作stage，GUI中文映射却使用postprocess；Text只在悬浮提示中，因此正文缺少具体步骤。该样例没有提供完整progress.log，不能据此判断百分比是该步骤完成、上个子步骤残留还是整个后处理完成。

现在normalize_cst_stage将已知Mesh/Meshing、Eigenmode(s)/Eigenmode Solver、Post-Processing等标题映射到既有标准键，允许大小写、分隔符和尾冒号差异；未知标题不猜测。CstProgressEvent新增可选native_header，stage为标准键、message保留原Text，native_header保留原Header；旧构造参数继续有效，旧保存事件的raw stage在GUI也做映射。

界面将此样例显示为两行：`Worker 0 714.606–764.606 MHz · 后处理` / `正在生成参数化 1D 结果`；两列等比布局，阶段文字可换行，避免仅剩120px。百分比仍为原始读数，注明`CST 局部读数 100%（非任务完成）`；未知具体步骤仍按原文显示。原始阶段/Text、来源、task/session置于悬浮提示，原始events.jsonl/stages.json格式不变。

100%仅表示CST提供了该数值，不驱动Manager完成、GUI READY、Completion/Ack或HOM区间确认；阶段/文本变化可使局部进度回到0。既不把100%抹掉，也不凭单条样例宣称整个后处理结束。无原生百分比继续显示不确定进度。

测试覆盖本样例、原始证据不变、未知阶段保留、旧事件回放、局部100%不改变RUNNING状态、来源优先级、终态忽略及显示列宽。未启动真实CST；本轮测试数字以current-status为准，真实桌面视觉/未知版本标题仍需现场验收。

本轮分组验收：主窗口30 passed（1.29s），其余离线578 passed、21 integration deselected（51.25s），合计608项在两个进程中通过；样例/解析/文档索引专项15 passed，与前两组有重叠，不能重复相加。轻量证据artifacts/native-progress-display-gui-20261015.xml、native-progress-display-rest-20261015.xml、native-progress-display-core-20261015.xml，不保证随Git迁移。

两次单进程全量在Qt阶段提前退出，未得到正常测试结果，不宣称单进程全量通过。样例检查证明字段、文本和布局配置，不证明现场字体/绘制效果；未启动CST，未猜测原生局部计数与算法内部完成度的对应关系。临时原生文件清理后需重生成。

另每秒观察同目录 output.txt，提取求解设置、线程数、估计频率、Pass 模态频率和 Accuracy、细化计数及成功/警告/错误消息。保存 output-observed.txt 原始副本与 solver-output.json 最新结构化观察，结束时额外刷新一次。未知内容保留在原始副本，不将 Accuracy 当成网格间频率变化，不将 solver_success_observed 当作任务成功。Model.log 尚未接入；Completion/Ack 仍是完成判据。

限制：文件没有协议 task_id，因此绑定是按串行提交时间观察推断，无法证明迟到内容属于当前任务；轮询可能遗漏 0.2 秒以内被覆盖的状态，不能声称收集了所有阶段。文件更新间隔和实际时效性仍需真实 CST 验证。
