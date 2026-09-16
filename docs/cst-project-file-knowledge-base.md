# CST `.cst` 项目文件知识库

状态：基于 `D:\work\cst_version` 实现和当前仓库样本的已验证认知  
日期：2026-09-16

## 1. 结论

`cst_version` 的核心方向应纳入本项目：把 `.cst` 看作一个可盘点、可比较、可建立指纹的项目容器，而不是只能通过 CST GUI、COM 或运行时 VBA 访问的黑盒。

这项能力最适合承担：

- 离线读取参数、工程元数据和 HISTORY LIST；
- 盘点工程内已有的 Result Template 和结果成员；
- 为 Project Profile 生成能力清单和稳定指纹；
- 比较两个 prepared project 是否发生参数、历史或模型成员变化；
- 为 Cold Backend 准备项目副本。

它不能直接证明所有后处理都可被删除。`.r0d/.r1d` 已确认是 Result Template 定义 artifact，包含设置表和 VBA 算法，而不是最终物理结果文件；本项目已有的 `Direct_PPS_0D` 读取的是展开运行目录中的 `Result/<name>.rd0` 文本结果。

因此当前架构决策是：

1. 采用 `cst_version` 的容器读取、成员盘点、差异比较和窄范围写回思路；
2. 先将其工程化为经过测试的只读基础设施；
3. Warm Worker 仍通过 CST 受支持接口应用参数、Rebuild 和求解；
4. `.cst` 写回只用于离线 Project Preparation/Cold Backend，验证完成前不修改正在运行的 Warm 工程；
5. 原生结果仍按“已验证的文本/导出格式优先，私有二进制谨慎处理”推进。

另一个直接收益是参数发现不再需要 VB：`Model/Parameters.json` 已提供名称、表达式、求值结果和描述。Python 可以在不启动 CST、不占许可证、不 Save 工程的情况下生成参数清单。旧 `GetParamList.vb/readParamsT.vb` 应退出默认流程。

## 2. 证据等级

本文使用以下标签，避免把样本经验写成格式规范：

- **已验证**：由 `cst_version` 代码和当前仓库实际 `.cst` 样本共同确认；
- **实现假设**：`cst_version` 为兼容样本采用的规则，但没有厂商格式规范保证；
- **待验证**：目前只能观察到成员或字节，尚不能稳定解释语义。

`.cst` 是 CST 私有格式。即使结构类似 ZIP，也不应把当前实现当成 Dassault Systèmes 发布的长期兼容协议。

## 3. 容器结构

### 3.1 ZIP-like 外层

**已验证：** 当前样本使用 ZIP-like 目录和 Deflate 压缩，但关键头签名被改写：

| 结构 | 标准 ZIP | 当前 `.cst` 样本 |
|---|---:|---:|
| Local File Header | `PK 03 04` | `DE 03 04` |
| Central Directory | `PK 01 02` | `DE 01 02` |
| End of Central Directory | `PK 05 06` | `PK 05 06` |

**实现假设：** 局部头和中央目录比标准 ZIP 多 4 字节的厂商字段，导致文件名、CRC、长度和 local-header offset 的位置不能完全按 Python `zipfile` 的标准布局解释。`cst_version` 兼容了两种已观察到的文件名偏移。

因此不能简单地把 `DE` 改回 `PK`、用 `zipfile` 全量重打包，再认为 CST 一定可以接受。`cst_version` 早期保留了这种全量重建方法，但实际写回路径已改为保留原始成员和头字节、只修补目标成员及相关索引。

### 3.2 CST 版本信息

**已验证：** EOCD comment 可出现以下形式：

```text
-cst-version:2022:4:20220426-license:Commercial License
```

可提取 major、release、build 和 license 字段。它适合记录来源和建立兼容性矩阵，不应单独作为“格式必然兼容”的判断依据。

### 3.3 当前样本的兼容性

使用 `cst_version` 只读解析器抽查当前仓库：

