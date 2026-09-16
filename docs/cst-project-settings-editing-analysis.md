# `.cst` 内部后处理与模拟设置修改分析

状态：可行性分析，尚未授权生产写回
日期：2026-09-17
前置知识：[CST `.cst` 项目文件知识库](./cst-project-file-knowledge-base.md)

P5.6/P6 已验证模板枚举、当前 Run 评估和 prepared HOM Profile 预检；模板新增/删除及离线生产写回仍未验证。当前实施状态见[当前状态与实施路线](./current-status.md)。

## 1. 总结判断

可以利用 `.cst` 内部成员读取并验证后处理和模拟设置，但“能够找到字段”不等于“直接修改该字段即可改变 CST 行为”。当前证据显示同一设置往往同时存在于 HISTORY LIST、JSON 摘要、项目元数据和私有二进制状态中。

推荐策略不是直接编辑多个内部文件，而是：

1. 用容器层读取、盘点和比较设置；
2. 用声明式 Project Profile 描述目标状态；
3. 在 Profile 构建阶段通过一次性的 CST Preparation Macro/COM 调用受支持 API；
4. 保存 prepared `.cst`；
5. 再用容器层验证实际成员、历史命令、结果能力和指纹；
6. Warm 运行阶段只修改预先参数化的控制参数，不动态重建后处理定义。

直接修改内部成员的建议等级：

| 对象 | 读取 | 直接修改 | 推荐方式 |
|---|---|---|---|
| `simulationproperties.json` | 高 | 低 | 用于摘要/验证；通过 CST API 修改真实设置 |
| `Model/Model.prj` | 中 | 禁止 | 只视为派生项目元数据 |
| `Model/3D/Model.mod` | 高 | 低 | 用于审计；通过 CST API 追加/更新历史操作 |
| `PC_integration.json` 输出值 | 中，需时序验证 | 禁止伪造 | 候选只读标量 Provider |
| `PC_integration.json` 输入/输出清单 | 高 | 低 | 用于能力清单；由 CST 保存过程生成 |
| `.r0d/.r1d` | 高：可拆分设置表和 VBA | 中低：注册语义待验证 | 优先由 CST Result Template API 创建 |
| `reportDB.json` | 中 | 低 | 主要是 Report/截图结构，不等同 Result Template 数据库 |
| 参数化 `fmin/fmax/nmodes` | 高 | Warm：高 | 预先绑定到 Solver 设置，运行时只改参数 |

## 2. 当前样本证据

### 2.0 单工程与复合工程必须分开建模

Enlarged/HOM 包含 `SP/<name>/Model/...` 子工程树，不是单一 `Model/...` 工程。观察到的 scope 包括 FME、FMEport、FMF、ME 和 Thermal；每个 scope 可拥有独立参数、HISTORY LIST、模拟设置、PC integration 和结果成员。

因此本文后续的“修改设置”必须带 scope：修改根工程的 `Model/3D/Model.mod` 不会自动修改 `SP/Thermal/Model/3D/...`，同名结果也不能跨 scope 合并。复合工程的后处理还可能依赖上游场源和多物理场求解顺序，必须在 Profile 中显式建模。

### 2.1 模拟设置存在多份表示

WTC 2022 的 `Model/simulationproperties.json` 包含：

- `active_solver = HF Eigenmode`；
- frequency minimum/maximum、表达式和单位；
- optimizer/sweep/single-run 标志；
- CPU/GPU/MPI 能力和用户加速设置；
- schema `version = 3`。

同一工程的 `Model/3D/Model.mod` 同时包含真正的历史命令：

```vb
ChangeSolverType "HF Eigenmode"
Solver.FrequencyRange "10", "100"
EigenmodeSolver.Reset
EigenmodeSolver.SetNumberOfModes "nmodes"
EigenmodeSolver.SetMeshType "Tetrahedral Mesh"
```

TM020 和 Pillbox 的历史中还观察到 Boundary、MeshSettings、accuracy、frequency target、loss handling 等完整命令。

因此 `simulationproperties.json` 更像便于集成/界面使用的结构化摘要，不能证明它是唯一权威状态。单改 JSON 可能造成“摘要已变、实际求解器未变”的分裂状态。

### 2.2 已存在参数化模拟设置

当前工程已展示正确方向：

```vb
Solver.FrequencyRange "fmin", "fmax"
EigenmodeSolver.SetNumberOfModes "nmodes"
EigenmodeSolver.SetFrequencyTarget "True", "fmin*1.2"
```

