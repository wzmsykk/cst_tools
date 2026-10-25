# 现场原生日志对照：Start=0、慢参数恢复与退出1

2026-10-25。会话110caff3-2113-49c3-8e95-79bde944091d，运行018cc7916f2e4b9aacdaf8330af874c5。此记录补充[第一轮诊断和局部修正](solver-failure-stop-idempotency-20261025.md)。本轮只读取用户文件、当前实现和CST离线帮助，没有启动求解或操作现场进程。

## 已取得的证据

Desktop三文件现已读取：diagnostics.json=49027字节、lifecycle.log=2183字节、cst.log=3360字节。context及日志路径匹配该会话，配置含203个参数、CST 2022.5。用户提供的文件按原样保存在artifacts/solver-failure-stop-20261025/native-*，native-analysis.json记录SHA256和时间计算；artifacts不保证随Git迁移。

## 收尾不是永久卡住

全部时间为日志本地时间UTC+8：

|时点|原生事实|间隔/含义|
|---|---|---|
|10:40:39|调用EigenmodeSolver.Start|已进入求解，不是前处理/后处理报错|
|11:34:52|returned=0，随后ACK任务清理|Start调用3253秒，即54分13秒；不是正常返回1后被Python误报|
|11:36:52|Python第一轮120秒关闭未确认|此时原生恢复仍未记录完成|
|11:38:52|Python第二轮120秒关闭未确认|不能据此证明之后不会完成|
|11:40:08|恢复表达式并移除新增参数完成|距ACK清理316秒；是最大可定位的收尾耗时区间|
|11:40:08–11:41:04|recovery-rebuild begin→returned True|56秒；明确no Solver replay|
|11:41:04–11:41:25|重建返回→Save开始|21秒；源码之间含Backup，但无Backup起止trace，不能精确独立计时|
|11:41:25–11:41:32|Save begin→returned|7秒；本例不是永久卡在Save|
|11:41:32|batch-return|距Start返回400秒（6分40秒），比第二次Python期限晚160秒|

“ACK清理→参数恢复完成”区间没有恢复入口/逐项计时，不能将316秒全部精确归到每个StoreParameter；但源码紧接ACK后进入收尾，并逐个无条件重写203个参数，与该耗时高度一致。不能把这一段笼统称为通信失败或Saved工程丢失。

最后batch-return trace在VBA close.receipt writer、条件StopAck writer及stopped marker之后；按当前源码路径，这些调用没有走失败分支。仍需读取实际回执/文件/哈希和进程退出观测后，才能判定收尾证据合法，不将一行trace替代协议核验。

## 两个分开的失败维度

1. **实际求解失败已确认**。lifecycle明确returned=0，和[CST EigenmodeSolver帮助](../knowledge-base/vendor/cst-2022-vba-help/VBA_3D/special_vbasolver/special_vbasolver_eigenmodesolver_object.htm)的失败返回定义一致。cst.log只有启动/许可/百分比输出，没有失败的内部原因；不能确认不收敛、内存不足、模型设置还是外部取消。许可证启动检查通过也不能证明整个后续求解没有任何许可事件。
2. **CST收尾后来完成，但进程码仍1**。cst.log末尾同时有Batch run finished successfully和EXITCODE_FAILED。没有直接异常栈或崩溃码，不能将它叫作已证明的崩溃；也不能仅凭batch文字把退出1视为标准成功。求解失败是否使进程聚合返回1是待对照的推测；现行0/严格恢复4规则不放宽。

任务原先耗时3313.6秒包含进入Start之前的准备，不等于Start自身3253秒；两种计时不矛盾。peak_private_bytes约56.6GiB不足以确认OOM或泄漏，未提供主机总内存/可用内存及采样趋势。当前任务未到复杂后处理，不能把R/Q的x轴设置当此次Start=0的原因。

diagnostics中的参数列表带fmin=490/fmax=510，是构造配置中的参数定义/初始值，不是当前task-context或CST实际求解设置的取证。Python提交任务日志为1165.82–1215.82MHz；不能仅凭diagnostics列表断言实际算了490–510MHz，仍应核对任务快照/output。

## 文档支持的修正方向（本轮未实施）

