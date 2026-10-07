# HOM 窄区间单模式扫描算法

## 目标

在扫描范围内按频率顺序逐个求解 HOM。CST 在较大频段内同时求多个本征模态时精度较差，因此主约束是：每次只请求一个模式，并尽量保持求解区间窄。

## 推进规则

1. 首次使用 GUI 给出的 fmin/fmax，且 nmodes=1。
2. 找到频率 f 后接受 Mode 1 的完整后处理结果。
3. 下一段从 f 加一个微小 tolerance 开始；窗口宽度继承 GUI 首段宽度，但不超过 50 MHz。
4. 没找到模式时，把下限推进到当前上边界，再扫描下一个窄窗口。
5. 到达 endfreq 后结束。

搜索窗口不保证其中存在模态，fmax 不作为返回频率的硬上限。
若单模结果高于当前窗口上限，保留下限，将上限提高到返回频率加一个窗口宽度，
留出余量后重新求解。只接受落在实际求解窗口内的重算结果，以重算得到的频率、
全部后处理值和存档为准；首次窗口外结果不计入模态汇总。
确认后的下一模式超过 endfreq 时正常结束，不将范围外模式写入汇总。
确认窗口可超过 endfreq；后续普通窗口仍维持原窗口宽度并受 endfreq 限制。
重算次数受区间重试预算及总求解次数限制。低于下限、重复模态、重算仍越界和
实际求解失败均保留具体失败原因。

日志使用 `HOM_SOLVE_RESULT` 展示每次返回频率和全部后处理值；
`HOM_MODE_ACCEPTED` 展示已确认模态的序号、频率、任务和存档路径；
`HOM_WINDOW_EXPAND`、`HOM_SCAN_LIMIT_REACHED`、`HOM_INTERVAL_EMPTY` 和
`HOM_FAILED_INTERVAL` 分别记录扩窗确认、扫描终点、空区间与具体失败原因。

旧实现使用 0.1 MHz 向上取整推进，可能跨过很接近的下一模式。新实现只加入 frequency_abs_tol，并用浮点后继值保证严格前进。

## 单模后处理协议

默认 PPS 恢复为 Mode 1 方法：Frequency、Q_Factor、R_over_Q、Shunt_Inpedence 和 Total_Loss。每项必须显式使用 iModeNumber=1。默认扫描不使用 _All，避免对同一大区间内多个模式执行成本高且精度较差的批量后处理。

CST 返回多个模式时不静默截断，而将该区间判为失败；这可以暴露 PPS 或 Solver 配置与单模协议不一致的问题。

## 结果验证

- mode index 为正整数；
- Frequency 和全部后处理值为有限数；
- Frequency 位于实际求解窗口内；首次高于窗口上限时扩窗重算确认；确认后超过 endfreq 正常结束；
- result name 不重复；
- 后处理结果对应 Mode 1。

空结果表示当前窄窗口没有模式，与结果缺失或 CST 任务失败严格区分。

## 失败、终止和恢复

- 每个区间只重试有限次数。
- 总 Solver 调用数有硬上限，防止无进展循环。
- 失败区间及原因写入 checkpoint；扫描结束存在失败区间时抛出 IncompleteScanError。
- 每次命中、判空或失败后原子更新 checkpoint，并同步输出 CSV。
- checkpoint schema、扫描策略、工程指纹或 PPS 指纹不一致时拒绝续跑。

## 已知物理边界

严格同频的简并模式无法仅凭“单模式 + 频率右移”证明全部枚举。右移后仍返回已接受频率时，扫描立即失败并报告可能简并或边界停滞，不能把它去重后宣称扫描完整。若目标工程存在简并模态，应增加专门的窄区间简并探测 Gate，必要时只在该局部区间临时请求多个模式；常规扫描仍保持单模式。

## 真实 CST Gate

1. prepared HOM 工程确认每个任务实际使用 nmodes=1；
2. 与人工窄区间 Cold 结果逐模比较 Frequency、Q 和 R/Q；
3. 验证相邻模式间隔小于旧 0.1 MHz 取整步长时不会被跳过；
4. 验证空窗口、任务失败和 checkpoint 恢复；
5. 单独确认目标工程是否存在严格或近似简并模式；
6. 正常完成、失败和用户停止时 CST 均标准退出。
## 可恢复运行边界

每次真实扫描在结果目录写入不可变 `scan_manifest.json`，包含源工程、prepared
工程、prepared SHA-256、起止频率、初始窗口、模式数、Worker 数和后台策略。
恢复时任一字段不一致都会拒绝继续，防止把检查点应用到另一个结构或频段。

用户停止属于协作式停止：Manager 首先进入 `STOP_REQUESTED`，拒绝新任务并禁止
Worker 轮换；已经进入 `EigenmodeSolver.Start` 的区间允许运行到安全点。该区间结果
写入 checkpoint 后扫描抛出 `ScanInterrupted`，应用状态写为 `INTERRUPTED`，随后
Worker 通过 Stop Request/Ack、Save 和 Quit 退出。紧急进程终止不属于普通停止。