这意味着频率范围、模式数和目标频率等批次变量可在 prepared project 中一次性绑定到参数。Warm 任务只需修改 `fmin/fmax/nmodes` 等参数并 Rebuild，不需要每任务生成新的求解设置 VBA。

此模式是否保留 Mesh 复用收益，仍需按 Profile 实测；改变频率范围、模式数、边界或网格参数可能触发不同程度的重新网格或结果失效。

### 2.3 `PC_integration.json` 是新的结果候选入口

该成员包含：

- `inputVariables`：名称、类型、表达式或数值；
- `outputVariables`：结果树路径、长度、类型；
- 部分已求解工程还包含 `value`。

本仓库抽查结果包括：

| 工程示例 | 输出声明 | 带 value |
|---|---:|---:|
| Pillbox 2020 | 80 | 80 |
| M1 2020 | 60 | 60 |
| TM020 JP 2022 | 40 | 40 |
| WTC ALT 2022 | 11 | 11 |
| WTC 2022 | 15 | 0 |
| TM020 基础工程 | 0 | 0 |

这说明它可作为 `PCIntegrationScalarProvider` 的研究对象，但不能直接进入生产，因为：

- 同一 schema 中 value 可全部存在、部分存在或全部缺失；
- 未观察到可靠 task ID、参数哈希或写入完成标志；
- 保存过的值可能对应旧参数或旧求解结果；
- 结果路径和数量依赖 prepared project；
- 需要确认 CST Save 是否才会刷新该文件；
- 需要与 `.rd0`、CST GUI 和现有 VBA 输出逐项比较。

读取时必须同时验证当前参数快照、工程保存时机、结果树路径、单位和 Profile 指纹。任何字段缺失都应返回 `not-ready`，不能回退到陈旧值。

### 2.4 `.r0d/.r1d` 已确认为 Result Template artifact

内部 `.r0d/.r1d` 可确定包含：

- 格式版本和 CST writer/reader 版本字符串；
- `TemplateType`；
- `Action`；
- `ModeNumbers`；
- `AllModesCB`；
- 模板输入结果名；
- 坐标、表达式和标签等设置；
- 完整 VBA 源码，包括 UI、`Define` 和 `Evaluate0D/Evaluate1D` 算法。

匹配的 `.cst` 内嵌成员与 CST 展开目录同名文件字节完全一致，所以内部格式没有差别。扩展名中的 0D/1D 表示输出维度，而不是纯结果数据维度文件。

创建一个后处理项仍可能不仅需要新增一个成员，还要维护：

- 成员内部长度和类型编码；
- 对其他结果项的引用；
- `PC_integration.json` 输出清单；
- 结果树顺序/名称；
- 版本特定字段；
- 可能位于其他私有成员中的缓存或索引。

因此可以实现 artifact parser/writer，但“生成文件”和“在 CST 结果树中正确注册模板”仍是两个问题。现阶段后处理定义优先通过 CST Result Template/API 创建，容器层负责反编译、diff 和验证。详见 [Result Template 文件结构](./cst-result-template-format.md)。

### 2.5 `reportDB.json` 不是 Result Template 主数据库

样本中的 `Model/Reports/reportDB.json` 主要描述报告、截图、视图设置、UID 和资源路径。某些工程没有该成员，但仍拥有大量 `.r0d/.r1d` 后处理项。

所以修改 `reportDB.json` 不能替代创建 Result Template。它最多适用于报告展示层，而且还需要同步截图、UID 路径和相关资源。

## 3. 模拟设置修改的可行路径

### 3.1 路径 A：Profile Preparation API，推荐

通过稳定、版本化的 Preparation Macro 调用 CST API：

- Solver 类型；
- frequency range；
- number of modes；
- accuracy/target；
- Mesh 类型和 refinement；
- Boundary 和 Background；
- Result Template 定义；
- 必需的 0D/1D 输出。

然后保存 `.cst`，由 `cst_project` 生成 manifest 并验证 HISTORY LIST 和能力清单。

优点：让 CST 自己维护所有内部副本、缓存、历史和索引。宏只在 Profile 发布时运行一次，不进入每任务通信协议。

### 3.2 路径 B：参数化设置，推荐用于 Warm 可变项

将允许变化的求解设置绑定到 CST 参数：

```text
fmin, fmax, nmodes, frequency_target, mesh_control_*
```

Profile 声明每个控制参数：

- 类型、单位和范围；
- 关联的 HISTORY 命令；
- 是否使结果失效；
- 是否可能触发重新网格；
- Warm 复用是否经过验证。

