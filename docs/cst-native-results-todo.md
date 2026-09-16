# CST 原生结果优先 TODO

状态：当前最高优先级  
日期：2026-09-16

知识依据：[Warm CST 与原生结果知识库](./cst-warm-native-results-knowledge-base.md)；[CST `.cst` 项目文件知识库](./cst-project-file-knowledge-base.md)

## 总目标

在建设完整 VBA/Python 后处理 ABI 前，验证主要优化指标是否可以直接从 CST 工程结果读取。根据验证结果，把后处理需求划分为：

-原生结果直读；
-Python 派生；
-必须保留的 VBA Extension。

最终目标是保留 Warm Mesh/进程复用收益，同时移除不必要的运行时 VB 后处理。

## Gate 0：冻结当前基线

- [ ] 选择 default、TM020、WTC 各一个权威参考工程。
- [ ] 记录对应 CST 版本。
- [ ] 保存一组固定参数输入。
- [ ] 使用当前 VB 后处理生成参考结果。
- [ ] 记录每项结果的数值、单位、模式编号和来源。
- [ ] 保存结果样本和 SHA-256。
- [ ] 定义每项物理量允许的比较容差。

验收标准：后续任何直读结果都可以与固定参考基线比较。

## Gate 0.5：吸收 `cst_version` 容器能力

- [ ] 从 `D:\work\cst_version\cstv.py` 提取最小只读核心，不通过 `sys.path` 依赖相邻项目。
- [ ] 为容器签名、中央目录和 EOCD comment 建立单元测试。
- [ ] 使用当前仓库 CST 2015、2020、2022 样本建立兼容性矩阵。
- [ ] 为零参数工程建立合法样本测试。
- [ ] 为截断文件、错误 offset、重复成员名和损坏 Deflate 建立拒绝测试。
- [ ] 使用 Enlarged/HOM 建立多工程复合结构 golden tests。
- [ ] 解析 EOCD 和中央目录，禁止通过全文件签名搜索遍历成员。
- [ ] 定义 `ProjectScope`，支持 root 和 `SP/<name>`。
- [ ] 所有参数、历史、设置和结果标识都包含 scope。
- [ ] 用 `.cst` 参数直读替代 `GetParamList.vb/readParamsT.vb`。
- [ ] 验证直接读取不会触发 CST Save 或改变源文件 SHA-256。
- [ ] 验证不同 scope 的同名成员和同名结果不会碰撞。
- [ ] 生成成员名称、大小、CRC、SHA-256 和类型分类的 manifest。
- [ ] 实现 `project_sha256`、`member_manifest_sha256`、`model_state_fingerprint` 和 `history_sha256`。
- [ ] 将 `.rd0` 结果与 `.r0d/.r1d` Result Template artifact 建模为不同资产类型。
- [ ] 实现 `.r0d/.r1d` 只读 parser：header、ordered settings、VBA source。
- [ ] 保留未知 header 字段，不猜测其语义。
- [ ] 未知容器布局返回明确的不支持错误，不做猜测性写回。

验收标准：只读解析在代表样本上可重复，损坏/未知格式安全失败，且不修改任何 `.cst`。

## Gate 1：结果资产盘点

对每个 Profile 和指标填写：

| Profile | 指标 | 当前来源 | 候选内部文件 | 格式 | 单位 | 模式规则 | 跨版本状态 | 候选 Provider |
|---|---|---|---|---|---|---|---|---|
| WTC | Frequency | Direct PPS | `.rd0` | text | 待确认 | Mode 1 | 待验证 | native |
| TM020 | Frequency | Simple VB | 待查 | 待查 | 待确认 | all modes | 待验证 | 待定 |
| HOM | Frequency | CST native | `Frequency (Multiple Modes)/Mode 1.rd0` | text scalar | MHz | Mode 1 | CST 2022.5 已验证 | fixed HOM reader |
| HOM | Q-Factor | CST native | `Q-Factor (Perturbation) (Multiple Modes)/Mode 1.rd0` | text scalar | 1 | Mode 1 | CST 2022.5 已验证 | fixed HOM reader |
| HOM | R/Q（轴上、5 mm、10 mm） | CST native | 三个 `R over Q beta=1.../Mode 1.rd0` | text scalar | ohm | Mode 1 | CST 2022.5 已验证 | fixed HOM reader |
| HOM | Shunt Impedance / Total Loss / Voltage | Runtime VBA | 当前工程无对应 `.rd0` | — | 待算法确认 | Mode 1 | CST 2022.5 已盘点 | runtime-vba |

