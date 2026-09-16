# Warm CST 与原生结果知识库

状态：当前架构认知  
日期：2026-09-16

项目文件结构、参数表、HISTORY LIST、指纹和安全写回边界详见 [CST `.cst` 项目文件知识库](./cst-project-file-knowledge-base.md)。后续 `.cst` 访问按该文档的容器化、只读优先和窄范围写回原则实施。

## 1. 核心背景

项目使用运行时 VBA 的首要原因不是后处理，而是保持 CST 工程和进程处于 Warm 状态。对于相似几何模型，运行时修改参数、Rebuild 并继续求解，通常比为每个参数点从独立 CST 文件重新开始 Mesh 更快。

这一性能收益对数百至数千次优化任务可能非常重要，但它不意味着所有后处理都应通过运行时 VBA 完成。

应将两个问题分开：

1. 是否保留 Warm CST Worker；
2. 是否保留动态 VBA 后处理体系。

当前判断是：优先保留前者，尽量缩小后者。

## 2. 当前实现的价值与成本

### 有价值的部分

- CST 工程只打开一次；
- 连续修改参数并 Rebuild；
- 相似模型可以减少 Mesh 生成成本；
- 多个 Worker 可以并行运行；
- Worker 失败或累计运行一定次数后可以重建；
- Python 负责优化算法和任务调度。

### 高维护成本部分

- Python 动态拼接大量 VB；
- 每个物理量拥有独立 builder 和 reader；
- Python 知道 VB 文件名、函数名和参数位置；
- Pattern、后处理库和 Python 配置必须同步修改；
- 多套重复 Pattern 难以保持一致；
- 错误只能通过松散文件和字符串表达；
- 真实正确性难以在没有 CST 的环境中验证。

真正值得保留的是 Warm 执行能力，而不是当前全部交互复杂度。

## 3. 已有可行证据

WTC 流程已经使用 `Direct_PPS_0D`，由 Python 直接读取 CST 工程中的 `.rd0` 标量结果。这证明至少部分指标可以跳过运行时 VBA 后处理。

`cst_version` 还证明现代 `.cst` 可作为 ZIP-like 容器进行离线盘点：可读取 `Model/Parameters.json`、`Model/3D/Model.mod`、工程配置及结果成员清单。当前仓库的 CST 2015、2020、2022 样本均观察到同类 `DE` 容器结构。

需要严格区分：

- `Result/<name>.rd0` 是当前代码已经读取的运行目录文本标量；
- `.cst` 内的 `Model/3D/*.r0d`、`*.r1d` 是 Result Template 定义，保存设置表和 VBA 算法，不是最终物理值文件。

可能适合直接读取的结果包括：

- Frequency；
- Q-Factor；
- Total Loss；
- Voltage；
-标准 R/Q；
- Shunt Impedance；
-工程内 Result Template 已生成的峰值和派生标量。

是否可替代现有 VB，仍需逐项验证文件格式、单位、模式编号、写入时机和跨版本稳定性。

## 4. 推荐的结果获取层级

每个 `ResultRequest` 按以下顺序解析：

```text
NativeResultProvider
        ↓ 不可用
PythonDerivedProvider
        ↓ 不可用
RuntimeVbaProvider
        ↓ 不可用
启动前报告能力缺失
```

### NativeResultProvider

直接读取 CST 求解后已经生成的稳定结果：

- 文本 `.rd0`；
- ASCII/CSV；
-项目 Result Template 输出；
-经过验证的其他稳定文件。

这是默认首选路径。

### PythonDerivedProvider

使用原生标量或表格结果在 Python 中计算：

-归一化指标；
-目标函数；
-约束；
-多个标量的组合；
-模式排序和筛选中不依赖 CST 场对象的部分。

Python 计算必须明确公式、单位、峰值/RMS、相位和归一化定义。

### RuntimeVbaProvider

只保留给必须访问 CST 内部场 API 的功能：

-特殊路径积分；
-动态场采样；
-`VectorPlot3D` 操作；
-无法通过原生结果或 Python 重建的模式识别；
-实验性用户扩展。

它是显式、可选、版本化的扩展路径，不是默认后处理路径。

## 5. 推荐执行链

目标流程：

```text
Python 提交参数
  → Warm VB Worker 应用参数
  → Rebuild
  → Solver.Start
  → Save/Flush Results
  → 写任务级 Solver Done
  → Python 读取或快照结果
  → Python 派生计算
  → 必要时运行可选 VBA Extension
  → 完成本任务
  → Worker 接收下一任务
```

运行时 VB 最终只负责：

-参数应用；
-Rebuild；
-求解器控制；
-结果保存/刷新；
-完成通知；
-可选扩展 Hook。

## 6. 关键同步约束

直接读取内部结果的最大风险不是解析，而是时序。

必须保证：

