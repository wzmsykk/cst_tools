# 最小 Python / VBA 协议 TODO

设计依据：[最小 Python / VBA Runtime Protocol](./minimal-python-vba-protocol.md)

## P0：修复现有确定缺陷

- [x] 已存在 `.failure` 时立即返回 Failure。
- [x] 修复成功返回 TaskIndex 加一偏移。
- [x] `.rd0` 缺失时返回明确失败，不返回成功 `None`。
- [x] Worker v1 每个任务使用独立结果目录；legacy Worker 等迁移时再切换。

## P1：最小协议

- [x] 定义 Task、Completion、Ack 三个 dataclass。
- [x] 实现键/值双行 Codec。
- [x] 实现 `.tmp -> final` 原子提交。
- [x] 增加 task UUID 和 Worker session UUID。
- [x] 保留 literal/expression 参数语义。
- [x] 只定义 `INVALID_TASK`、`REBUILD_FAILED`、`SOLVER_FAILED`、`RESULT_FLUSH_FAILED`、`INTERNAL_ERROR`。

## P2：fake Worker 安全网

- [x] 冻结 Task、成功/失败 Completion、Ack golden vectors。
- [x] 实现独立 VBA v1 Task decoder、Completion writer 和 Ack decoder。
- [x] VBA Codec 无 `Sub Main`，尚未接入生产 Worker。
- [x] 不读取 `.tmp`。
- [x] 拒绝错误 session。
- [x] Completion 必须匹配 task。
- [x] Ack 前不得读取下一任务。
- [x] failure 不进入结果读取。
- [x] 超时后停止 Worker；成功 Completion 不停止 Worker。

## P2.5：接入前 Gate

- [x] 使用目标 CST 2022.5 的 VBA/WWB 解释器执行 golden vectors，而不仅是静态检查。
- [x] 把 VBA Codec 编译进一份独立测试宏，验证 ASCII 文件读写和 `Name temp As final`。
- [x] 使用标准 OLE `Project.Quit` / `Application.Quit` 关闭测试项目和应用，并验证无 CST/UI 残留；强制清场发生时 Gate 失败。
- [x] Gate 已通过；允许进入 P3 的独立 Worker v1 接入。失败期间只修 Codec，未改 legacy `worker.vb` 生命周期。

验证记录：真实 Contract Test 已在包含完整 P2 的当前实现上通过（2026-09-16，`1 passed in 24.32s`）。外部控制器通过版本化 `CSTStudio.Application` OLE 接口创建并持有项目，宏写出成功 marker 后正常返回，再依次调用标准 `Project.Quit` 和 `Application.Quit`。由 OLE 持有项目的 Contract 宏内不得调用 `Quit`；P3 的应用级 `-m` Worker 则在 Ack 后自行 `Save`、`Quit`。只有标准退出成功且未留下需要用户通过 UI 处理的窗口或进程，Gate 才能通过；强制结束仅用于失败清场。

P2.5 至此完成。下一步 P3 使用独立 Worker v1 路径验证 default 工程、参数、Rebuild/Solve/Flush 和一个 `.rd0`；在 P3 通过前不替换现有 legacy `worker.vb`，新旧协议不得共用 Worker 目录。

## P3：真实 CST 最小验证

- [x] default Pillbox 工程的独立临时副本。
- [x] 一个 literal 参数：`nmodes=1`。
- [x] 一个 expression 参数：`L=R + 30`。
- [x] 一次 Rebuild/Eigenmode Solve/Backup Flush。
- [x] 一个 `.rd0` 结果：`Result/Frequency (Multiple Modes)/Mode 1.rd0`。
- [x] Python 读取完成后 Ack。

验证记录：真实 Worker v1 Gate 已在 CST Studio Suite 2022 上通过（2026-09-17，`1 passed in 54.13s`）。CST 通过应用级 `-m` 执行独立 Worker v1；Worker 打开临时工程副本，应用参数并完成求解和 Backup，确认 `.rd0` 已落盘后才发布 Completion。Python 使用现有 `cst0dreadout` 读得 `503.782` 后发布 Ack，Worker 随后调用官方 `Save`、`Quit`，测试确认未留下需要用户处理的 CST/UI 进程。

P3 没有替换 legacy `worker.vb`，也没有引入 Result Manifest、通用 Operation ABI 或新 Transport。真实 CST 产物证明该结果是目录化路径，而不是早先假设的扁平 `Result/<name>.rd0`。

## P4：最小 Warm Worker 双任务验证

- [x] 同一 CST 进程连续执行两个任务。
- [x] 每个任务使用 `results/<task-uuid>/` 独立结果目录。
- [x] 第一任务 Ack 前不读取或执行第二任务。
- [x] 两个任务分别使用 literal 和 expression 参数。
- [x] 两个 `.rd0` 均由 Python 在对应 Completion 后读取。
- [x] 第二个 Ack 后发送 session-scoped Stop Request。
- [x] Worker 写出 Stop Ack 后执行官方 `Save`、`Quit`。
- [x] 记录每个任务的 Rebuild、Solve、Backup Flush 时间。