P5 已完成上述 HOM Profile 的最小闭环：固定路径、严格标量 Codec、单位、缺失/损坏错误和两个频段的 Cold/Warm 一致性。这里不勾选整个 Gate 1，因为 WTC、TM020、场数据及跨版本盘点仍未完成；也不把 HOM 专用 reader 提升为通用 Provider ABI。

- [ ] 盘点 Frequency。
- [ ] 盘点 Q-Factor。
- [ ] 盘点 Total Loss。
- [ ] 盘点 Voltage。
- [ ] 盘点标准 R/Q。
- [ ] 盘点 Shunt Impedance。
- [ ] 盘点场峰值。
- [ ] 盘点 ModeRec 输入和输出。
- [ ] 盘点 E/H Field 数据。
- [ ] 标记所有私有二进制格式。
- [ ] 标记所有工程 Result Template 依赖。

验收标准：所有生产优化目标均有明确来源或明确“尚不可获得”状态。

## Gate 1.5：单变量工程设置差分

详细实验设计见 [`.cst` 内部后处理与模拟设置修改分析](./cst-project-settings-editing-analysis.md)。

- [ ] 在 CST 中只修改 frequency minimum，保存 before/after。
- [ ] 只修改 number of modes。
- [ ] 只修改 solver accuracy。
- [ ] 只切换一次 mesh adaptation。
- [ ] 只新增一个 0D Result Template。
- [ ] 只修改一个 Result Template 表达式。
- [ ] 只删除一个 Result Template。
- [ ] 比较每项实验的成员增删、SHA-256 和文本语义差异。
- [ ] 在 CST 2020 和 2022 重复关键实验。
- [ ] 验证重新打开、Rebuild、求解后的真实行为。

验收标准：明确每项设置的权威修改入口、派生成员和版本差异；没有证据时一律通过 CST API 修改。

## Gate 2：建立只读探针

- [ ] 实现不修改工程的运行结果目录扫描工具。
- [ ] 使用统一容器模块扫描 `.cst` 内成员，不重复实现 ZIP-like 解析。
- [ ] 记录文件路径、大小、修改时间和哈希。
- [ ] 识别 `.rd0` 文本结果。
- [ ] 识别 ASCII/CSV 结果。
- [ ] 盘点 `.cst` 内 `.r0d/.r1d`，解析 TemplateType、settings 和 VBA SHA-256。
- [ ] 检测空文件和不完整文件。
- [ ] 检测上一任务遗留结果。
- [ ] 不解析未经确认的私有二进制格式。
- [ ] 输出机器可读的 inventory 报告。

验收标准：探针只读运行，不影响 CST 工程和现有 Worker。

## Gate 3：Native Result Provider 样板

- [ ] 定义 `ResultRequest`。
- [ ] 定义 `ResultValue`。
- [ ] 定义 `ResultProvider` Protocol。
- [ ] 实现 `Direct0DProvider`。
- [ ] 实现文本标量 Codec。
- [ ] 研究 `PCIntegrationScalarProvider`，默认保持实验状态。
- [ ] 比较 `PC_integration.json` value、`.rd0`、CST GUI 和现有 VB 结果。
- [ ] 验证求解后不 Save、Save/Flush、改参数但不求解时 value 的刷新和陈旧行为。
- [ ] 增加单位字段。
- [ ] 增加 Profile/来源字段。
- [ ] 增加缺失、空文件、非法数值错误。
- [ ] 使用 WTC 当前 `.rd0` 建立单元测试。
- [ ] 保持当前算法结果结构的兼容适配器。