| 样本 | EOCD 版本 | 参数 | HISTORY steps | 结果成员 |
|---|---:|---:|---:|---|
| WTC 2022 | 2022.4 | 17 | 66 | `.r0d/.r1d` |
| WTC 2020 | 2020.1 | 17 | 66 | `.r0d/.r1d` |
| TM020 | 2022.4 | 9 | 61 | 仅观察到 plot settings |
| Pillbox 2020 | 2020.0 | 7 | 61 | 多模式 `.r0d/.r1d` |
| Pillbox 2015 | 2015.0 | 0 | 60 | 多模式 `.r0d/.r1d` |

这说明 `cst_version` README 中“面向 CST ≥ 2019”的说法是保守支持范围，不是已证实的容器起始版本。至少一个 CST 2015 样本也采用 `DE` 容器并可读取历史和结果成员。参数为 0 只表示该样本没有可读参数项，不能据此判定解析失败。

## 4. 已知重要成员

| 成员/范围 | 当前认知 | 建议用途 |
|---|---|---|
| `Model/Parameters.json` | JSON；包含 `parameters` 列表，常见字段为 `name/expr/value/descr` | 参数清单、比较、Cold 项目准备 |
| `Model/3D/Model.mod` | 类 VBA 的 HISTORY LIST | 建模历史审计、步骤差异 |
| `Model/simulationproperties.json` | JSON；包含求解器和频率等配置 | Profile 元数据和能力检查 |
| `Model/Model.prj` | INI-like 文本 | 工程概况、网格/求解器辅助信息 |
| `Model/3D/*.sab`、`*.chksm` 等 | 几何或模型状态成员 | 模型成员指纹，不直接解释几何语义 |
| `Model/DS/*` | Design Studio/装配相关成员 | 项目指纹和差异盘点 |
| `Model/Reports/reportDB.json`、`Model/Reports/*` | 报告定义及资源 | 识别 prepared project 能力 |
| `Model/3D/*.r0d`、`*.r1d` | Result Template artifact：长度前缀头、设置表、VBA 源码 | 模板盘点、反编译、diff；不作为最终数值文件 |
| `Model/3D/plot_settings.rps` | 绘图设置/结果相关私有成员 | 不作为物理结果来源 |

成员名在不同 CST 版本、Solver、模板和语言环境中可能变化。代码应通过“精确已知路径 + 可声明的候选规则”定位，不能把一次扫描到的名字写死为通用标准。

### 4.1 多工程复合结构

Enlarged/HOM 不是普通单工程样本，而是包含多个子工程的复合 `.cst`。已观察到：

```text
Model/...                         # 根工程
SP/FME/Model/...                  # 子工程
SP/FMEport/Model/...
SP/FMF/Model/...
SP/ME/Model/...
SP/Thermal/Model/...
SP/FME.cst、SP/FMF.cst ...        # 子工程相关容器成员/标记
```

每个子工程命名空间都可能拥有自己的：

- `Model/Parameters.json`；
- `Model/3D/Model.mod`；
- `Model/Model.prj`；
- `Model/PC_integration.json`；
- `ModelCache/*`；
- `.r0d/.r1d` 和场源文件；
- Solver、Mesh、Boundary 和结果能力。

因此不能再把 `.cst` 抽象为“一个 Model + 一套结果”。正确模型是：

```text
CstProject
  ├─ root scope: Model/
  └─ subproject scopes: SP/<name>/Model/
```

所有参数、历史、设置和结果 API 都必须接受 `ProjectScope`。逻辑键应为 `(scope, member_path)` 或 `(scope, result_id)`，不能仅用 `Frequency (Mode 1)` 等局部名称，否则不同子工程会发生碰撞。

复合工程还可能表达电磁、热、机械或端口等多物理场链路。仅观察目录名不能推断求解顺序和耦合关系；Profile 必须显式记录子工程角色、依赖和执行顺序，并由 CST API/真实工程验证。

## 5. 参数表

### 5.1 读取

`Model/Parameters.json` 的顶层通常含 `parameters`，每项可含：

```json
{
  "name": "Fx",
  "expr": "30-Fxx",
  "value": "15",
  "descr": "Width of Low Ferrite Room"
}
```

应保留字符串形式的 `value` 和 `expr`。例如 `0.00`、`00.1` 与数值等价的规范化字符串并不相同，随意格式化会产生无意义 diff，甚至影响 CST 行为。

### 5.2 表达式计算