验证记录：真实 Warm Worker Gate 已在 CST Studio Suite 2022 上通过（2026-09-17，`1 passed in 241.76s`）。`R=229, L=R+30` 得到 `503.782`；`R=230, L=R+29` 得到 `501.576`，因此第二次读取不是第一任务残留。两次计时分别约为 `Rebuild 0.608s / Solve 104.498s / Flush 0.819s` 和 `Rebuild 1.059s / Solve 105.670s / Flush 2.310s`。本样本证明了串行时序、结果隔离和可控退出，但没有证明 Solve 加速；Warm/Cold 性能结论仍需多点对照。

P4 使用独立的有界双任务 Worker Gate，不替换 legacy `worker.vb`。Stop 协议仅包含 session ID，不扩展为通用控制或恢复协议。

## P4.5：固定 HOM 结构扫频基准

- [x] 使用 `HOM analysis_clean.cst`，所有几何参数保持不变。
- [x] 仅改变 `fmin/fmax`：`720–800 MHz`、`800–880 MHz`。
- [x] 两个频段分别执行独立 Cold 进程。
- [x] 同一 CST 进程串行执行两个 Warm 频段。
- [x] Cold/Warm 使用相同 Task/Completion/Ack 和独立结果目录。
- [x] 比较每个频段的原生 Frequency `.rd0`。
- [x] 记录 Rebuild、Solve、Flush 和进程墙钟时间。
- [x] Stop Ack 后标准 Save/Quit，无 CST/UI 残留。

验证记录：真实 HOM Cold/Warm Gate 已在 CST Studio Suite 2022 上通过（2026-09-17，`1 passed in 446.68s`）。Cold 两次墙钟合计 `270.062s`，Warm 双任务墙钟 `172.796s`，整体加速 `1.563x`。`720–800 MHz` 的 Cold/Warm Frequency 均为 `765.981`；`800–880 MHz` 均为 `826.770`。第二频段 Solve 从 Cold `41.012s` 降至 Warm `26.477s`。结果支持“复杂 HOM 结构不变、只改变频率范围”时保留 Warm CST 的价值。

该双点结果是可重复基准的起点，不外推为所有工程或所有频段的固定加速比。后续性能结论仍应使用更多频段和重复运行统计。

## P5：HOM 原生结果最小闭环

- [x] 为已验证的 HOM 工程定义固定结果映射，不引入通用 Result Manifest 或 Operation ABI。
- [x] 直接读取 CST 工程快照中的 5 个原生 `.rd0`：Frequency、Q-Factor、轴上 R/Q、5 mm 偏轴 R/Q、10 mm 偏轴 R/Q。
- [x] 结果对象携带稳定 key、数值、单位和来源路径。
- [x] 缺失、空文件、多行、非数值及非有限值均返回明确错误。
- [x] Cold/Warm 两个频段逐项比较全部 5 个原生指标。
- [x] 将当前工程中不存在原生 `.rd0` 的 Shunt Impedance、Total Loss、Voltage 明确归类为 `runtime-vba`。

验证记录：扩展后的真实 HOM Gate 已在 CST Studio Suite 2022 上通过（2026-09-17，`1 passed in 523.97s`）。`720–800 MHz` 的 Cold/Warm 结果完全一致：Frequency `765.981 MHz`、Q-Factor `229.748`、R/Q `0.125728 ohm`、5 mm 偏轴 R/Q `0.243961 ohm`、10 mm 偏轴 R/Q `0.457261 ohm`；`800–880 MHz` 对应为 `826.770 MHz`、`54.0335`、`0.00750064 ohm`、`0.00747065 ohm`、`0.0432976 ohm`。Cold 两次墙钟合计 `307.860s`，Warm 双任务墙钟 `213.031s`，整体加速 `1.445x`。

P5 证明的是“现有 CST 原生标量的严格读取”和 Cold/Warm 一致性。它尚未证明这些原生 R/Q 与 `EigenResult_Complex.vb` 自定义算法数值等价，因此暂不删除复杂 R/Q VBA；若业务仍依赖该算法，应先建立同参数基线再决定迁移。

## P5.5：固定 Result Template 与动态运行时后处理边界

- [x] 将 R/Q 能力按积分位置路由，而不是把整个指标统一标记为 `native`。
- [x] 按官方 `coordinates=0/1/2` 和 `u/v/w` 设置建模 x/y/z 任意积分轴与三维偏移。
- [x] 任意轴上与工程内预定义模板精确匹配的积分线使用原生 Result Template 输出；当前 HOM Profile 实际预装 z 轴 0/5/10 mm。
- [x] 未预定义的任意轴、任意积分位置继续使用 `EigenResult_Complex` 运行时 VBA。
- [x] 显式拒绝求解后通过修改工程参数驱动 Result Template；`Update Params` 会使当前求解结果失效。
- [x] 使用同一次 Solver 结果运行 x/y/z 三个方向和 5/7.5 mm 复杂 R/Q 后处理，不执行第二次 Rebuild/Solver。
- [x] 5 mm 运行时 VBA 与工程内预安装 Result Template 数值对照。
- [x] Completion/Ack 后标准 Save/Quit，无 CST/UI 残留。

