# 原生执行采集、RunStore绑定与B4副本验收

2026-11-02。共用实现`csttool/native_execution_capture.py`、`RunStore.prepare_execution_attempt/finalize_execution_attempt`；依赖[B3验证内核](execution-snapshot-verification.md)。不新建Worker或调度框架，不在MCP中另建采集层。

[公共single-simulation](single-simulation-service.md)已接入Managed单次采集，definition_revision贯穿公共定义，configuration_digest独立核对；默认生产G03显式验证后才能执行。新组合真实正常链已通过[G04](single-simulation-g04-acceptance.md)。HOM/standard默认不启用此采集选项。

## 执行所有者的接入顺序

1. 所有者持有现有项目单写权限，调用prepare_execution_attempt冻结源码CST hash、明确配置、批准的设置历史、project/run/task、模型副本路径和安装指纹。候选初始字节必须与冻结来源一致；setup_history只是所有者批准计划的记录，不是接收任意用户VBA的工具。独立采集未传公共revision时保留配置摘要；公共单次已传入已发布definition_revision，并另存configuration_digest，不把两个身份混用。
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

原生post采集在Start返回后、后处理/恢复前；observed_at记录所有者在关闭后收取证据的UTC时间，不声称VBA写出了UTC。数据库须从该明确新生attempt采集，不能仅补改revision/nonce包装旧Model.db。缺帧保持未确认，不重新计算。Managed在显式execution_config选项下集成该链；公共single-simulation通过此选项采集并由finalize_execution_capture归档。HOM/standard默认不启用；B4工具是另一受控消费者，不是唯一消费者。

result_success在本采集回执中特指Start=1且实际模式数>0的求解事实；不代表R/Q、所有产物、结果采用或安全收尾总成功。process_exit_code、batch_exit_zero、exit_confirmed、database_verified分别记录，不将退出0命名为standard_closed，也不把失败退出1改写为正常退出。publish_ready始终false。

## 验收与当前接入

该模块已由[公共single-simulation服务](single-simulation-service.md)复用；生产G03及新Managed组合真实子链见[G04记录](single-simulation-g04-acceptance.md)。模块本身的静态/快照报告不单独证明live设置、求解、结果或退出。未知编码/历史及未校准组合继续保守拒绝。

原批次离线数字、故障修正、B4正常/失败/旧库副本及清理记录完整移至[历史验收](archive/20261102-progress-consolidation/native-execution-capture.md)。旧not-run/下一步只在原批次成立；当前未完成项查[TODO](minimal-python-vba-todo.md)。
