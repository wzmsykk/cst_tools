# HOM求解失败：临时加密、扩窗探测与窄窗恢复

2026-10-25。针对[现场迭代耗尽/退出1](field-failure-bundle-20261025.md)。实现入口AdaptiveHomScanner._recover_interval、HomScanAlgorithm.start、ManagedCSTWorker.retire_failed_session。本轮是源码/假Worker/假协议对端验证，没有启动真实CST或操作用户原工程。

## 默认生产流程

1. 常规窄窗仍nmodes=1，单Worker正常任务只传nmodes/fmin/fmax，不反复写cell。仅SOLVER_FAILED（包括Start=0、solver-start/solver-result异常）进入数值恢复；ACK/通信、参数/重建、后处理或输出非法不被当成空区间证据。
2. 已知固定网格绑定时，同一失败窄窗仅加密一次：临时cell=max(base+1,ceil(base*1.5))，如4→6。保持关闭自适应，不改原processed.cst。cell已由预处理历史绑定MeshSettings StepsPerWaveNear，参数变化经正常Rebuild/Start生效，不增加未经文档核实的Mesh API。项目配置为保持原Mesh/未绑定固定cell时跳过加密，不创建无效cell假装已调网格。
3. 加密重算成功且有有效模式时可接受该模式，存档/CSV保留实际密度。下一次常规任务恢复base cell；之后单Worker不再重复传cell。多Worker发生过密度恢复后，每次明确传base cell，防止任务轮转到仍保留临时密度的另一个Worker；相同表达式仍由VBA跳过写入。恢复的是密度设置，不是保证网格二进制完全相同。加密成功存档不反向改参数/重建，避免清掉结果；停止/结束时原预处理基准始终未变。加密成功但零模态只作为证据，仍需原密度扩窗，不直接判原区间为空。暂停后active_mesh_cells也持久化，即使没有mode记录，续跑仍知道需切回原密度。
4. 加密仍失败或返回上界外模式，则先恢复原密度，再扩窗探测。保持原失败下界，默认原宽度的2/4/8倍，最多3级；每次仍只求首个模式。探测上界允许越过全局输出终点以定位下一个模式，但不把终点外模式加入结果。所有尝试受累计max_solver_calls预算，正常Solver不设固定总超时。
5. 探测得到有效首模后不直接入模式表：在其附近建立一个正常window_width窄窗，以原密度确认并取得对应后处理值。确认频率须在窄窗内、不是已采用频率，并与探测频率差不超过5%/绝对容差阈值；这是防明显跳模的数值检查，不是COMSOL场重叠匹配或退简并模式身份认证。
6. 确认后从模式频率右侧的小偏移继续原密度窄窗扫描，宽窗不会变成后续默认窗口。若确认得到模式在原区间内，不判原区间空；若探测首模和窄窗确认都位于原上界之上，则按用户约定将原区间记录为empty，写入empty-inferred证据。成功探测明确返回零模态时，也只标原窄窗empty，随后回窄窗；原生生产宏仍要求其现有成功/结果门禁，不能把Start=0当零模态成功。

判空依赖CST SetFrequencyTarget下限以上首模按升序返回的契约，并限于当前模型、边界和求解筛选条件。失败/达到迭代上限、非法结果或探测始终无有效解都不判空。探测/确认耗尽时保留failed原区间，不用扩窗范围覆盖它；按原有策略可继续后续区间，但最终存在缺口，不声称全覆盖。

## 覆盖、结果和恢复检查点

成功探测记录probed范围及其TaskID，探测作为已消费的证据采用，不重复作为模式导入。probed可以抬高calculated_upper；它不能单独推进confirmed_frontier。未完成确认时原区间仍在pending，确认覆盖保持在原下界；失败则留在failed。全局终点外候选不入模式列表。

检查点写入schemaVersion=4：保留原policy/项目指纹/结果/快照约束，新增recovery_states、recovery_events、probed、active_mesh_cells及模式mesh_cells_per_wavelength。每次效果前持久化当前阶段/累计调用数；成功探测后保存候选、probe_hi和confirm阶段。确认前中断后直接续confirm，不从正常失败求解重来。未完成的同一阶段可依既有received/ACK/快照身份对账取结果，不为修补元数据主动重放Solver；真正未产生可采用结果的在途阶段仍需重新计算。

读取旧v3时仅为缺失的新增恢复策略填入当前默认，扫描边界/项目指纹/原模式/采用和快照哈希继续严格检查；首次后续保存升级v4。v4缺字段/策略不匹配不自动改策略。旧程序不能读取新v4，升级后不要降级运行此项目。HomRunManifest的原基准/mesh/边界检查不放宽。

普通任务名和参数保持原形式以兼容旧received匹配；只有mesh/probe/confirm附加阶段名。HOM关闭Manager内部相同参数盲重试（retry_count=0），由扫描器统一安排恢复顺序；正常Worker任务上限回收和标准批任务行为不变。CSV新增meshCellsPerWavelength；历史ModeResult没有密度时为None，不推测旧结果使用何种实际Mesh。