`cst_version` 使用 Python AST 白名单计算基本算术、部分数学函数、常量和参数引用，不调用 `eval`。这是正确的安全方向，但它只是 CST 表达式语言的一个子集。

推荐规则：

- 默认只修改表达式，让 CST 自己完成最终求值；
- Python 重算只能用于已覆盖语法的预检、比较或明确启用的 Cold 准备；
- 未识别函数、单位、条件表达式或循环依赖必须返回 `unresolved`，禁止猜值；
- 保留原数值字符串，只有数值确实变化时才写新值；
- 以真实 CST 打开/Rebuild 作为最终语义验证。

### 5.3 替代 VB 参数发现

旧流程：

```text
复制 .cst
  → 启动 CST
  → 运行 readParamsT.vb / GetParamList.vb
  → 输出临时文本
  → Python 解析文本
  → CST Save / Quit
```

推荐流程：

```text
读取 .cst::Model/Parameters.json
  → 规范化 ParameterRecord
  → 生成/校验 params.json
```

复合工程必须指定 `ProjectScope`，例如读取 `SP/FME/Model/Parameters.json`，不能默认搜索并取第一个同名成员。

兼容旧 `params.json` 时要注意：旧 VB 使用 `GetParameterSValue`，导出的更接近参数表达式。适配旧 schema 时应将：

- `expr` 映射到旧 `value`；
- `value` 保留为 `evaluated_value`；
- `descr` 完整映射到 `description`。

旧文本解析通过空格拆列，带空格的 description 实际会被截断；直接 JSON 读取可修复这一信息损失。

长期 schema 不应继续用“是否能转成浮点数”推断 `fixed/optimizable`。表达式、当前求值和是否参与优化是三个独立概念，应分别声明。

## 6. HISTORY LIST

`Model/3D/Model.mod` 保存类 VBA 的建模历史。样本中步骤边界由形如 `'@ ...` 或 `''@ ...` 的注释标记引出，后续代码块直到下一步骤。

`cst_version` 提取：

- 顺序号；
- 注释；
- 从首个有效命令归纳的标题；
- 完整代码块；
- 是否全部被注释，从而推断该步骤已停用。

这适合人类审阅和结构化 diff，但步骤注释并不是稳定 ID。若两个版本重命名注释、插入重复标题或大范围移动步骤，基于 `SequenceMatcher` 的对齐可能产生“删除 + 新增”而不是精确移动。因此正式指纹应同时保留：

- `history_sha256`：整个 `Model.mod` 的内容哈希；
- `history_steps`：用于展示的结构化步骤；
- 原始文本 diff：用于最终审计。

## 7. 项目与模型指纹

`cst_version` 对 `Model/3D` 和 `Model/DS` 中排除部分已知结果/报告成员后的内容逐项求哈希，再汇总为模型指纹。这个思想可用于快速判断 prepared project 是否漂移。

需要收紧术语：该集合可能包含几何之外的模型配置成员，因此更准确的名称是 `model_state_fingerprint`，不应宣称“相同即几何在数学意义上完全相同”。

本项目建议保存四层身份：

1. `project_sha256`：整个 `.cst` 文件的字节身份；
2. `member_manifest_sha256`：成员名、未压缩长度和 SHA-256 的有序清单；
3. `model_state_fingerprint`：排除已知结果/报告后的模型相关成员；
4. `history_sha256` 与规范化参数清单哈希。

MD5 可用于非安全的快速变化检测，但新实现统一使用 SHA-256，避免同一系统中混用哈希语义。

## 8. 工程内部结果的真实边界

### 8.1 `.r0d/.r1d` 是 Result Template，不是 `.rd0` 结果

当前样本的 `.cst` 容器中存在：

```text
Model/3D/Frequency (Mode 1).r0d
Model/3D/TTF.r1d
```

它们由长度前缀 header、UI/脚本设置键值表和 VBA 模板源码组成。匹配工程中，`.cst` 成员与展开工作目录文件逐字节一致。`r0d/r1d` 对应模板输出维度；具体结构见 [CST `.r0d/.r1d` Result Template 文件结构](./cst-result-template-format.md)。

当前 `Direct_PPS_0D` 读取：