验收标准：WTC 核心指标无需动态 VB 后处理即可返回统一结果对象。

## Gate 4：TM020/default 可行性验证

- [ ] 对相同参数运行当前 VB 后处理。
- [ ] 读取对应 CST 内部结果。
- [ ] 比较 Frequency。
- [ ] 比较 Q-Factor。
- [ ] 比较 Total Loss。
- [ ] 比较标准 R/Q。
- [ ] 比较 Shunt Impedance。
- [ ] 验证单模式与全模式映射。
- [ ] 验证单位和归一化。
- [ ] 验证结果名称不受 UI 语言影响。
- [ ] 验证重复运行不会读到旧结果。

验收标准：每个指标被分类为 `native`、`python-derived`、`runtime-vba` 或 `unsupported`。

## Gate 5：写入完成与覆盖时序

- [ ] 明确 `EigenmodeSolver.Start` 返回语义。
- [ ] 验证 Save/Backup 对结果文件落盘的影响。
- [ ] 定义 `CST_SOLVER_DONE_V1` 标志。
- [ ] 标志包含 task ID、参数哈希和 Worker ID。
- [ ] Python 只在标志完成后读取。
- [ ] 定义 Python acknowledge。
- [ ] Worker 收到 acknowledge 后才开始下一任务。
- [ ] 测试下一任务不会覆盖上一任务结果。
- [ ] 测试 CST 异常退出时不会误报完成。

验收标准：连续 Warm 任务不会串结果或读到部分写入文件。

## Gate 6：Warm/Cold 性能与一致性

- [ ] 为每个 Profile 选择 20–30 个代表参数点。
- [ ] 测量 Cold 工程准备时间。
- [ ] 测量 Warm 参数更新和 Rebuild 时间。
- [ ] 测量 Mesh 时间。
- [ ] 测量 Solver 时间。
- [ ] 测量结果读取时间。
- [ ] 连续运行至少 50 个 Warm 任务。
- [ ] 记录 CST 内存增长。
- [ ] 记录失败和 Worker 重建次数。
- [ ] 比较 Warm/Cold Frequency。
- [ ] 比较 Warm/Cold Q。
- [ ] 比较 Warm/Cold R/Q。
- [ ] 比较关键场峰值。

验收标准：形成每个 Profile 的 Warm 使用建议、参数范围和精度结论。

## Gate 7：Python Derived Provider

- [ ] 列出可由原生结果计算的派生指标。
- [ ] 记录物理公式及文献/CST 定义来源。
- [ ] 明确峰值/RMS。
- [ ] 明确复数相位规则。
- [ ] 明确单位换算。
- [ ] 明确 beta 和归一化规则。
- [ ] 实现 `PythonDerivedProvider`。
- [ ] 使用当前 CST/VB 结果建立对照测试。

验收标准：派生结果在规定容差内与现有结果一致，并具有独立单元测试。

## Gate 8：Project Profile

- [ ] 定义 Profile Schema。
- [ ] 声明 prepared CST 工程。
- [ ] 声明原生结果能力。
- [ ] 声明 Python 派生能力。
- [ ] 声明可选 VBA Extension。
- [ ] 记录 CST 版本。
- [ ] 记录源工程和 Profile 哈希。
- [ ] 记录成员 manifest、模型状态、HISTORY LIST 和参数 schema 哈希。
- [ ] 记录 Result Template/结果成员 inventory，并区分“存在”和“已解码”。
- [ ] 运行前校验必需结果存在。
- [ ] 评估自动安装 Result Template 的 Preparation Macro。
- [ ] 将 Solver、frequency、mode count、Mesh 和 Boundary 建模为声明式目标状态。
- [ ] 区分 Profile 固定设置和允许 Warm 修改的参数化设置。
- [ ] 记录每个参数化设置的结果失效、重新网格和 Warm 复用规则。
- [ ] 对复合工程记录各 scope 的物理角色、依赖、数据交换和求解顺序。
- [ ] 分 scope 声明 Solver、参数和结果能力。
- [ ] 无法自动安装时保留权威 prepared 工程并验证能力。

