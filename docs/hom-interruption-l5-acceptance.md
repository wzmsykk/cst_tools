# L5 小网格 Pillbox：真实 HOM 中断与恢复

日期：2026-10-25。此记录针对生产 Runner → Backend → HomScanAlgorithm → Manager → Managed Worker → CST 链路，不以标准批次或假 Worker 代替 HOM 验收。

## 范围与方法

使用测试夹具 Pillbox 的独立副本，CST 2022、cells per wavelength=8、nmodes=1、初始区间480–530 MHz、终点530 MHz；仅配置 Frequency 后处理。不修改原工程，不终止 CST。无总求解超时；通信、启动、退出仍有界。

[探针](../test/support/validate_hom_exit_l5.py)先运行无中断基线，再串行在三个时点结束本轮拥有的 Python Runner：

1. 首个模式的检查点已写、receipt/RunStore采用标记尚未写。
2. 已有首段确认覆盖，下一任务接收成功但尚未发布ACK。
3. 已有首段确认覆盖，下一任务已进入实际 EigenmodeSolver.Start。

孤立 CST 继续完成自身工作；新 Runner 显式recover、再次recover、resume。核对确认检查点在对账期间字节不变，旧模式/TaskID/后处理值及CST快照和原生场哈希保留；覆盖不倒退、TaskID不重复、每所属RunStore采用事件一条。最终提交参数序列、实际Solver调用数和覆盖与无中断基线比较。算法规定的扩窗确认属于基线工作，不作为恢复重复计算。

独立求解的频率/区间末位可能相差约1e-12MHz，跨用例数值比较采用abs=1e-6MHz、rel=1e-9；任务数量/顺序、nmodes=1、TaskID唯一性、旧模式记录、旧快照/场SHA256不因此放宽。CSV的taskId顺序/唯一性和频率也与最终检查点核对。

运行命令：

```powershell
python test/support/validate_hom_exit_l5.py --cst-exe "D:/Program Files (x86)/CST Studio Suite 2022/CST DESIGN ENVIRONMENT.exe" --point all
```

## 本轮发现与修正

真实检查点的 `mode.project_snapshot` 由 HomScanAlgorithm 保存为相对项目根目录路径。此前 `reconcile_checkpoint_adoptions` 按程序cwd解析，合法HOM恢复被误拒绝为 `HOM checkpoint result differs from receipt`。现明确以项目根目录解析，再与receipt绝对路径及原SHA256严格核对；绝对路径保持原义。没有改变检查点、模型、覆盖或VBA wire，也不通过重算规避核验。

回归夹具增加相对路径/绝对路径与多模式/空任务组合；先前仅绝对路径夹具不足以暴露生产格式差别。初轮探针另有起始窗口上限大于终点的配置错误，已被现有ScanPolicy拒绝并正常收尾，失败不计通过。

## 验收记录

真实矩阵通过，根目录 `artifacts/hom-exit-l5-68989b49`；统一汇总 `artifacts/hom-interruption-l5-verification-20261025.json`。各用例均为实际求解/实际结束本轮Python Runner，不是协议文件回放。先前2026-10-24标准双任务验收仍是其原范围。

|用例|实际Solver调用|确认前沿|已计算上界|核验|
|---|---:|---|---|---|
|无中断基线|5|最终530MHz|最终约738.745671MHz|无失败/待扫区间|
|检查点已写、采用未写|5|503.494644596→530MHz|530→约738.745671MHz|两次recover不改检查点，补写采用，旧Task/结果/四个场哈希不变|
|received未ACK|5|503.494644596→530MHz|530→约738.745671MHz|已有计算复用，提交序列与基线一致|
|实际Solver执行期间退出Runner|5|503.494644596→530MHz|530→约738.745671MHz|孤立CST完成后恢复，不重新求解该任务|

每例最终5个实际提交TaskID均唯一，参数顺序与基线在明确数值容差内相同；3个已确认TaskID（含超终点后终止扫描的确认任务）每个所属RunStore采用事件一条。CSV两条数值结果与检查点一致，未增加重复行。两条近频结果不能当作两个独立物理模，见下方边界及[知识库](../knowledge-base/hom-interruption-l5-20261025.md)。

确认前沿与已计算上界分别保留：扩窗使calculated_upper超过扫描终点，不将其强制改成模式最大频率，也不以它替代confirmed_frontier。

最终所有会话进程死亡且needs_recovery=False。无中断实例保有退出0证据；Controller被结束后丢失原Popen退出观测的孤立实例由显式恢复记为abandoned-dead，Runner可显示exited-unverified。此处不伪造退出0、不称为已证明标准关闭，但无活跃进程或待恢复阻断；其余新Worker正常退出。

修复前路径错误的原失败目录另外重新启动测试Runner恢复通过：检查点SHA不变、Solver仍1次，证据 `artifacts/hom-exit-l5-d1252d1f/checkpoint/path-fix-recovery-verification.json`。初轮失败记录不改成成功。初版跨用例汇总严格浮点相等因约1e-12MHz差异失败，改用已声明容差后重新独立复核通过，未重新计算或改写原数据；未把旧脚本退出码当新验证结果。

最终离线其余套件776 passed、21 integration deselected（154.53s）；主窗口独立34 passed（1.05s）；最后恢复/覆盖/采用/探针/文档与日志索引专项79 passed（6.73s，含重叠）。报告`artifacts/hom-l5-{offline-final,window,focused-final}-20261025.xml`。索引检查只证明链接和符号可解析。

初次受限全仓运行807 passed、1 failed、1 teardown error，均关联假对端读取current.ack的PermissionError；不计整套通过。正常用户权限分组复验通过，不证明权限/文件共享时序偶发问题已消除；生产协议未因此增加盲目重试或放宽校验。

## 边界

本轮不证明十模式长扫描、所有复杂后处理、退简并识别、多用户竞争、其他CST版本、掉电或任意指令级崩溃恢复。保留轻量报告/日志/宏/检查点/哈希；artifacts不保证随Git迁移。原始场与副本结束后清理，清理后重新验证需再生成。

清理完成：四个成功用例及两个初轮失败目录所属三个根目录共删除193296796字节（约184.3MiB）可再生模型/原始场，pytest本轮临时目录已清理。保留报告、宏、日志、检查点、receipt/RunStore及各根cleanup.json中的模型/场SHA256，原生output/progress与Model.run另存retained-native。旧路径现不能直接恢复或重验原始模型，需重新生成。所有测试Runner已离线，CST清单为空，原Pillbox SHA256保持7b63939b2dbed3de567aa55a5ff19cb69e7447245882a691be15d28580f1ddfa。