- **参数恢复批量化**：当前CSTPMW_RestoreGoodParameters对所有参数调用StoreParameter，即使未变。CST 2022 [Project Object帮助](../knowledge-base/vendor/cst-2022-vba-help/VBA_3D/common_vbaapp/common_vbaappapplication_object.htm)明确提供StoreParameters(names, values)，说明大量参数比逐个循环可明显更快，允许表达式相互依赖。应传原表达式字符串数组，保留参数删除和随后Rebuild，不把表达式求值成常数。现有goodParameter数组ReDim(count)多一个空尾项，不能直接把整数组传入，须按实际count组装并覆盖零参数边界。仍需WinWrap编译和CST副本实测。
- **补阶段开始/完成**：恢复入口、批量写入、删除新增参数、Backup、回执/StopAck发布均记录开始/返回及计数，必要时记录有限进度。让后续区分正在恢复与无响应，不用反复重启试错。
- **一会话一次有界收尾预算**：本例两次120秒均早于400秒收尾完成。按实测大模型配置合理预算并显示阶段，避免Manager替换失败后再无进展地从零重复同一等待；不设正常Solver总时限、不无限等待，也不通过强杀获得成功。不能只改大数字就宣称问题解决。
- **退出1受控对照**：取得合法回执、StopAck、模型哈希和该进程/后代死亡事实，再用串行副本对比成功任务与原生失败任务的退出行为，之后才能决定如何表达“任务失败但模型收尾完成”。当前不更改接受规则。

本地vendor帮助不保证进入源码发布包；应以安装版本对应文档为准。

## 仍需的最小文件

该失败会话worker-input/Result/output.txt；protocol/close.receipt、protocol/stop.ack（若存在）；resource_usage/77a4c346315f40b79d59fbbb0fafc4ea/samples.jsonl。前者定位Start=0，回执解释收尾状态，资源采样判断峰值/持续时间。保留temp和原确认结果，不从头扫描或删除现场证据。

## 后续补证：output与实际回执

同日新增读取Desktop/output.txt（3605字节）与close.receipt（352字节）。原样副本及SHA256保存在artifacts/solver-failure-stop-20261025/native-output.txt、native-close.receipt与native-output-receipt-analysis.json；不保证随Git迁移。以下结论更新前文“求解内部原因未知/回执未取得”的历史状态。

- **直接失败原因已确认**：output明确写出“The eigenmode solver stops due to maximal number of iterations.”，随后Eigenmode solver stops。与原生Start=0一致，是迭代次数耗尽；不是Python总超时或后处理读取失败。日志没有实际迭代计数、残差曲线和上限配置，不能据此确定物理/数值根因或直接提高上限。
- **运行设置得到补证**：估计频率1165.82MHz、复材料求值频率1190.82MHz、nmodes=1、四面体网格、二阶、精度1e-6、考虑损耗、32线程。与任务区间相符，不支持“实际仍算490–510”的猜测。输出没有完整上下频率，不把估计频率当完整区间证据。
- **后处理未继续**：求解失败后询问是否取消后续模板后处理，自动回答Yes；不能把这次失败归因于R/Q积分轴或外部Q结果缺失。
- **数值风险提示**：最短/最长边比1:307499，部分曲率为维持网格质量而降低，自适应网格关闭；还有历史块非ASCII提示。这些是观察到的警告，未证明与迭代耗尽有因果关系。固定网格是项目意图，不能为消除警告而自动开启自适应。
- **回执合法且身份一致**：使用现有decode_close_receipt严格解析，通过字段/枚举/交叉约束，并核对session/task。close_origin=stop-request、task_outcome=failure、close_outcome/model_state=restored-saved、last_completed_phase=save、error_code=none。snapshot_ref=worker-input.cst.recovered.cst，声明1730521字节。说明任务失败与模型收尾成功可同时出现，协议已经分别表达。
- **仍不放宽物理关闭门禁**：本地未取得快照本体及哈希、stop.ack、现场进程/后代退出观测。回执的声明大小未与实际文件核对；合法回执不替代这些核验，也不使退出1自动成为可接受标准退出。收尾耗时400秒与两个120秒等待失配、重复停止发布缺陷仍是独立问题。

后续优先读取迭代残差/求解器设置并做明确授权的串行副本对照，区分网格、估计频率、损耗与迭代上限影响；不能仅凭本例失败把区间判为空或推进已确认覆盖。当前继续需要stop.ack、资源samples和必要快照核验信息；不需再提供这两份已收到文件。本轮未启动CST、未改求解/退出接受规则。

补证验证：现有回执编解码测试及文档索引57 passed（1.27s）；现场回执额外通过decode_close_receipt及指定session/task断言。仅证明文件协议/身份和索引，不证明现场快照或进程已安全退出。

2026-10-25后续实现：[批量恢复与收尾预算](parameter-restore-close-budget.md)。宏批量保留表达式并校验；Worker共用一次600秒期限；失败重试从预处理基准启动，旧副本仍须正常关闭。此前未实施描述为历史分析，真实CST兼容/提速及退出1对照仍pending，关闭证据门禁不变。
