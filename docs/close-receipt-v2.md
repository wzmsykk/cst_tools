# L2：Python/VBA收尾回执v2

后续L5已真实运行四组WinWrap codec及部分生产故障矩阵，并增加固定.closed.cst token；见[验收与升级要求](close-v2-l5-acceptance.md)。以下未真实运行描述保留L2历史边界，不覆盖本轮证据。

日期：2026-10-24。状态：两端codec、静态声明、原子/幂等发布、读取门禁与隔离契约宏已实现；**没有默认启用生产v2，也没有执行真实WinWrap/CST验收**。Task/Completion/ACK/Stop v1不变，退出1不放行。L3的状态采集、retiring及生产CloseSession调用顺序仍待实现。

同日后续[L3](production-close-v2-l3.md)已接入生产生成器与CloseSession实际writer：新会话改为v2，旧会话不变，仍没有真实WinWrap/CST验收。本文“生产v1/待L3”为L2完成时边界，当前状态以L3专页为准。pending回执与有效failed回执的运行期处置、最后接收任务身份也已在L3细化。

## 1. 冻结的消息

位置：会话根目录下`protocol/close.receipt`。magic为`CST_CLOSE_RECEIPT_V2`；之后10个键/值双行，编码ASCII、无BOM，LF/CRLF兼容，最终换行；总帧不超过4096字节。未知字段、重复键、缺字段、截断、非法枚举及不一致字段均拒绝，不因解码失败重试有副作用操作。

|顺序|字段|约束|
|---|---|---|
|1|session_id|规范小写UUID；匹配静态声明/工作空间|
|2|last_task_id|规范小写UUID或none；启动无任务用none|
|3|close_origin|stop-request / worker-failure|
|4|task_outcome|not-started / success / failure / cancelled / unknown|
|5|close_outcome|saved / restored-saved / failed|
|6|model_state|prepared / committed / dirty / restored-saved / restore-failed / unknown|
|7|last_completed_phase|none / restore / rebuild / backup / save / receipt|
|8|snapshot_ref|none / worker-input.cst / worker-input.cst.recovered.cst / worker-input.cst.closed.cst；不接收任意路径|
|9|snapshot_bytes|规范非负十进制int64（0到9223372036854775807），无符号/前导零/小数；VBA用String承载避免Long溢出或浮点舍入|
|10|error_code|none或下述稳定错误码|

错误码：CLOSE_RESTORE_FAILED、CLOSE_REBUILD_FAILED、CLOSE_BACKUP_FAILED、CLOSE_SAVE_FAILED、CLOSE_RECEIPT_FAILED、CLOSE_PROTOCOL_ERROR、CLOSE_INTERNAL_ERROR。长文本与本地化错误留在日志，不进入此信封。

关联约束：

- none任务只允许not-started/unknown；已知UUID不能声明not-started。任务unknown不代表成功。
- 无快照必须none/0；声明路径必须大小大于0。failed可以保留已有快照信息，但不因此变成成功。
- saved只允许prepared/committed及worker-input.cst或worker-input.cst.closed.cst；新生产宏使用后者独立Backup。restored-saved要求同名模型状态及恢复快照。L5实际发现活动工程在Save后仍变化，修订与两端升级要求见[真实验收](close-v2-l5-acceptance.md)。
- 正向收尾必须完成到save或receipt、快照非空且error_code=none；failed必须携带非none错误码。
- VBA不能填写进程退出码。回执证明宏的声明，不证明CST已退出或结果已被扫描器采用。后续producer仍需遵循Save→回执→合法StopAck→批返回顺序，不能将L2 codec成功当成此顺序已实现。

## 2. 静态版本与兼容

`close-protocol.json`只含schema_version=1、session_id、close_protocol(v1/v2)。创建新工作空间时一次声明，重复相同声明幂等；更改版本/会话或非法原文件明确拒绝，不能热切换活跃宏。

- 新生产Managed生成器显式声明v1，与当前旧宏一致；没有GUI或WorkerConfig里的v2开关。
- 专用契约生成器声明v2，并把v2常量、两份库和唯一Main编译进同一宏；不是动态协商。
- 旧目录没有声明也没有v2回执时可按legacy v1读取；孤立v2回执与v1声明冲突均拒绝。
- 调用方已知v2时必须传expected_version/expected_close_protocol=v2：声明缺失也不能降级。仅靠遗留磁盘目录无法判断“原本旧v1”和“声明、回执都被删除的v2”；未来L3生产启用必须绑定已知期望版本，不能把磁盘猜测当防篡改保证。
- 声明v2后，缺失/损坏回执、串session/task、快照缺失/大小变化或越界路径都不能用旧StopAck＋退出0绕过。现有L1发现/恢复入口已接入此阻断，保留原证据；没有自动退回v1或自动放弃损坏v2的分支。

## 3. Python API与文件语义

实现：[close_receipt.py](../csttool/close_receipt.py)。