```text
<run-dir>/Result/<result-name>.rd0
```

这是另一条路径。知识库和代码必须使用准确扩展名：

- `.rd0`：本项目已知的运行目录文本标量候选；
- `.r0d/.r1d`：Result Template 定义，目前用于解析设置/VBA、inventory 和 diff，不直接返回物理结果；
- ASCII/CSV：通过 CST 明确导出的稳定交换格式。

### 8.2 对后处理架构的影响

`cst_version` 已证明“不启动 CST 也能知道工程准备了哪些结果模板”，这能解决 Project Profile 的能力发现和漂移检查；它尚未证明“不启动 CST 就能可靠读取全部物理结果”。

推荐优先级不变：

```text
已验证的 .rd0 / ASCII / CSV
  → Python 派生
  → 经多版本样本验证的容器 Codec
  → 最小 Runtime VBA Extension
```

禁止仅凭文件名存在就把结果标记为 ready。还必须验证任务 ID/参数哈希、求解完成、文件稳定、值和单位。

## 9. 安全写回策略

`cst_version` 当前最有价值的写回做法是“外科手术式替换”：

1. 保留所有未修改成员的原始 local header 和压缩字节；
2. 只重新压缩被替换的成员；
3. 更新该成员的 CRC、压缩/未压缩长度；
4. 重新计算后续 local-header offsets；
5. 修补中央目录和 EOCD；
6. 重新打开输出文件做基本可读性检查。

本项目采用这个原则，但必须增加工程级安全网：

- 永不原地覆盖输入 `.cst`；
- 在同目录写临时文件，完成全部验证后使用原子替换；
- 默认保留输入和 SHA-256，不把备份覆盖掉；
- 校验成员数量、顺序、名称、CRC 和未压缩内容哈希；
- 除声明的目标成员外，其他成员必须逐字节或逐成员哈希一致；
- 参数写回后验证 JSON 结构、名称唯一性和预期 diff；
- 用 CST 目标版本执行 Open → Rebuild → Save → Reopen 冒烟测试；
- 对代表工程执行求解和关键结果回归；
- 失败时留下临时文件和诊断，不替换权威工程。

正在被 CST 打开的 Warm 工作副本不可由外部代码改写。Warm 参数更新仍走 CST 自动化接口，否则会绕过 CST 内存状态、缓存和 Mesh 复用语义。

## 10. 对 `cst_version` 的工程评价

### 可直接继承的设计思想

- 容器优先，而不是依赖 GUI 自动化读取静态信息；
- 参数、历史、模型状态分层比较；
- 完整项目快照与内容寻址对象；
- 编辑在内存完成，输出新文件；
- AST 白名单而非 `eval`；
- 保留非目标成员的窄范围写回；
- 输出后重新解析，尽早拒绝损坏文件。

### 不能原样复制的实现限制

- `cst_version` 当前是单文件脚本，不是可声明依赖的包；
- 目录中没有 Git 元数据和自动化测试，README 声明缺少回归证据；
- 整个文件一次读入内存，对大型含结果工程成本较高；
- 部分成员定位依赖字节搜索和已观察偏移，恶意或异常文件可能误定位；
- 写文件后只验证“可重新读取且参数非空”，会误判合法的零参数项目，也不足以证明 CST 可打开；
- 输出写入不是临时文件 + 原子提交；
- model fingerprint 使用成员 MD5，且“模型成员”分类仍是经验规则；
- `Model.prj` 解析会丢弃 section 和重复 key 信息；
- 参数表达式支持的是子集，不能等同完整 CST 语法；
- `.r0d/.r1d` 结构可解析为设置表和 VBA，但模板注册、重命名和删除的关联语义尚未验证。

因此应复用知识和算法，经测试后提取为本项目模块；不应在生产代码中通过 `sys.path` 直接导入相邻目录的 `cstv.py`，也不应复制后形成两个独立分叉。

## 11. 推荐模块边界

建议在当前工程形成一个独立的 `cst_project` 子系统：