运行时仍通过 CST 参数 API 修改，不直接写 `Parameters.json` 或 `Model.mod`。

适合：频率范围、模式数、部分收敛精度。  
需谨慎：Mesh 控制、Boundary、材料、Solver 类型。后者更适合作为不同 Profile，而不是同一 Warm Worker 的任务变量。

### 3.3 路径 C：直接编辑 JSON，暂不采用

理论上可以用窄范围 writer 替换 `simulationproperties.json`，但目前缺少以下证据：

- CST 打开时是否将其加载为真实设置；
- 是否会被 HISTORY/二进制模型状态覆盖；
- 是否需要同步 `Model.mod`、`Model.prj` 或其他成员；
- Rebuild 后是否仍保持修改；
- 不同版本 schema 是否兼容。

在完成受控差分和 CST 行为实验前，它只能用于沙盒研究。

### 3.4 路径 D：直接编辑 `Model.mod`，暂不采用

修改历史脚本文本看似更接近权威命令，但风险更高：

- 当前模型状态可能已由历史执行产生；
- 只改历史文本不代表当前内存/几何/求解对象已同步；
- 下一次 Rebuild 可能重放全部或部分历史，行为依赖 CST；
- disabled block、步骤边界和版本标记有私有语义；
- 其他模型状态成员可能仍与旧历史对应。

正确做法是让 CST API 创建或修改历史项，再保存工程。

## 4. 后处理设置修改的可行路径

### 4.1 预制 Result Template，首选

每个 Profile 在发布时安装稳定的 Result Template 集合。运行批次只读取已声明结果，不动态创建模板。

Profile 保存：

- 逻辑结果 ID；
- CST 结果树路径；
- template 类型；
- mode 规则；
- 单位、归一化、峰值/RMS 和相位规则；
- 可用读取源：`.rd0`、`PC_integration`、ASCII/CSV 或 VBA Extension；
- 依赖的其他结果项；
- CST 版本和 prepared project 指纹。

### 4.2 Preparation Macro 生成模板，推荐

对于希望“无需手工在 GUI 定义”的需求，可由 Python 根据声明式 Profile 生成一次性 Preparation Macro。它不是现有的 per-task 动态 VB：

- 输入是版本化 schema；
- 输出是 prepared `.cst`；
- 在发布/升级 Profile 时运行；
- 生成后进行能力和数值回归；
- 日常 Warm Worker 不再生成模板代码。

这样既保留自定义后处理能力，也避免 Python、VB、Pattern 和 reader 每任务联动。

### 4.3 Runtime VBA Extension，仅保留真正动态能力

只有下列需求保留运行时扩展：

- 参数决定采样路径或场对象，无法预先定义；
- 需要运行时访问 CST 场 API；
- 用户临时实验且不值得发布新 Profile；
- 现有 Result Template/导出格式无法表达。

即使保留，也应按 `Profile + Extension Set` 编译一次，而不是每任务拼接 VBA。

### 4.4 直接修改模板 artifact，仅限受控实验

修改已有 `.r0d/.r1d` 的设置表或 VBA 在结构上可行，但新增、改名、删除仍可能涉及结果树和 `PC_integration.json`。只能在副本中实验；即使 CST 能打开，也必须证明模板完成注册并被重新计算，而不是继续显示缓存结果。

## 5. 推荐的声明式设置模型

Project Profile 可增加：

```yaml
simulation:
  solver: HF Eigenmode
  frequency:
    minimum: {parameter: fmin, unit: MHz}
    maximum: {parameter: fmax, unit: MHz}
  number_of_modes: {parameter: nmodes}
  mesh_profile: tet_default_v1
  boundary_profile: electric_xy_magnetic_z_v1

results:
  - id: frequency
    tree_path: "3D\\Frequency (Mode 1)"
    kind: scalar
    unit: MHz
    sources: [rd0, pc_integration]
  - id: r_over_q
    tree_path: "3D\\R over Q beta=1 (Mode 1)"
    kind: scalar
    unit: ohm
    sources: [rd0, pc_integration]

preparation:
  schema_version: 1
  macro_version: eigenmode_profile_v1
  target_cst_versions: [2020.1, 2022.4]
```

这是概念 schema；正式字段应通过真实样本和现有配置迁移确定。

## 6. 受控差分实验

下一阶段最有效的方法不是继续猜格式，而是让 CST 只改变一个设置并保存 before/after 工程，再用容器 manifest 做差分。

每项实验必须：

