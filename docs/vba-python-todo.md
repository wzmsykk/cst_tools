# CST VBA 与 Python 联合改造 TODO

状态：历史完整改造规划；当前延期
日期：2026-09-17
当前实施入口：[CST Tools 当前状态与实施路线](./current-status.md)

设计依据：[CST VBA 与 Python 联合架构设计](./vba-python-integration-design.md)

> 执行顺序更新：本 TODO 不再作为当前阶段编号。项目已按更小的 P2.5–P6 路径完成协议、Warm/HOM 原生结果和最小 Profile Gate。完整 Operation ABI、Manifest、Schema 和批量 VB 改写继续延期，只有第二个真实 Profile 出现共同需求后才重新裁剪。

## 当前基线

- [x] 建立默认单元测试与 CST 集成测试隔离。
- [x] CSTManager 使用固定 Worker 池和明确生命周期。
- [x] 当前后处理生成器改为声明式注册表。
- [x] `defaultPPS.json`、`TM020PPS.json`、`WTCPPS.json` 可生成。
- [x] 当前默认测试 76 个通过，11 个 CST 集成测试隔离（2026-09-17）。
- [x] `hom-2022-v1` 最小 Profile、五个模板预检和 fail-fast Gate 已完成。
- [x] CSTManager API 和设计文档已建立。
- [ ] 新联合 ABI、Operation 包和 Result Codec 尚未实现。
- [ ] 当前声明式 `VBPostProcessor` 仅作为迁移基线，不是最终架构。

## P0：冻结联合契约

目标：在继续修改生产 VB 或生成器前确定稳定边界。

- [ ] 编写 `operation-manifest-v1.schema.json`。
- [ ] 编写 `pipeline-v1.schema.json`。
- [ ] 定义 Generator ABI v1 的统一 VB 函数签名。
- [ ] 定义 Task Protocol v1 的任务、终止和结果文件格式。
- [ ] 定义 `scalar-v1` Codec。
- [ ] 定义 `mode-map-v1` Codec。
- [ ] 定义 `table-v1` Codec。
- [ ] 定义 `fileset-v1` Codec。
- [ ] 冻结第一版错误代码表。
- [ ] 定义错误到重试、Worker 重启策略的映射。
- [ ] 冻结 `prepare → solve → postprocess` Pipeline 模型。
- [ ] 完成一次设计评审并将本文档状态改为“已接受”。

验收标准：

- Schema、协议样例和错误表可以独立评审；
- 不依赖某个具体 VB 文件或 Python 类；
- 至少能完整表达现有 default、TM020 和 WTC 配置。

## P1：建立基础框架

依赖：P0。

- [ ] 创建 `cst_operations/` 目录结构。
- [ ] 实现 Manifest 加载器。
- [ ] 实现 JSON Schema 校验。
- [ ] 实现 `OperationRequest` 数据模型。
- [ ] 实现 `PipelineSpec` 数据模型。
- [ ] 实现 Operation 版本解析。
- [ ] 实现依赖拓扑排序和去重。
- [ ] 实现 Profile 能力校验。
- [ ] 实现统一 VBA 调用生成。
- [ ] 实现 `build-manifest.json`。
- [ ] 记录生成器、Profile、Operation 和源文件哈希。
- [ ] 增加未替换占位符检查。
- [ ] 增加 `Sub Main` 唯一性检查。
- [ ] 增加 entrypoint 存在性检查。
- [ ] 增加重复公共符号检查。
- [ ] 增加空生产脚本检查。

验收标准：

- 使用假 Operation 可以生成确定性的 `main.bas` 和 Build Manifest；
- 输入顺序不影响依赖输出顺序；
- 错误配置在启动 CST 前失败。

## P2：实现 `eigen.scalar@1` 纵向样板

依赖：P0、P1。

- [ ] 创建 `eigen_scalar/operation.json`。
- [ ] 创建符合 ABI v1 的 `eigen-scalar.vb`。
- [ ] 支持 Frequency。
- [ ] 支持 Q-Factor。
- [ ] 支持 Total Loss。
- [ ] 支持 Total Energy。
- [ ] 实现 `scalar-v1` 输出。
- [ ] 实现 `mode-map-v1` 输出。
- [ ] 实现对应 Python Codec。
- [ ] 建立参数校验测试。
- [ ] 建立生成调用区 Golden Test。
- [ ] 建立结果样本解析测试。
- [ ] 使用最小 CST 工程完成 Contract Test。

