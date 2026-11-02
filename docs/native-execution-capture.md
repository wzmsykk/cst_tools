# 原生执行采集、RunStore绑定与B4副本验收

2026-11-02。共用实现`csttool/native_execution_capture.py`、`RunStore.prepare_execution_attempt/finalize_execution_attempt`；依赖[B3验证内核](execution-snapshot-verification.md)。不新建Worker或调度框架，不在MCP中另建采集层。

后续服务接入：[公共single-simulation](single-simulation-service.md)现可显式配置Managed单次采集，definition_revision直接沿用公共定义，另存configuration_digest。默认G03原生验证端口未注册，普通候选仍不可执行；HOM/standard保持关闭本采集选项。下文“当前消费者仅B4/公共服务待实施”是较早批次状态；本轮新组合只有离线/假对端证据，没有追加真实CST验收。

## 执行所有者的接入顺序

1. 所有者持有现有项目单写权限，调用prepare_execution_attempt冻结源码CST hash、明确配置、批准的设置历史、project/run/task、模型副本路径和安装指纹。候选初始字节必须与冻结来源一致；setup_history只是所有者批准计划的记录，不是接收任意用户VBA的工具。定义revision为来源hash、配置及批准历史的稳定摘要，尚不是MCP公共定义服务的发布事务。
2. intent写入现有RunStore任务下execution/intent.json，并生成独立nonce；重复相同准备返回原记录，冲突拒绝。RunStore任务只记录submitted，不伪造received/ACK/algorithm_adopted。
3. 现有已加载工程Model.run合入render_capture_runtime生成的固定辅助函数。主宏仍由执行所有者控制，按CaptureBeforeSolver→真实EigenmodeSolver.Start→CaptureAfterSolver执行；辅助函数没有Main、Start、OpenFile、Save或Quit，不启动第二套执行链。
4. 原生先输出完整pre帧，再检查工程路径、2022版本、HF Eigenmode、mm/MHz，以及六个数据库key全部明确MISSING。任何已有值或未知读取错误均在Start前拒绝。仅已实测的错误号及完整missing消息可认作不存在，不能将任意异常吞成missing。
5. 同nonce记录started和post帧。post保存实际Start返回、实际模式数及六个固定key；与configured Modes区分。帧有CSTEXEC1/end标记，拒绝缺尾、重复key、错误阶段、身份/nonce不一致。阶段间精确版本等元数据须一致。
6. 等既有进程归属门禁确认该模型的归属进程均退出，所有者才调用finalize。安装指纹须与本attempt冻结时相同，Model.db在64MiB预算内复制为独立归档并双hash核对原件/归档。大文件hash及写入不占RunStore锁，发布及索引短事务才加锁。
7. snapshot先写、receipt后写、artifacts索引最后写；重复对账验证既有产物、不覆盖冲突。不调用Start、不重复写task事件；snapshot已写/receipt未写可补发，receipt已写/索引缺失可补索引。配置匹配并不采用仿真结果。

prepare会核对安装中launcher和AMD64/modeler_AMD64.exe并记录SHA256；不是从任意运行窗口连接工程。关闭证明由执行所有者提供，不是开放给MCP调用方的自报布尔；当前验收使用既有wait_probe的PID+创建时间、子进程及精确task-project归属。库不独自构建操作系统级信任或跨控制器文件锁。

## 2022大版本兼容决定

按本次用户决定，2022各小版本/补丁按同一套行为规则处理，profile改为cst-2022-root-tet-g6-v1。不因未知补丁号或新安装的二进制hash单独拒绝；非2022、其他scope/mesh/未校准Modes等边界仍保留。绑定中的精确cst_build继续核对，不能拿2022.0的旧attempt替代2022.5的当前attempt。

原生GetApplicationVersion实测返回`Version 2022.5 - Jun 03 2022`，不是既有长build标签。对已知原modeler hash，短显示串可映射既有完整build身份；其他2022安装保留原生版本串，不猜change号。每次均保留launcher/modeler hash。若安装在同一次attempt冻结后发生变化仍拒绝，这是证据稳定性检查，不是小版本兼容限制。

该兼容范围来自用户工程决策；真实验收仅本机2022.5。未将其他2022安装写成已实测。

## 原生与持久边界

GetProjectPath("Project")官方返回工程计算目录（无.cst后缀），不是工程文件名；比较必须按该语义。GetOwnProject.GetDataBaseValue仅使用固定objdata/EigenmodeParameter六个key，不遍历数据库，不把私有Model.db读成通用格式。

WWB Print当前使用宿主编码，本首版只接受ASCII采集目录/模型路径；不将未知ANSI误当UTF-8身份。需要非ASCII路径时须新增明确编码通道。帧64KiB、intent批准历史总32KiB，来源CST 256MiB、归档DB 64MiB；超限拒绝。

