# 恢复与退出链整体审计

2026-11-02。审计对象为当前工作区（1b4afa4加尚未提交的最大化/退出修正），不以旧发布包或旧测试数字代表当前审计。当前批次仅静态分析、最小离线复现和文档同步，未修改运行逻辑、未启动真实CST、未触碰现场F盘。复现摘要：artifacts/recovery-exit-audit-20261102/reproductions.json；不保证随Git迁移。

## 应坚持的用户契约

|操作|应有行为|不应混淆|
|恢复|核实进程/协议、恢复确认结果归属，保留检查点|恢复不自动重新求解|
|继续未完成|从检查点的待算区间继续，保护确认覆盖/结果|不是从最近已找到模式猜起点|
|安全停止计算|保存停止意图，CST在可响应的边界收尾，结果按证据采用|点击成功不等于求解已立即退出|
|停止恢复|在安全边界暂停扫描/对账，保留可再次恢复状态|不能强杀CST，也不应接受无效停止|
|完整退出|停止活跃执行，核实物理退出，再退出Runner与GUI|逻辑待恢复不等于有活进程|
|仅关界面|释放本地资源及控制租约，后台原状态保留|目录可能仍被Runner/控制台占用|

至少区分四条事实轴：计算结果、CST物理安全、结果采用/检查点一致性、Runner/GUI存活。现有实现已分开不少事实，但GUI操作门禁仍将多个轴合并进has_active_work，造成以下问题。

## 发现与修复优先级（A01–A08）

### A01 / P1：待确认停止意图会绕过新的安全退出路径

源码：GUI/runner_controller.py:65、192、278。stop_after_start=True被has_active_work视为活跃执行；自动cancel_start又跳过RECOVERY_REQUIRED/RECOVERING状态，request_shutdown因has_active_work直接False。即使物理会话已经退出，新的服务端检查也没有机会运行。

离线复现：控制器RECOVERY_REQUIRED、stop_after_start=True、pending=False、unknown=False时has_active_work=True、shutdown_dispatched=False、客户端ops为空。不是已确认现场根因。应将传输在途、待协调意图和实际执行拆开；允许幂等协调停止意图，然后把最终退出决定交给Runner。不能靠删pending-ui-stop.json绕过。

### A02 / P1：恢复和退出的重型核验可阻塞控制通道

源码：project_session_recovery._owned_alive/discover_managed_sessions/recover_project_sessions，session_closure.read_recorded_exit/_proof_hashes，runner.Runner.command。discover会在_owned_alive中复验退出hash，构造record时又读一次；每恢复一个session，fresh又全项目discover，末尾再全项目discover。k个待恢复/n个历史会话可达O(k*n)次扫描；核验还会读取模型快照，并非只读小JSON。checkpoint_adoption随后还逐任务计算快照hash。

shutdown的project_lifecycle及这些文件I/O在Runner全局self.lock内执行；status/heartbeat/其他命令也要拿同一锁。慢盘或不可响应文件系统可能使UI显示连接未知，并非只有CST本体卡住。此处为静态确定调用关系，未做网络盘耗时基准。

应按本轮操作建立可失效的来源快照/索引，单会话复查不重新扫描全部历史；重型I/O移出控制锁，提交前再核验操作代次/归属和关键证据。不能简单永久缓存hash或取消完整性门禁。

### A03 / P1：多个未完成意图没有一次性对账收口

源码：runner.py初始化commands枚举（约109行），_execute末尾仅为status.run_id写outcome（约414行）。初始化逐个遇到无outcome的start就覆盖当前run_id；恢复只为当前run_id写终态。

离线实际执行：两个人工历史意图run-a/run-b，首次选择run-b；恢复显示IDLE，仅run-b有outcome；重新创建Runner又以run-a进入RECOVERY_REQUIRED。没有求解或导入。这是不符合“一次恢复完成”的行为，也使显示run与真实待恢复集合混淆。

应显式登记全部未收口意图，按原run身份逐一核对，写reconciled/cancelled/failed等符合证据的终态；恢复作业使用独立操作身份或明确关联集合，不能把恢复完成写成旧计算成功。损坏意图应逐条诊断，不依赖目录枚举顺序。

### A04 / P1：恢复中的停止请求没有被恢复循环消费

源码：runner._stop_run可在RECOVERING接受stop并改STOPPING；LocalExecution.request_stop→Backend.request_stop写stop_intent。恢复Backend无Manager时直接返回；project_session_recovery、managed_session_recovery和checkpoint_adoption没有消费该stop_intent。