验收标准：

- 同一 Operation 同时支持单模式和全模式；
- 修改 VB 内部实现但保持契约时，Python 测试无需修改；
- 真实 CST 输出可以被标准 Codec 解码。

## P3：旧 PPS 兼容层

依赖：P2。

- [ ] 实现 `legacy_pps_to_pipeline()`。
- [ ] 映射 Frequency、Q、Loss 和 Energy。
- [ ] 映射 R/Q 和 Shunt Impedance。
- [ ] 映射 ModeRec_All。
- [ ] 映射 Direct_PPS_0D。
- [ ] 为历史拼写 `Shunt_Inpedence` 提供兼容别名。
- [ ] 保证三套现有 PPS 转换后语义一致。
- [ ] 对无法转换的旧配置给出明确错误。

验收标准：

- 三套现有 PPS 不需要人工修改即可转换；
- 转换结果包含明确 Operation 版本；
- 兼容层之外不再传播旧 method 字符串。

## P4：迁移复杂后处理

依赖：P2、P3。

### `eigen.complex-axis@1`

- [ ] 封装 R/Q。
- [ ] 封装 Shunt Impedance。
- [ ] 明确 axis、offset 和单位。
- [ ] 使用标准 Codec。
- [ ] 建立零偏移及非零偏移 CST Contract Test。

### `mode.recognition@1`

- [ ] 梳理 ModeRec 的最小输入输出契约。
- [ ] 把场采样与模式分类结果分开。
- [ ] 明确结果单位和缺失模式语义。
- [ ] 建立 TM020 参考工程测试。

### `direct.0d@1`

- [ ] 把 `.rd0` 读取建模为 `python-reader` Operation。
- [ ] 校验结果文件存在性和数值格式。
- [ ] 建立 WTC 参考结果测试。

### 场导出

- [ ] 设计 `field.export@1`。
- [ ] 选择 `table-v1` 或 `fileset-v1`。
- [ ] 修复或隔离 `FieldValue.vb`。
- [ ] 评估 `3DField.vb`。
- [ ] 评估 `R_over_Q_weird.vb` 是否保留。
- [ ] 删除或实现空的 `Loss.vb`。

## P5：Task Protocol 和 Worker Runtime

依赖：P0；可与 P2 部分并行，但合并前必须完成集成。

- [ ] 实现 `.task.tmp → .task` 原子提交。
- [ ] 实现结果临时文件原子提交。
- [ ] 增加协议头和版本。
- [ ] 增加 task ID、job name、Worker ID。
- [ ] 增加参数数量和完整性检查。
- [ ] 统一成功与失败结果。
- [ ] Worker Runtime 统一产生任务级状态。
- [ ] Operation 禁止直接写 `.success/.failure`。
- [ ] 支持标准错误代码。
- [ ] 支持重试建议和 Worker 重启建议。
- [ ] 增加任务超时信息。
- [ ] 增加安全终止协议。

验收标准：

- VB 不会读取尚未写完的任务文件；
- 任意失败都有结构化结果；
- Python 可以区分模型错误、求解错误和 Worker 错误。

## P6：VB 生产规范

- [ ] 所有生产 VB 使用 `Option Explicit`。
- [ ] 修正 `Sub`/`Function` 混用。
- [ ] 所有参数显式声明 `ByVal`/`ByRef`。
- [ ] 清理不必要的 `Variant`。
- [ ] 统一 `CSTPP_` 公共符号前缀。
- [ ] 建立公共错误处理模块。
- [ ] 建立公共结果写入模块。
- [ ] 禁止无边界 `On Error Resume Next`。
- [ ] Operation 不允许 `Quit`。
- [ ] Operation 不允许写任务级标志。
- [ ] 添加 VB 静态检查测试。

## P7：Profile 和 Pattern 收敛

依赖：P2、P4、P5。