原生post采集在Start返回后、后处理/恢复前；observed_at记录所有者在关闭后收取证据的UTC时间，不声称VBA写出了UTC。数据库须从该明确新生attempt采集，不能仅补改revision/nonce包装旧Model.db。缺帧保持未确认，不重新计算。默认Managed/HOM生产路径尚未自动调用此可选采集链；当前消费者为B4受控单次执行工具，公共single-simulation服务接入仍待实施。

result_success在本采集回执中特指Start=1且实际模式数>0的求解事实；不代表R/Q、所有产物、结果采用或安全收尾总成功。process_exit_code、batch_exit_zero、exit_confirmed、database_verified分别记录，不将退出0命名为standard_closed，也不把失败退出1改写为正常退出。publish_ready始终false。

## 本轮真实副本证据

工具：[validate_execution_capture.py](../test/support/validate_execution_capture.py)。只复制model/Pillbox.cst，cell near/far=4/4、box=2/1、nmodes=1、2线程、关闭外部Q与热损耗，参数表达式不改固定值。source hash逐次核对，只有本轮受控副本写设置历史。求解阶段无固定总超时，启动/退出有界；不强杀或操作其他实例。

|用例/目录后缀|实际行为|结论|
|---|---|---|
|正常/a093f33b|Start=1、实际1模式，约503.4633MHz；配置match，DB源/归档hash一致；Save/batch-return，归属进程退出0|原生采集与RunStore两次对账一致，表达式保持|
|旧库/5fb2741d|完整结果副本pre六项均存在；在Start前抛明确拒绝，无started/post|不把旧库重新标注为新attempt；0次求解调用，归属进程退出0|
|实际求解失败/9e07a24a|禁用target，Start=0、实际0模式；原生日志最大迭代耗尽，配置仍match；归属进程退出1|求解失败与配置匹配独立，表达式保持；不当空频段、不视标准退出|

运行根前缀为artifacts/execution-capture-normal-、execution-capture-preexisting-及execution-capture-solver-failure-。成功和失败回执均保留在logs/run/tasks/<task>/execution；原生帧、CST日志、stage、session/源检查在各根。人工删除两次artifacts.json再调用当前finalize，回执SHA与events.jsonl字节均未变，索引补回；证据artifacts/execution-capture-b4-summary-20261102/reconcile-gap.json，不重复求解或采用结果。

前置问题也保留：受限环境首轮新宏921e2363与旧无求解宏51c79610均在宏前退出5；相同旧宏在非受限环境893146be正常退出0。支持“与启动执行环境有关”，尚未定位具体受限权限；不能泛称退出5都是此原因。随后新宏1ed27301因版本显示串与完整build直接比较而在Start前拒绝，归属退出0，修正显式身份解释后才运行正常/失败副本。

2022大版本策略修改后另用旧库副本ca3f5462验证最终WinWrap辅助函数编译/门禁，预期不求解。具体最终结果、离线回归及清理范围由当前状态和下方补记记录；这些过程不等于G01–G08完整MCP验收。

最终补记：ca3f5462明确以preexisting拒绝，无started/post，归属退出0。共8次串行会话均确认归属退出，只有2次实际求解（一次成功、一次最大迭代失败）；没有强杀。完整矩阵`artifacts/execution-capture-b4-summary-20261102/acceptance-matrix.json`，两次真实索引补写见reconcile-gap.json。当前代码对原真实回执重复对账未改变回执hash或事件字节；在清理后再用B3读取归档DB，正常/失败配置均仍match且结果状态保持独立，见archive-readback-after-cleanup.json。

最终离线288 passed（10.00s），报告artifacts/b4-final-20261102.xml，覆盖采集/RunStore、检查点采用、B1–B3、原校准安全和文档索引。早期一次测试因helper名setup被pytest当作模块setup执行而12项错误，改名后重跑；不算生产故障或通过数。各轮数字重叠不累加。

已核对进程身份及路径，清理20个模型/结果目标及8个本轮pytest目录，保留原字节历史/参数、宏、帧、原生日志、轻量DB和RunStore记录；cleanup.json记录明确删除目标。原model/Pillbox.cst hash不变；原始副本/场不再存在，重开须重生成，不能继续使用旧运行路径finalize；已归档证据可独立只读核验。artifact不保证随Git迁移。本轮未提交或推送。

## 测试与剩余工作

[故障测试](../test/native_execution_capture_test.py)覆盖意图幂等/冲突、身份/nonce、旧库、退出未确认、snapshot/receipt冲突、发布中断及补写、定义hash和预算、同attempt安装变化。B3另增加2022小版本规则复用与精确绑定仍不互换的用例。既有RunStore/检查点采用回归保持。

B4本轮范围是采集/绑定/故障与关闭事实，不是首阶段完整历史投影发布、从空工程建模、原生Save/Rebuild所有陈旧性组合或GUI/MCP宿主验收。没有迁移普通Manager/Worker的ACK、结果采用或退出状态机。后续将本入口接入公共single-simulation执行所有者，并补完整定义服务、候选发布/重开和B4余项，G03仍未解锁。