1. 从同一个权威工程复制两个工作副本；
2. 只通过 CST GUI/API 修改一个设置；
3. 保存并关闭 CST；
4. 比较成员新增/删除、未压缩 SHA-256 和文本语义 diff；
5. 重新打开、Rebuild、求解；
6. 比较 UI 设置、Mesh、结果树和数值；
7. 在至少 CST 2020 与 2022 重复。

优先实验矩阵：

| 实验 | 观察目标 |
|---|---|
| 改 frequency minimum | `simulationproperties.json`、`Model.mod`、其他状态成员 |
| 改 number of modes | HISTORY、结果树、缓存失效 |
| 改 solver accuracy | JSON 是否记录、真实权威位置 |
| 开关 mesh adaptation | Mesh/HISTORY/私有状态变化 |
| 新增一个 0D Result Template | `.r0d`、PC integration、索引变化 |
| 修改 Result Template 表达式 | 二进制成员内部 diff、依赖更新 |
| 删除 Result Template | 成员、结果树和缓存清理 |
| 求解但不 Save / Save | `PC_integration.value` 和 `.rd0` 刷新时机 |
| 改参数后不求解 | 陈旧值检测能力 |

## 7. 新 Provider 候选

建议增加实验性的：

```text
PCIntegrationScalarProvider
```

它只能在满足以下条件时返回值：

- `outputVariables` 中精确匹配声明路径；
- `value` 存在且为合法有限数；
- prepared project/Profile 指纹匹配；
- 已确认 Save/Flush 时机；
- 当前参数哈希与求解参数一致；
- 同批次 `.rd0` 或现有 VB 基线通过对照；
- 单位和 mode 规则由 Profile 提供。

否则返回结构化 `ResultNotReady`，继续尝试 `.rd0` 或其他 Provider。不得因为值字段存在就无条件采用。

## 8. 对现有容器实现的额外警告

批量抽查确认 Enlarged/HOM 是多工程复合 `.cst`，分别观察到约 330 和 420 个成员，大部分位于 `SP/<subproject>/...`。`cst_version` 的 `member_list()` 可以扫出这些名字，但 `members_all()`/读取流程会出现 Deflate 错误。

直接原因是当前实现通过在整个原始字节流中反复搜索 `DE 03 04`，每次只前进 4 字节，而不是按中央目录和已解析成员长度跳到下一个真实 header。复合工程成员多、压缩数据大，压缩 payload 中偶然出现相同字节序列的概率显著增加，随后会把伪 header 当成成员并以错误边界解压。

正确修复是：

- 以 EOCD 定位中央目录；
- 严格解析每个 central-directory entry；
- 使用 entry 中的 local-header offset、压缩长度和文件名；
- 验证范围不重叠且全部落在文件边界内；
- 对 `(scope, relative member path)` 建立索引；
- 禁止用 `raw.find(member_name)` 读取成员，因为同名/相似名称可存在于多个 scope，也可能出现在 payload 中。

在完成上述修复前：

- 不得用当前解析器写回这些工程；
- 对复合工程只能把当前扫描结果作为诊断，不能当作完整可信 inventory；
- 不能把“其他小样本可读”外推为全项目兼容；
- read-only parser 的鲁棒性优先于设置写回。

另一个已确认限制是 `cst_version._parse_prj()` 按 `key=value` 解析，但样本 `Model.prj` 实际多为 `[Key]` 后跟下一行 value，因此当前 `project()` 会遗漏 `Results`、Mesh Type 等字段。必须先修正 parser，不能用其返回的空值作业务判断。

## 9. 最终建议

- **值得做：** 内部读取、差分、Profile 验证、PC integration 标量可行性实验。
- **值得做：** 用声明式 Profile 生成一次性 Preparation Macro，自动设置 Solver/Mesh/Boundary/Result Template。
- **值得做：** 将频率范围、模式数等稳定变量预先参数化，Warm 运行只改参数。
- **暂不做：** 直接修改 `simulationproperties.json` 并宣称真实 Solver 已改变。
- **不建议：** 直接拼装、复制或改写 `.r0d/.r1d` 创建后处理项。
- **不建议：** 每任务动态生成设置和后处理 VBA。
- **必须先做：** 单变量 before/after 差分、Save/Flush 时序测试和真实 CST 回归。
- **必须先做：** 将 root 与 `SP/<name>` 建模为独立 ProjectScope，并修复基于字节搜索的成员遍历。

换言之，内部格式最适合成为“可观测、可验证的工程状态”，而不是绕过 CST 的主要写接口。自动化写设置应放在 Profile Preparation 阶段并通过 CST 自身 API 完成。