验收标准：用户不需要为每次运行手动定义后处理步骤。

## Gate 9：残余 VBA Extension 盘点

只有前面各 Gate 完成后执行。

- [ ] 列出无法原生读取的结果。
- [ ] 列出无法在 Python 派生的结果。
- [ ] 评估特殊路径积分。
- [ ] 评估动态场采样。
- [ ] 评估 ModeRec 中必须依赖 CST API 的部分。
- [ ] 定义最小 Extension ABI。
- [ ] 扩展按 `Profile + Extension Set` 编译一次。
- [ ] 禁止每任务重新生成 VBA。
- [ ] 禁止扩展修改参数、重跑 Solver 或终止 CST。

验收标准：VBA Extension 清单只包含有证据证明无法替代的操作。

## Gate 10：迁移与删除

- [ ] WTC 切换到统一 Native Provider。
- [ ] default 切换已验证指标。
- [ ] TM020 切换已验证指标。
- [ ] 保留旧 VB 路径作为可比较回退。
- [ ] 运行真实 CST A/B 回归。
- [ ] 稳定运行一个发布周期。
- [ ] 停止扩展旧 `VBPostProcessor`。
- [ ] 删除被完全替代的 per-metric builder/readout。
- [ ] 删除被完全替代的 VB 后处理模块。
- [ ] 更新联合架构设计和原 TODO。

## Gate 11：离线 `.cst` 写回（非当前前置条件）

只有只读能力和原生结果迁移稳定后才执行。

- [ ] 定义允许修改的成员白名单，首个候选仅为 `Model/Parameters.json`。
- [ ] 保留非目标成员原始 header 和压缩字节。
- [ ] 使用同目录临时文件和原子提交，永不原地写权威工程。
- [ ] 验证目标成员 CRC/长度和所有非目标成员 SHA-256 不变。
- [ ] 修复 `cst_version` 对零参数工程的误判。
- [ ] 对目标 CST 版本执行 Open → Rebuild → Save → Reopen。
- [ ] 对代表工程执行求解与关键结果回归。
- [ ] 验证完成前只用于实验性 Cold Backend，不用于正在运行的 Warm 工程。

验收标准：写回失败不损坏输入，非目标成员保持不变，且所有目标 CST 版本真实回归通过。

## Go/No-Go 决策

满足以下条件时，某项指标可以移除运行时 VB 后处理：

-内部结果格式稳定可读；
-数值和单位通过对照；
-Warm 连续运行不串结果；
-目标 CST 版本均通过；
-错误和缺失结果可检测；
-Python 有自动化测试。

以下任一情况存在时保留 VBA 或标记暂不支持：

-只能依赖未确认的私有二进制格式；
-结果定义与当前物理公式不一致；
-需要 CST 场对象或内部积分 API；
-写入完成无法可靠判断；
-跨版本格式频繁变化；
-Warm/Cold 结果无法满足容差。

## 实施约束

- 本 TODO 是当前最高优先级，先于完整 Operation ABI 建设。
- 探针阶段只能只读，不修改生产 CST 工程。
- `.cst` 容器能力复用 `cst_version` 的思路但必须工程化；禁止维护第二套无测试解析器。
- `.rd0` 是结果交换数据；`.r0d/.r1d` 是 Result Template artifact，不能把模板设置或缓存字段当作当前结果。
- 不因“能够解析一次”就宣布格式稳定。
- 每个迁移结果必须保留来源、单位、Profile 和版本信息。
- 删除旧 VB 前必须有真实 CST 对照和至少一个发布周期的回退路径。