## 非标准失败会话退役

正常退出接受规则仍仅0/严格恢复4，退出1不改为standard_closed。HOM任务显式设置SimulationTask.retire_failed_session=True，在stop已正常等待/取证但拒绝退出1后，才允许尝试严格退役：v2、任务failure、模型restored-saved、进程及后代已结束、唯一缺项为exit-code-not-accepted；恢复快照存在/大小与回执一致、记录的退出/PID/证据SHA仍匹配；有效StopAck和该TaskID的ACK accepted回执；无当前task/completion/ack、临时文件或当前任务待采用成功结果。

核验通过记录recovery-l1.json disposition=abandoned-dead，保留实际exit_code=1和standard_closed=false，关闭日志后新Worker从processed.cst建立。不是强杀、不是把失败结果改为成功，不重用失败恢复快照做计算基准。没有来源不明进程清理，也不改标准批任务默认策略。未知/活跃进程、缺或坏证据/哈希变化/已成功但后处理失败、ACK待定仍停止调度并要求显式恢复。

Runner最终发现仍有阻断会话时会保留recovery_reason；即使业务返回ScanInterrupted也不会留下RECOVERY_REQUIRED但顶层error为空。原错误已存在则保留，不用新关闭原因覆盖求解根因。

## 配置、GUI与诊断

生产HOM默认启用；独立ScanPolicy回调API为兼容旧调用默认failure_recovery=False，调用方明确开启后使用base_mesh_cells、mesh_retry_factor和max_probe_expansions。GUI没有新增复杂profile/协议协商或一组恢复开关，基准密度沿用当前固定mesh设置。

GUI主工作台显示临时加密/原密度扩窗/原密度窄窗确认阶段；新模式带密度时额外显示cells/λ设置列，旧模式为未知，不把它当实际网格单元总数。仅恢复元数据变化不会重建未变化模式表。结构化事件HOM_RECOVERY_STEP/RESULT/FAILED/EMPTY及WORKER_FAILED_RETIRED提供阶段、范围、密度、TaskID和退役事实；每个步骤结果/错误写入检查点和原日志，诊断导出继续包含这些文件。

## 当前验收与未完成

核心、Manager、Runner、采用/恢复、manifest、随机假Worker/mesh回归167 passed（17.27s），artifacts/hom-recovery-final-20261025.xml；收尾证据/新恢复/Runner原因/工作台专项58 passed（17.43s，重叠），hom-recovery-focused-20261025.xml；GUI/假Worker流程13 passed（1.38s，重叠），hom-recovery-gui-20261025.xml。首轮39 passed/2 failed为旧断言发现正常任务传cell，随后改为仅需恢复密度时传cell并复验；另一次131 passed/1 failed为新测试插入位置错置旧facts断言，修正测试归属后复验，原失败XML保留。

测试涵盖加密成功后恢复基准、加密失败→扩窗→窄窗确认→常规、空探测与无效/失败探测区别、调用预算、探测后中断只续确认、v3迁移身份约束、密度状态持久化、失败退出1的严格退役与快照篡改/缺ACK拒绝、普通任务不自动退役及顶层错误传播。

尚需真实CST串行副本验收：cell4→6是否实际重建网格及恢复4、真实迭代耗尽后的退役/新基准、扩窗首模与窄窗对照和中断窗口。当前没有真实原工程或长达50分钟求解补验，不能宣称解决数值不收敛或保证物理无漏模。加密和扩大最高频率会增加内存，现有资源准入/内存保护仍适用；5%频率检查不替代复杂模式匹配。

现场旧项目已经RECOVERY_REQUIRED时仍应先执行一次“清理残留会话”，再“继续未完成扫描”；不会绕过旧会话的显式恢复门禁。未提交或打包。

### 2026-10-25 最终离线复验补充

正常用户权限的无CST协议/Runner回归92 passed（12.49s），扫描与恢复检查点73 passed（6.44s），GUI及假Worker流程15 passed（1.62s），诊断导出与索引27 passed（3.19s）；各组重叠，不相加。报告分别为artifacts/hom-recovery-native-final-20261025.xml、hom-recovery-closeout-20261025.xml、hom-recovery-gui-final-20261025.xml、hom-recovery-bundle-20261025.xml。此前受限环境协议夹具读文件出现PermissionError，88 passed/4 failed/4 errors；保留失败记录，不用重试掩盖原因，正常权限通过也不证明现场不存在瞬时文件访问异常。

最终审计将生产接口的空后处理列表视为输出缺失，禁止据此确认空区间；通用扫描器的明确空结果契约保留。相关测试首次52 passed/2 failed：密度测试夹具以空后处理结束尾窗，更新为含终点模式的夹具后54 passed（3.10s），报告artifacts/hom-recovery-final-audit2-20261025.xml。未启动真实CST，临时加密是否实际生效及现场扩窗恢复仍待串行副本验收。轻量报告保留，临时测试副本清理；artifacts不保证随Git迁移。
