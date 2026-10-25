# 现场失败与重复停止发布

2026-10-25，[完整证据及修正](../docs/solver-failure-stop-idempotency-20261025.md)。来源59条用户JSONL，原始文本只留artifacts/solver-failure-stop-20261025，不保证随Git迁移。

日志中188个已确认采用TaskID续跑通过；新任务约3313.6秒后SOLVER_FAILED，ACK完成并retiring。随后两次120秒关闭均缺StopAck/close.receipt/退出观测，第二层Manager停止发布再次写已有stop.request，抛FileExistsError。

顺序不能颠倒：重复发布错误发生在第一次退出等待失败之后，不是之前CST求解失败/收尾卡住的原因。peak_private_bytes约56.6GiB是观测峰值，不足以确认OOM/泄漏。没有总求解超时触发的证据。

源代码原先在solverReturn<>1时统一写returned 0；仅Python失败消息不能证明真正返回0，必须看lifecycle的returned=行。生产宏修正为CStr(solverReturn)，既有运行宏不热替换；该修改只完成源码契约测试，尚非真实WinWrap验收。

停止请求修正为同session有效既有文件幂等，进程内跨实例按路径短锁串行，不等待任务锁；坏消息/异会话/未完成tmp继续阻断、保留。没有借文件存在宣称CST已关闭，没有改退出码/回执门禁或强杀进程。

现场F:未在本环境挂载；之后给出的Desktop路径经默认和正常权限确认都没有实际文件，附件目录也没有三份原生日志。用户需传实际文件或粘贴内容，路径相同不意味着远程与本机同一个桌面。因此CST失败实际值、恢复Rebuild/Save等卡点仍未确认。

同日后续重读已成功取得三文件，上段为首轮状态：[原生对照](../docs/solver-failure-native-analysis-20261025.md)。lifecycle明确Start=0，ACK后316秒恢复表达式完成、Rebuild56秒、Save7秒、总400秒后batch-return，晚于Python两次120秒退出等待；不再把它视为永久卡Save。CST日志batch成功文字与exit1并存，仍不放行退出1。求解内部原因还缺output.txt，实际回执/StopAck及资源采样亦待补齐。

CST 2022 Project Object本地帮助提供StoreParameters(names, values)，说明批量写参适合大量且相互依赖的表达式，比逐项循环可更快。现行恢复对203项无条件StoreParameter，作为主要耗时区间的优化候选；没有逐项trace，不能精确宣称316秒全部消耗在setter，也未将批量方案冒充已实现/实测。goodParameter数组比count多一空尾项，未来传批量前必须重组精确长度。

同日output/close.receipt补证更新上述缺证状态：原生错误为最大迭代次数耗尽；nmodes=1，估计频率1165.82MHz，后处理自动取消。v2回执严格解析及session/task一致，报告任务failure但模型restored-saved、快照1730521字节；快照大小/哈希未实核，StopAck/现场进程事实仍缺。边比1:307499、曲率降低及自适应关闭是警告，不能直接认定为数值根因；不因此自动开启自适应或接受退出1。详见原生对照新增补证章节。

2026-10-25后续已实施批量参数恢复/阶段诊断及同Worker共享600秒期限，见[实现说明](../docs/parameter-restore-close-budget.md)。与先前仅分析的状态区分，未做真实CST批量性能验收。失败重试输入为预处理基准，安全收尾检查点与HOM确认覆盖分别管理，不能将旧副本恢复快照当作失败后的新输入。

真实Pillbox副本补验：[208项恢复与基准重试](../docs/batch-restore-real-acceptance-20261025.md)。批量StoreParameters原表达式通过，8秒写入、5秒清理新增项、随后文本校验/重建/保存通过，失败按恢复退出4完成，基准重试成功。短预算重复停止不重计，迟到退出0可核验。不是复杂现场203项的同模型性能对比，不推导加速倍数；受限环境许可证-63,403而正常用户成功，且受限进程清单不代表正常用户无进程。清理前同权限核实，原始副本已删，轻量证据不保证随Git迁移。

同日进一步实施并真实验证[任务级撤销](../docs/task-parameter-undo.md)。工程208项、故障请求5项但只改3项，恢复2个原表达式并删1个新增项，成功阶段不再全表捕获；基准重试/快照/关闭门禁通过。实际CStr(Boolean)诊断为-1/0，不能按API名字假定文字True/False。缩小调用范围不等于证明墙钟按比例加速（本轮恢复批返回约21秒）；原始数据清理后需重生成，旧全量记录保留为历史。