```text
csttool/cst_project/
  container.py       # 严格只读容器、成员表、按名读取
  manifest.py        # ProjectManifest 与多层 SHA-256
  parameters.py      # 参数 schema、diff、受限表达式预检
  history.py         # Model.mod 步骤视图和原始 diff
  results.py         # 结果成员 inventory；Codec 必须显式注册
  writer.py          # 离线窄范围写回，默认禁用
  validation.py      # 结构、成员保持性和 CST 集成验证
```

外部稳定对象建议包括：

- `CstProject.open(path, mode="read")`；
- `ProjectScope` 与 `CstProject.scopes()`，区分根工程和 `SP/<name>` 子工程；
- `ProjectManifest`；
- `ParameterRecord` / `ParameterDiff`；
- `HistoryStep`；
- `ResultAsset`，其状态为 `inventory-only`、`decoded` 或 `unsupported`；
- `ProjectCapabilityReport`；
- `ProjectEditPlan`，显式列出允许修改的成员。

`CSTManager`、Warm Worker 和后处理 Provider 只依赖这些稳定对象，不依赖 ZIP 偏移、JSON 键顺序或某个 GUI 工具。

## 12. 与 Project Profile 的结合

每个 prepared project 在 Profile 中记录：

- CST major/release/build；
- `project_sha256`；
- `member_manifest_sha256`；
- `model_state_fingerprint`；
- `history_sha256`；
- 参数 schema/hash；
- Result Template/结果成员 inventory；
- 已验证 `.rd0`、ASCII/CSV 输出契约；
- 必需的 Runtime VBA Extension；
- 已通过的 CST 版本与回归样本。
- 子工程 scope、物理角色、依赖和求解顺序。

运行前比较实际工程和 Profile：

- 完全匹配：正常运行；
- 只有允许的参数值变化：记录后运行；
- HISTORY、模型状态或结果能力漂移：拒绝或要求重新发布 Profile；
- 未知成员变化：默认告警，不静默接受。

这样，工程内手工定义 Result Template 不再是不可见前置条件，而成为可扫描、可版本化、可验证的 Profile 能力。

## 13. 分阶段采用路线

### 阶段 A：只读安全网

- 从 `cst_version` 提取最小只读解析核心；
- 用当前仓库 2015/2020/2022 样本建立 golden tests；
- 生成成员、参数、历史和结果资产清单；
- 任何未知布局都返回明确的 `UnsupportedCstLayout`。

### 阶段 B：Profile 与结果盘点

- 把 manifest/fingerprint 接入 Project Profile；
- 自动检查 prepared project 的参数和结果能力；
- 明确区分 `.rd0` 与 `.r0d/.r1d`；
- 为已验证的文本结果建立 Native Provider。

### 阶段 C：离线受控写回

- 仅允许 `Model/Parameters.json` 等白名单成员；
- 实施临时文件、原子提交、成员保持性检查；
- 通过目标 CST 版本的真实打开/Rebuild/求解回归后，才用于 Cold Backend。

### 阶段 D：可选二进制 Codec

- 只有在多个 CST 版本、多个 Solver 和足够样本中验证字段语义后，才注册 `.r0d/.r1d` Codec；
- Codec 必须带适用版本、结果类型、单位规则和拒绝条件；
- 未知版本绝不“尽力猜测”。

## 14. 当前不可越过的边界

- 不把私有容器观察结果称为官方格式规范；
- 不因能列出 `.r0d` 就声称能读取其物理值；
- 不修改 CST 正在使用的 Warm 工程文件；
- 不用全量标准 ZIP 重打包替代窄范围保真写回；
- 不在没有 CST 集成测试的情况下删除旧参数/后处理回退路径；
- 不把模型成员哈希等同于电磁结果等价性；
- 不按文件扩展名或成员名存在判断求解已完成。

## 15. 相关文档

- [CST `.r0d/.r1d` Result Template 文件结构](./cst-result-template-format.md)
- [`.cst` 内部后处理与模拟设置修改分析](./cst-project-settings-editing-analysis.md)
- [Warm CST 与原生结果知识库](./cst-warm-native-results-knowledge-base.md)
- [CST 原生结果优先 TODO](./cst-native-results-todo.md)
- [CST VBA 与 Python 联合架构设计](./vba-python-integration-design.md)
- [CSTManager 设计文档](./cstmanager-design.md)