- `CloseReceipt(...)`：构造时验证UUID、枚举、大小与字段关联；`encode_close_receipt`/`decode_close_receipt`处理wire格式。
- `declare_close_protocol(root, session_id, version)`：在生成/启动前原子发布静态JSON；`read_close_protocol(..., expected_version=...)`严格读取，包括拒绝JSON重复键/未知字段及bool冒充schema整数。
- `publish_close_receipt(root, receipt)`：要求已声明v2，`.tmp→final`原子发布；同语义原文件幂等返回，冲突、损坏原件或未完成tmp拒绝，不覆盖/删除。
- Python提交阶段不能使用会覆盖目标的replace：Windows使用不覆盖目标的rename，POSIX使用link建立最终文件后移除自己已提交的tmp；不支持该操作时明确失败，不回退覆盖。8线程冲突测试确认只有一个不同回执能成为最终文件；未成功提交的临时证据不自动清理。v1原有发布器本轮不变。
- `read_close_receipt(root, session_id, expected_task_id=..., validate_snapshot=True)`：严格v2读取；校验指定身份及工作空间内固定路径/文件大小。参数validate_snapshot=False只适合codec检查，不是关闭确认。
- `session_closure.read_stop_evidence`：v2声明时附加上述核验，使用task-context核对最后task及合法停止请求；有效failed回执可单独读取，但当前L1门禁仍要求恢复，失败分类/自主退出的完整处置留待L3–L4。
- Python退出观测摘要现在绑定静态声明、v2回执及固定快照的哈希；篡改同大小快照也会使保存的退出证明失效。它不提供对恶意修改整套工作空间的认证。

退出规则保持L1：v2恢复回执不能替代旧退出4例外所需的recovery-saved凭据；退出1仍为异常。当前L1任务/模型字段完整采集未扩展，不把v2库的存在宣称为L4已完成。

## 4. VBA API与契约宏

实现：[runtime_close_receipt_v2.vb](../data/runtime_close_receipt_v2.vb)。必须拼接在runtime_protocol_v1.vb之后、同一模块内，复用私有字段解析/原子写入函数；不能作为另一个独立模块调用这些私有函数。

- `CSTC2_CloseReceipt` UDT；`SnapshotBytes As String`。
- `CSTC2_ReadCloseReceipt(path, expectedSessionId, expectedTaskId, receipt, errorMessage)`。
- `CSTC2_WriteCloseReceipt(path, receipt, errorMessage)`：先校验，存在原件时完整读取比较，同值幂等、冲突失败；新文件复用CSTP_AtomicWrite，不删除tmp或覆盖最终文件。VBA单线程producer，不承诺多producer竞争发布的额外重试。

[close_receipt_contract.py](../csttool/close_receipt_contract.py)提供`prepare_close_receipt_contract`：只使用新/空目录，生成静态v2声明、golden输入、微型快照夹具和宏，不运行CST、不打开用户模型。宏执行读→写→同值重写→冲突必须拒绝→读回确认→发布contract-passed.txt；没有Solver/Rebuild/Save/Quit调用。

`verify_close_receipt_contract`要求匹配回执和最终成功标记，但只验证codec产物；真实调用方还必须确认CST进程标准退出，不能只看标记、文件或退出0。

## 5. 验收与剩余TODO

固定向量：[saved](../test/data/close_receipt_v2/saved.txt)、[restored](../test/data/close_receipt_v2/restored.txt)、[failed](../test/data/close_receipt_v2/failed.txt)、[startup](../test/data/close_receipt_v2/startup.txt)。

测试：[close_receipt_test.py](../test/close_receipt_test.py)覆盖四种golden、LF/CRLF、截断/重复/未知字段、大小边界、字段关联、静态版本冲突、缺回执不降级、任务/快照匹配、幂等/冲突/tmp保留、隔离宏生成及Python产物核验；VBA部分是字段/枚举/源码顺序检查，不是WWB解释器运行。

未完成：L3生产宏采集实际状态并调用writer，L4完整生命周期传播和失败/自主关闭处置，L5真实WinWrap codec Gate和CST串行副本故障矩阵。不得据此自动启用生产v2或把用户现场退出1解释为安全关闭。真实VBA验证将包含int64字符串、UDT和私有库拼接兼容性；目前不能声称已编译/运行通过。

最新测试数字见当前状态，轻量报告在artifacts，不保证随Git迁移；本轮pytest临时夹具结束后清理、可重新生成。用户工程与原始场文件未触碰，未启动真实CST。

最终验收：离线695 passed、21 integration deselected（144.78s），主窗口独立34 passed；专项123 passed（3.17s，与前述重叠）。报告artifacts/close-v2-{offline,window,focused}-20261024.xml；生成而未执行的契约工作空间artifacts/close-v2-contract-20261024-startup保留输入、静态声明及宏哈希。8字节worker-input.cst不是有效模型，不能拿它进行求解。最初一次生成测试因非法Windows双引号目录名失败不计通过，修正合法目录测试后上述通过。
