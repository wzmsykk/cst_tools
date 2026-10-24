# P0-1：坏重建后直接停止的参数恢复

2026-10-24 L3：[生产v2时序及保护](production-close-v2-l3.md)新会话实际调用收尾writer；Start=1之后保守保留当前工作副本/结果，不为后处理/快照失败恢复Rebuild；Start=0等改模型失败停止仍走原表达式恢复。退出4旧例外保留、退出1拒绝，以下历史真实Gate不能追认本轮新宏已执行通过。

2026-10-24：[L1统一关闭证据](session-closure-l1.md)现已接入，保留退出4例外且拒绝退出1；StopAck文件存在/旧stopped标记不能证明未知或活跃进程关闭。旧会话缺退出码时可在确认已死后显式放弃，不能凭空记录标准退出；以下历史真实Gate不覆盖本轮新代码。

2026-10-20协议审计补充：[生命周期范围修订](python-vba-lifecycle-protocol-v2-plan.md)。当前退出4例外保持，下文旧Gate只证明其具体case。现场Start=0后恢复重建/Save返回而退出1暴露任务失败与会话收尾判定不充分；不据此放行退出1。StopAck字段、发现与正常停止/显式恢复判定一致性列入L1–L5待办，未实施。

更新日期：2026-10-14。对应功能F03/F04/F09/F16。此前真实nmodes=0导致历史重建失败后立即停止，出现Save拒绝及退出4；不能用进程退出代替安全关闭。

## 实现

Managed VBA在启动和每个成功任务快照发布后捕获完整参数名称与原始表达式；工作副本旁输出`worker-input.cst.last-good-parameters.tsv`用于诊断。任务开始变更参数即标记需要恢复，只有成功完成快照/参数检查点才清除。

失败后直接Stop：恢复最后良好参数表达式→移除该检查点之后新增的任务参数→完整Rebuild→Save→StopAck→返回批执行器。没有Solver重放，原失败Completion/received记录不改成成功，已有成功结果留在独立快照。

恢复、重建或保存失败均不发布成功StopAck；保留诊断并要求会话核对。Python停止要求StopAck及退出核对。退出0按正常路径处理；退出4只有具备本session严格匹配的recovery-saved回执及非空recovered.cst快照才能确认停止，记录WORKER_STOP_RECOVERED警告，不改写失败任务结果。其他非零、缺回执/快照或缺StopAck均拒绝确认。已退出的实例也按同一规则核对。

## 边界

- 检查点只涵盖项目参数及原表达式，不是完整工程事务；不恢复任意历史编辑、边界/网格直接setter、Global Data或外部文件。
- 恢复Rebuild会删除当前副本中的结果；不声称保留失败任务现场的可计算场。已有成功快照不覆盖，恢复动作与失败诊断保留。
- 启动检查点是输入工程参数；输入工程自身无效时恢复仍可能失败。不会无限试错或强杀。
- 参数不进入新的固化历史块；重放既有历史读取已恢复参数。源码入口见[功能索引](feature-index.md)。

## 验收

工具：`test/support/validate_failed_rebuild_stop.py`；默认测试启动后立即坏重建并停止，`--after-success`先成功求解后再坏重建、立即停止。完成后补实际证据，不以静态检查替代CST运行。

首轮`failed-rebuild-stop-ae5729af`证明恢复Rebuild与Save已返回、无保存拒绝，但CST仍退出4，严格退出0门禁失败，记录保留。后续`failed-rebuild-stop-b417feb1`通过恢复快照及回执门禁：StopAck/标准停止返回True，退出4保留，源未变，Solver调用0。该反例说明任务失败退出码与“尚需UI解决的关闭问题”不能混为一谈；不是通用忽略CST退出码。

已有成功任务后的对照：`failed-rebuild-stop-0ea47a64/report.json`通过。先成功求解nmodes=1，再以nmodes=0、Gap=140及新参数触发真实REBUILD_FAILED，立即停止；最后成功参数检查点仍为Gap=150，concaveL=(Leq-Gap)/2、concaveR=concaveL。恢复Rebuild成功，恢复快照及本session回执存在，StopAck与停止返回True，CST退出码4保留；Solver总调用1次，原成功快照SHA未变，源工程未变。最终可靠权限进程核查无CST主实例/Modeler/Solver残留，无强杀。

默认基线探针和成功后失败探针已通过。2026-10-14另补齐恢复Rebuild自身失败、快照及回执写入失败三个pending。任意非参数历史破坏不属于参数恢复机制，不因本次验收宣称能够自动回滚。

离线：最终436 passed、19 deselected（15.34秒）。中间完整测试因新WORKER_STOP_RECOVERED未同步事件索引失败，已同步并通过事件门禁；一次受限os.replace WinError5另行记录，完整提升权限回归通过。功能索引检查路径与Python/VBA符号，不能代替文档内容评审。

## 2026-10-14：pending故障注入完成

工具：[validate_recovery_faults.py](../test/support/validate_recovery_faults.py)。证据根目录：`artifacts/recovery-faults-771c8a0a`，各case/report.json保留完整生命周期和停止错误。

|case|实际注入|观察及验收|
|---|---|---|
|rebuild|仅探针在恢复参数后重新设置nmodes=0，实际调用Rebuild；不伪造返回值|Recovery Rebuild返回False，recovery-rebuild阶段报错，停止拒绝、无StopAck|
|snapshot|在新副本的精确recovered.cst输出路径建立目录，阻止真实Backup写文件|recovery-snapshot阶段10051 Could not open file；无回执、无StopAck|
|receipt|在精确recovery-saved路径建立目录，阻止真实Open For Output|recovery-receipt阶段报错；快照及Save不等于整个停止协议成功，无StopAck|

三项均保留Task Failure、没有成功结果/快照，Solver调用0、源SHA未变，CST标准批执行退出4，无活跃主实例/Modeler/Solver。之后现有recover_project_sessions确认记录进程确已死亡，将会话标记abandoned-dead；不制造StopAck、不把坏副本升级为良好快照，不复用损坏工程。活跃或身份未知的进程不得走此分支（新增离线门禁）。原始阻断目录保留为证据，不清理用户文件。

补强：Backup后FileLen检查恢复快照非空，未满足不发布保存回执/StopAck；非ASCII或损坏恢复回执拒绝退出4停止确认。正常路径回归`failed-rebuild-stop-9bde6833/report.json`通过：保存恢复快照、StopAck、源未变、Solver调用0，退出4仍保留为失败证据。

最新离线441 passed、19 deselected（14.89秒）；三项真实故障及正常回归通过，未强杀。完成的是这组明确pending，不代表Save无返回值的全部错误、任意历史损坏、磁盘满、父进程死亡及跨版本矩阵全部验收。工具是测试专用，生产不提供故障开关。变更未提交。
