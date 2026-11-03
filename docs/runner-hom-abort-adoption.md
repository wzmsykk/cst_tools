# 生产Runner/HOM中止、恢复与结果采用

更新：2026-11-04；本批基线b580fd5。此页定义本轮生产链验收范围；[此前Worker层中止](public-fault-injection.md#官方中止自动时序探针2026-11-04)不等于上层采用证明。

## 执行链与验收终点

使用真实Runner服务、LocalExecution、应用后端、CSTManager、Managed Worker、HomScanAlgorithm、检查点及RunStore；不另外建立任务控制器。受控父进程通过RunnerClient提交HOM。仅在本轮子Runner里注入官方中止和故障边界，不改变生产取消接口。

首任务以官方abort_solver中止一次；失败Worker正常收尾，生产Manager从processed.cst新建Worker，HOM按既有策略恢复。首个确认模式写入检查点/CSV后采用，然后测试钩子请求Manager正常停止。最终预期是INTERRUPTED、有已确认结果及后续pending，不是扫描目标480–530MHz全部计算完成。这样把协议/采用验收与小网格频率漂移分开；nmodes仍为1，不修改频率判重容差。

继续运行时，测试钩子在重新核对已确认模式的采用后再次请求正常停止，要求不增加实际Solver调用、CSV/模式/覆盖不变。这一有意的提前停止不证明之后所有未算区间可完成；逻辑请求预算可能因落盘后的待执行意图增加，不能当作实际求解次数。

## 故障与恢复矩阵

|场景|注入前必须核实的事实|恢复要求|本批真实状态|
|---|---|---|---|
|baseline|官方中止返回True，替代任务实际成功|采用回执/索引/日志闭合，正常暂停|通过|
|received|成功档案已经形成，尚未进入HOM模式记录，采用事件0|重启对账后按原TaskID接力，不重算，不把收到结果直接当已采用|通过|
|checkpoint|模式检查点已写，receipt/index仍acknowledged，采用事件0|核验后补标记，不改检查点或结果|通过|
|journal|采用事件已追加一次，index/receipt仍acknowledged|补索引及回执，日志不追加第二次|通过|
|receipt|日志和index已采用，receipt仍acknowledged|仅补缺口，多次恢复不改变已齐标记|通过|

只有这四个故障场景结束本轮Python Runner；从不结束其CST子进程/进程树。重启先recover，恢复完成后再resume。原父进程死亡后原生退出码未必可观察，必须保留实际关闭/身份/回执事实，不伪造exit=0。所有实际CST副本串行。

每个成功模式要求原任务ID、后处理值、快照及原生场hash保持；失败TaskID不能进入采用集合。接收时点还核验归档重命名后的索引和snapshot hash。每个有关RunStore内采用事件恰为一次；同一任务恢复后可映射到新的RunStore，不把多个运行各有一次记录误当一次求解被重复导入。

## 实现修正与持久化边界

生产Worker的lifecycle.log位于集中observation_root；独立Worker探针此前默认读临时会话目录。桥接意图现可显式携带lifecycle_path，要求位于artifacts、文件名固定、父目录会话ID匹配；实际abort仍核验原生PID+创建时间+程序、精确工程及is_solver_running。注入未触发/桥接失败时留injection-failed.json，父控制器经Runner正式stop停止后续测试，不把注入错误转换为“实际求解器故障已验”。

恢复采用原来核对HOM任务名与快照，未逐项比对模式频率及后处理值。现validate_hom_mode_receipt在任何采用写入前核验模式号、非空标量值、唯一指标、有限数值、完整指标集合、frequency与接收回执一致。只有已持久接收值才是采用依据，独立求解之间的物理误差不在这里使用容差。

带模式但values为空、值被改动、丢指标或指标歧义的检查点会拒绝恢复；不自动给旧不完整记录编造数值。没有模式记录的合法consumed/probe任务仍按现有任务/成功回执/快照及归属核验，不把这一分支说成模式数值已校验。校验失败保留证据，不重新调用Solver。

还修正了跨运行采用：接力旧receipt时，新RunStore和receipt已采用而原RunStore索引可能仍acknowledged。mark_adopted现在先收集当前运行、原回执祖先运行及该TaskID已有日志索引，只核验这些运行的项目归属后，再幂等补齐各运行日志/索引，最后写receipt；任一写入缺口可继续补齐，不重复追加。外项目运行混入会在任何写入前拒绝。没有新增结果导入或求解步骤。

## 使用与证据

```powershell
python test/support/validate_runner_hom_abort.py --run-cst --case all --cst-exe "D:/Program Files (x86)/CST Studio Suite 2022/CST DESIGN ENVIRONMENT.exe"
```

可单独选择baseline、received、checkpoint、journal、receipt；--child、--project及restart用于本轮内部Runner启动。工具登记不等于执行授权。正常求解不设固定总超时，桥接连接、协议和退出有独立有界等待。测试前检查磁盘，完成并核实退出后清理伴随场/网格目录，保留报告、意图、宏、回执、参数及hash；artifacts不保证随Git迁移。

离线故障测试使用合成接收数据，执行生产扫描器、检查点和采用实现；BaseException模拟控制器清理未执行，不冒充OS进程退出。真实子Runner矩阵另列。Start=0/Start自身异常和模式物理身份、整段扫频完备性均不由本批推定通过。

## 本批实际结果

`artifacts/runner-hom-abort-74a731d9`的baseline/received/checkpoint/journal/receipt五场景全部通过，每例实际Start两次（一次中止、一次恢复），共10次；重复recover及暂停后resume不增加实际求解。结果保持原TaskID，Frequency及Z轴R/Q、CST/原生场hash和已确认覆盖不变。失败任务不进入采用集合，相关RunStore的每个TaskID采用事件均为一次。全部28个Managed会话已核实物理退出且无未收口恢复事项；原父死亡后的退出码仍按实际证据保留unknown，不伪造0。

最终矩阵清理66个可再生成伴随目录，保留轻量报告/宏/参数/回执及hash；先前失败探针也在任务结束后另行清理。原始场需重生成。Git内轻量证据：[本批知识记录](../knowledge-base/runner-hom-abort-adoption-20261104.json)。

99项核心/故障/文档登记回归、98项生产相关回归、47项定位/故障登记/源码包边界检查通过，集合有重叠，不累加。原生期间冻结的生产源码/桥接/驱动hash逐例留档；真实结束后仅修正测试套件汇总状态（中途失败不能把已通过子集报为整个矩阵通过），此元数据失败路径以离线反例验，不改写原生驱动hash为最新字节。

剩余：更长完整频段扫描、生产probe/confirm专属采用故障时点、模式身份/频漂判重和Start=0/自身异常；本页不将它们勾选完成。