- [ ] 定义 Profile Schema v1。
- [ ] 建立 default Profile。
- [ ] 建立 TM020 Profile。
- [ ] 建立 WTC Profile。
- [ ] 建立 Pillbox Profile。
- [ ] 建立 Enlarged/HOM Profile。
- [ ] 抽取公共 Solver Runtime。
- [ ] 抽取公共 Worker Runtime。
- [ ] 明确固定后处理和配置后处理边界。
- [ ] 合并 `copper/pillbox/pillbox_tet/POP.pattern`。
- [ ] 合并 `M1_fieldexport/pillbox_fieldexport.pattern`。
- [ ] 合并 `Enlarged_Mode/HOM_Mode.pattern`。

验收标准：

- 每个生产项目只引用一个版本化 Profile；
- Profile 不复制公共 Worker 和 Solver 实现；
- 同一物理量不会被固定与动态后处理重复输出。

## P8：前处理整理

- [ ] 将 `cst_version` 的容器/参数读取核心提取为 `csttool.cst_project`。
- [ ] 实现 `CstParameterProvider`，按 `ProjectScope` 读取 `Model/Parameters.json`。
- [ ] 定义 `ParameterRecord(name, expression, evaluated_value, description, optimizable)`。
- [ ] 为旧 `params.json` 提供兼容适配器；旧 `value` 使用 `expr`，避免改变现有优化变量语义。
- [ ] 使用 CST 2015/2020/2022 和复合工程建立参数读取 golden tests。
- [ ] 从默认流程删除 `GetParamList.vb` 和 `readParamsT.vb` 调用。
- [ ] 将 `preprocess_cst.py` 收缩为兼容层，不再负责参数发现。
- [ ] 拆分“参数读取”和“工程 Preparation”，禁止继续用一个 VB 流程同时完成两者。
- [ ] Prepared 工程直接复制并读取参数，完全跳过 CST 预处理进程。
- [ ] 未 Prepared 工程仅运行会修改状态的 Preparation Macro，保存后由 Python 读取参数。
- [ ] 明确 `fmin`、`fmax` 和 `nmodes` 的所有权。
- [ ] 评估 `modelPreprocessT.vb`。
- [ ] 评估 `preparamize.vb`。
- [ ] 清理未使用的动态前处理路径。

验收标准：参数发现不启动 CST、不占许可证、不生成临时 BAS/TXT、不修改或保存源工程；只有确需改变工程状态时才启动 Preparation Macro。

## P9：测试与真实 CST 验收

- [ ] Manifest Schema 测试。
- [ ] Operation ID 和版本唯一性测试。
- [ ] 依赖解析测试。
- [ ] Generator Golden Test。
- [ ] Result Codec 测试。
- [ ] VB 静态检查。
- [ ] 每个 Operation 的最小 CST Contract Test。
- [ ] 单任务端到端测试。
- [ ] 多 Worker 并发测试。
- [ ] 失败重试与 Worker 重启测试。
- [ ] CST 超时测试。
- [ ] 强制退出和恢复测试。
- [ ] default Profile 回归。
- [ ] TM020 Profile 回归。
- [ ] WTC Profile 回归。
- [ ] Pillbox/Enlarged/HOM 回归。

## P10：完成迁移后清理

依赖：所有生产 Profile 通过真实 CST 验收。

- [ ] 所有算法改用 `SimulationTask` 和 `run_batch()`。
- [ ] 删除旧三参数 `addTask`。
- [ ] 删除 `runWithx()`。
- [ ] 删除旧每指标 builder/readout。
- [ ] 删除重复 Pattern。
- [ ] 将 `utils/modes_v*.bas` 移入 `legacy/`。
- [ ] 删除未使用和无法编译的 VB。
- [ ] 删除旧前处理生成路径。
- [ ] 发布迁移说明。
- [ ] 更新用户、开发和部署文档。

## 实施规则

- P0 未冻结前，不继续批量改写生产 VB。
- 每个 PR/提交只迁移一个 Operation 或一个明确基础能力。
- VB、Manifest、Codec 和测试必须同批提交。
- 不兼容变化必须升级版本，禁止静默同步修改两端。
- 删除旧实现前必须有真实 CST 回归证据。
- 当前 `VBPostProcessor` 保留为兼容层，不继续承担新架构职责。