GUI在RECOVERING禁用StopButton；若CLI等入口提交stop，则可能显示正在停止，但会话等待/全量对账继续；每会话1200秒从恢复开始计时，不能区别CST仍在正常求解与协议卡住。完整退出在RECOVERING又选择继续等待，因此用户只有detach能脱身。此为静态分支结论，未进行真实CST故障触发。

应定义恢复的安全暂停点及已执行副作用，协议已发布ACK/stop时不能半途伪造收尾；纯校验/对账可在安全边界取消。不能提供看似成功但不生效的stop。正常求解与通信/收尾应分别计时。

### A05 / P2：后台已退出时仍先要求连接成功

源码：runner_client.shutdown_and_wait:116。先connect(launch=False)，之后才进入所有权释放检查。离线模拟已退出运输层报错时直接OSError返回，所有权探测尚未发生。保留陈旧连接的GUI可能不能确认后台已经离线。

应先区分已离线/同实例仍在线/归属不明；连接失败后以OS锁及instance/process证据对账，不启动新Runner来完成退出。Runner离线与CST物理安全仍分别展示，不能仅因锁释放就宣布CST正常关闭。

### A06 / P2：业务拒绝被显示成连接未知

源码：runner_client.request将HTTP拒绝转RuntimeError；GUI/runner_controller.py:220把所有future异常设unknown=True，显示“正在重连”。因此服务端明确给出session safety unresolved或控制权拒绝，也会被当成断线。

审计时纠正早先假设：服务端HTTP拒绝不是被shutdown_and_wait吞掉；该函数只捕获OSError/ValueError，HTTPError包装后的RuntimeError会向上传播。真实缺陷是异常分类与GUI状态含义混用。应区分业务拒绝/协议错误/传输失败；保持已知连接事实和原会话原因，只有传输不确定才置unknown。

### A07 / P2：诊断导出可无期限阻止任何窗口关闭

源码：GUI/main_window.py:230。导出线程isRunning就直接拒绝close，连仅关界面也没有出口。导出虽限制字节/候选，文件系统read/stat没有硬耗时上限；因此慢映射盘可能造成“退出又卡在导出”。

应提供明确导出进度/取消或延期关闭的交互，保留线程生命周期安全；在可响应的读写边界取消，不能销毁运行中的QThread，也不能声称能够立即中断不返回的OS调用。

### A08 / P2：恢复按钮名称和计数不反映实际工作

源码：RunnerController.poll把recovery_count赋为int(state==RECOVERY_REQUIRED)，MainWindow.renderState却显示“清理残留会话 (count)”。因此显示1只是一个状态布尔值，不是真实残留CST数量。恢复实际还可能执行检查点/430项结果对账；CST已全部退出时，仍显示要清理1个残留会话，会误导排障和退出判断。

建议按钮改为“恢复项目/核验并恢复”，残留会话数来自完整lifecycle统计，结果对账数量另行显示。不同事实缺失显示未知，不把布尔值伪装成计数。

## 安全上应保留的拒绝

未知或复用PID、未归属的孤儿进程、坏StopAck/v2回执、快照hash变化、重复/缺失采用身份不能自动放行。Start=1/进程退出0/worker.state=stopped均不单独等于结果或收尾成功。旧数据缺身份时需要一条有证据的人工复核入口；当前只有“需人工核验”的提示，没有完成该复核的正式操作，这是设计欠账，不应改成猜测退出。

Manager CLOSED/Worker DEAD目前还含资源池退役含义，不能从该状态推断CST已退出；上层必须继续使用独立lifecycle证据。未发现本批静态审计足以证明已确认结果被覆盖或重复求解的新缺陷，不把“未发现”当完整证明。

## 建议执行顺序与验收

1. 先做A01/A03：停止意图和全部旧启动意图幂等收口；多次恢复和重启不反复出现同一待恢复意图，不重算/重复采用。
2. 做A02/A04：去除重复扫描、将重型I/O移出全局锁，明确恢复暂停点；阻塞哈希时status仍可返回，ACK/StopAck各窗口暂停不破坏证据。
3. 做A05/A06/A07：已退出/已拒绝/未知状态各自提示；导出与退出可取消/重试；不同关闭方式对Runner和目录占用的结果明确。
4. 再验证旧数据人工复核、归属及目录迁移边界；真实CST另行串行副本验收，不默认启动。

本轮三项最小离线复现完成；没有将新发现写成已修复。现有回归通过只支持其原覆盖范围，尤其前批“GUI可在RECOVERY_REQUIRED请求shutdown”没有覆盖stop_after_start=True的组合。文档索引验收另记current-status。

## 后续实施

A01–A08已按[实施记录](recovery-exit-audit-implementation.md)修复并做离线故障验收。本文“未实施/缺陷”是分析时点证据，不表示最新代码仍未处理；真实CST/现场根因未因此追认。