- Solver 已完成；
- CST 已刷新或保存结果；
-完成标志属于当前 task ID；
-结果文件不是上一任务遗留；
-Python 已完成读取或快照后，Worker 才开始下一任务。

推荐单 Worker 内串行：

```text
solve → result ready → read/snapshot → acknowledge → next task
```

跨 Worker 仍然可以并行。

任务和完成标志应包含：

-协议版本；
-task ID；
-job name；
-参数哈希；
-Worker ID；
-工程/Profile 版本；
-结果是否已经保存。

## 7. 文件格式边界

优先读取：

-已经确认是文本的 `.rd0`；
-CST 自动导出的 ASCII/CSV；
-项目内稳定 Result Template 输出。

`.cst` 容器读取可用于参数、HISTORY LIST、工程元数据、结果资产 inventory 和 Project Profile 指纹。它不自动提升私有结果成员的稳定性等级。

谨慎处理：

-`.r0d`、`.r1d` 模板的直接注册/改名/删除关联关系；
-`Model.rdb`、`Model.res`、`Storage.sdb`；
-依赖 CST 版本的私有数据库；
-CST 仍持有或尚未写完的文件。

其中 `.r0d/.r1d` 是模板定义，已验证文本 `.rd0` 是结果交换文件，文档、配置和代码不得混写。

不要为了删除 VBA 而引入未经文档化、跨版本不稳定的二进制解析器。

## 8. Project Profile

完全依赖工程内结果会带来“需要手工配置 CST 工程”的问题。解决方式不是恢复所有运行时后处理，而是引入版本化 Project Profile。

Profile 应声明：

-准备好的 CST 模型；
-Solver 配置；
-可提供的原生结果；
-结果路径、单位和 Codec；
-可用的 Python 派生结果；
-可选 VBA Extension；
-Profile 版本和源文件哈希。

Profile 可以通过两种方式维护：

1. 保存权威的 prepared CST 工程并在运行前校验能力；
2. 使用一次性的 Project Preparation Macro 自动安装标准参数和 Result Template。

工程准备发生在 Profile 构建阶段，不应在每个仿真任务中重复。

## 9. 可选 VBA Extension 规则

扩展按 `Profile + Extension Set` 编译一次，并复用于整个批次，禁止每任务重新生成。

扩展允许：

-读取当前求解结果；
-调用必要的 CST 场 API；
-写入声明的扩展结果。

扩展禁止：

-修改模型参数；
-再次运行求解器；
-终止 CST；
-写任务级成功/失败标志；
-依赖未声明的全局变量或输出文件。

稳定 Worker Runtime 负责错误汇总和任务完成。

## 10. Warm 与 Cold 双后端

建议保留统一 API 下的两个后端：

- `WarmCSTBackend`：用于高数量、相似几何、Mesh 复用明显的优化任务；
- `ColdCSTBackend`：用于开发、低数量任务、拓扑变化、回退和结果验证。

Cold Backend 还是 Warm 结果正确性的参照。应定期抽取 Warm 参数点进行 Cold 重算，监控：

-Frequency；
-Q；
-R/Q；
-场峰值；
-其他关键目标。

如果误差超过物理容差，应停止复用当前 Worker 或缩小允许的参数变化范围。

## 11. 是否值得保留 Warm Runtime

使用以下量化关系判断：

```text
总时间收益 = 任务数 × (Cold 单次时间 - Warm 单次时间)
```

还应扣除：

-接口维护成本；
-失败重跑成本；
-内存增长和 Worker 重建成本；
-Warm/Cold 一致性验证成本。

经验判断：

-Warm 节省超过 50% 且每批数百次以上：值得重点维护；
-节省 20%–50% 且任务量大：保留但必须简化接口；
-节省不足 20%：优先 Cold；
-结果无法稳定复现：不得用于正式结果。

## 12. 当前结论

- 保留 Warm CST Worker 的性能能力。
- 不再默认把每个结果实现为运行时 VBA Operation。
- 优先验证 CST 原生结果直读。
- 能在 Python 派生的结果移出 CST。
- 只为剩余必要能力设计小型 VBA Extension ABI。
- 当前 `VBPostProcessor` 保留为迁移兼容层，不继续扩张为最终架构。
- 原生结果可行性盘点完成前，不实施完整的大型后处理 ABI。

## 13. 相关文档

- [CST `.cst` 项目文件知识库](./cst-project-file-knowledge-base.md)
- [`.cst` 内部后处理与模拟设置修改分析](./cst-project-settings-editing-analysis.md)
- [CST VBA 与 Python 联合架构设计](./vba-python-integration-design.md)
- [CST VBA 与 Python 联合改造 TODO](./vba-python-todo.md)
- [原生结果优先 TODO](./cst-native-results-todo.md)
- [CSTManager API 与使用指南](./cstmanager-api.md)
- [CSTManager 设计文档](./cstmanager-design.md)
