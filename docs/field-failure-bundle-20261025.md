# 261012现场诊断包：迭代耗尽与退出1阻断

2026-10-25。用户提供261012-failure-20261025-165144-470850.zip（283735字节），仅只读分析。包SHA256=89b83b803e002363c9e39ff0925eb9fd97dea4bbcc141498a92466a594d57aef。原包及分析保存artifacts/failure-bundle-261012-20261025-165144，artifacts不保证随Git迁移。没有启动CST、操作远端F:或修改求解/关闭接受策略。

## 身份与完整性

当前run=75e271b181544d3b915bd9f4ef840eed，session=ccb45284-e0c2-4870-9fdc-f979cf2cf890，task=89b3da87-f376-43f7-97c1-efe00f65f334。manifest全部included文件捕获SHA256核对一致；实际close.receipt用现有v2 codec解析成功，StopAck用v1 codec核对session成功，并核对close-verification内可在包中取得的证据文件SHA。模型/恢复快照按导出策略未包含，无法在当前主机独立复核其内容/大小/哈希，只能引用现场Python的核验记录，不将包内历史进程信息冒充16:51之后的实时进程探测。

## 已确认事实

- 当前区间1165.8231853449101–1215.8231853449101MHz，nmodes=1；确认覆盖1165.8231853449101MHz、计算上界1215.17243800861MHz、模式188。
- 15:29:33进入Solver.Start，16:20:02返回0，调用3029秒（50分29秒）。原生output.txt明确最大迭代次数耗尽；后续模板后处理自动回答Yes取消。不能据此将区间判空或推进确认覆盖。
- 任务撤销requested=3/changed=2，仅fmin/fmax；原表达式分别1165.17243800861/1215.17243800861，nmodes未变跳过。16:20:02–16:20:07批量恢复2项，删除0项，表达式核对通过。
- Rebuild 16:20:07–16:20:51约44秒，Backup18秒，Save6秒；16:21:16发布恢复回执/StopAck并batch-return。原生收尾共74秒，没有重放Solver。
- 现场Python于16:21:43确认process_state=exited、exit_code=1、model_state=restored-saved，唯一missing_evidence为exit-code-not-accepted；首次stop耗时101.84秒，未达到600秒期限。第二次检查约5秒后同样拒绝；不是又等600秒。
- 回执task_outcome=failure、close_outcome/model_state=restored-saved、snapshot_ref=worker-input.cst.recovered.cst、声明1731526字节、error_code=none。任务失败与模型保存分别表达，不能将保存成功改为求解成功。
- 因关闭门禁拒绝退出1，Manager取消替换。因此本次没有实际执行失败后的processed.cst重试，不能把未替换解读为基准来源逻辑仍错误。
- 同包前次run=9bd87a99的38a9232e会话同样发生迭代耗尽、恢复成功、退出1；两个启动后未执行任务的会话退出0。这支持求解失败可能影响批执行聚合退出码的推测，不等于所有退出1都是安全退出，仍需同版本受控失败对照。
- 最高private约60.7GB（约56.5GiB），不足以证明OOM/泄漏；直接报错是迭代上限。短边比/曲率/关闭自适应警告仍不证明数值根因。

## 状态展示缺口与下一步

control/status.json为RECOVERY_REQUIRED、session_safety=exited-unverified，但error/error_diagnostic/cleanup_diagnostic/recovery_reason为空；实际lifecycle及日志保留exit-code-not-accepted。说明顶层未给出阻断原因，不能向用户显示为无异常。当前Runner._execute对ScanInterrupted清空error及成功返回仍需恢复的分支均需审计，不能未经调用链证据断言只走了哪条分支。

后续应分别处理：求解不收敛的物理/数值恢复策略；有合法回执/StopAck、快照实核且进程/后代已死时的失败收尾分类；顶层原因传播。不得全局把退出1加入成功白名单，不得因为反复恢复就自动重算同一区间或推进覆盖。包本次已足够定位上述问题，无需重复向用户索取同份output/receipt；快照独立复核和受控对照仍是剩余边界。

此为现场证据分析，不是新生产策略验收。新恢复优化只写2项并在5秒完成已得到实际用户模型补证，但不同模型/运行不计算固定提速倍数。

本轮文档/日志索引3 passed（0.62s），仅证明映射有效；原包捕获文件SHA全部通过，最新回执/StopAck codec和可取得收尾证据哈希已直接核验。pytest临时目录已清理，无代码策略修改、未提交。

2026-10-25后续实现：[Mesh/扩窗/窄窗恢复](hom-solver-failure-recovery.md)。HOM默认恢复、正常任务不重复写cell，checkpoint v4读取旧v3；退出1仅可在严格已结束/恢复保存及协议证据齐全时按非标准失败退役，不改为标准成功，旧现场分析“仅拒绝/待实现”为历史状态。实际真实CST门禁仍以新文pending为准。