验证记录：真实多轴 P5.5 Gate 已在 CST Studio Suite 2022 上通过（2026-09-17，`1 passed in 165.78s`）。同一次求解后，x 轴（y=5 mm）得到 `0.343891121231489 ohm`，y 轴（x=5 mm）得到 `7.10848179256522 ohm`，z 轴（y=5 mm）得到 `0.243960805493713 ohm`，z 轴（y=7.5 mm）得到 `0.338608596491386 ohm`。其中 z 轴 5 mm 与原生 Result Template 的 `0.243961 ohm` 在输出精度内一致。本次 Rebuild、Solve、Flush 分别约 `5.023s`、`46.850s`、`5.182s`，运行时后处理阶段没有修改工程参数。

Result Template 生命周期由此分为两类：求解前可安装模板并设置随后参与本次求解的参数；求解后只能直接 Evaluate 已注册模板、修改不触发工程参数更新的模板实例设置，或调用运行时 VBA。禁止以工程参数变化模拟求解后的动态积分位置。

## P5.6：已注册 Result Template 的运行期边界

- [x] 使用 CST 官方 `ResetTemplateIterator` / `GetNextTemplate` 盘点项目已注册模板，而不是用 `.r0d/.r1d` 文件存在性冒充注册状态。
- [x] 使用官方 `EvaluateResultTemplates` 对当前 Run 重新评估全部已注册模板。
- [x] 显式评估前后 inventory 必须一致，代表运行期没有偷偷新增、删除或改名。
- [x] 显式评估前后的原生 Frequency `.rd0` 必须一致。
- [x] 整个 Gate 只运行一次 Solver，求解后不调用 `StoreParameter`、`Update Params` 或 Rebuild。
- [x] Completion/Ack 后仍使用标准 Save/Quit；强制清理发生时 Gate 失败。

CST 2022 的公开 VBA API 提供模板枚举和评估，但不提供新增、复制、删除模板的方法；官方自带 `Import Result Templates` 宏也已废弃，并要求在 Template Based Post-Processing 对话框中复制/粘贴。因此 P5.6 不把 GUI 自动化包装成运行协议：模板安装属于一次性的 Project Profile 制备与版本评审，运行期只验证声明能力并执行评估。`.r0d/.r1d` 修改器仍只用于读取、diff 和受控实验，不能声称完成模板注册。

验证记录：真实 P5.6 Gate 已在 CST Studio Suite 2022 上通过（2026-09-17，`1 passed in 178.71s`）。官方 iterator 返回 5 个已注册 M0D 模板，均由 `3D Eigenmode Result` 提供；显式 `EvaluateResultTemplates` 前后 inventory 完全一致，Frequency 均为 `765.981 MHz`。本次只调用一次 Solver，求解后没有参数更新，并在 Completion/Ack 后标准 Save/Quit；只保留运行前即存在的 `cstd.exe` 许可服务。

## P6：最小 HOM Project Profile

- [x] 只定义一个 `hom-2022-v1` Profile，不引入通用 Schema 或动态能力协商。
- [x] 声明 CST 2022、prepared 源工程和 Warm 任务只允许修改 `fmin/fmax`。
- [x] 集中声明 5 个必需 M0D Result Template 的完整注册身份。
- [x] 集中声明 5 个原生标量路径、单位和 3 条固定 R/Q 积分线。
- [x] 声明动态 R/Q、Shunt Impedance、Total Loss 和 Voltage 继续使用运行时 VBA。
- [x] Python 在生成 Worker 前拒绝 Profile 未允许的任务参数。
- [x] Worker 在参数更新、Rebuild 和 Solver 前使用 CST 官方 iterator 校验模板能力。
- [x] 缺少能力时发布 `PROFILE_CAPABILITY_MISSING`，不启动 Solver，并标准退出。
- [x] 现有 HOM reader 和 R/Q 路由从 Profile 派生，同时保留兼容常量。

P6 仍不自动安装 Result Template，也不引入 Profile 哈希、Manifest 或通用 Operation ABI。prepared 工程是 Profile 的权威载体；运行期只做确定性预检。

验证记录：真实 P6 Gate 已在 CST Studio Suite 2022 上通过（2026-09-17，`2 passed in 292.90s`）。正向 `hom-2022-v1` Profile 在参数更新前确认五个模板后完成唯一一次 Solver，显式模板评估前后 Frequency 均为 `765.981 MHz`。负向 Profile 临时声明一个不存在的模板，Worker 返回 `PROFILE_CAPABILITY_MISSING`，未生成 timing/result 文件，并以 CST 批处理退出码 0 标准结束；两次测试均未留下新增 CST/UI 进程。

## 明确不做

- [ ] 不做 Result Asset Manifest。
- [ ] 不做参数或结果 SHA-256。
- [ ] 不做动态 capability negotiation。
- [ ] 不做多 Transport 抽象。
- [ ] 不做通用 Operation/插件 ABI。
- [ ] 不做跨主机和断点恢复。

以上项目只有出现真实失败样例或明确需求后才能移入实施列表。
