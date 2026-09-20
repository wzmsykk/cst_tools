# CST Tools 当前状态与实施路线

状态日期：2026-09-20
当前基线提交：`a2664e6 Migrate GUI to managed CST worker`（其后工作区实施 GUI P13，尚未提交）

本文是项目当前状态的权威入口。历史设计文档仍保留其分析价值；若与本文或[最小 Python/VBA 协议 TODO](./minimal-python-vba-todo.md)冲突，以本文和已经通过的真实 CST Gate 为准。

## 1. 当前结论

项目不再以“先建设完整 Python/VBA Operation ABI”为近期目标。当前方案是：

1. 保留 Warm CST，用于结构不变、主要改变频率范围的批量 HOM 任务；
2. 优先读取 CST 原生 `.rd0` 结果；
3. Python 负责结果读取、严格校验、任务身份和调度；
4. VBA 只保留 CST 内必须执行的状态变化和复杂运行时后处理；
5. Project Profile 声明 prepared 工程、允许修改的参数、注册模板和结果能力；
6. 不把 CST Result Template GUI 操作包装成运行期 ABI。

当前实现是独立、安全、可验证的增量路径。GUI 已迁移到新的应用后端边界；底层生产 `CSTManager`、`worker.vb` 和算法执行链尚未切换到 P7 Profile/Warm 协议核心。

## 2. 当前执行链

```text
Python Task
  -> 原子提交 Task v1
  -> CST Worker 打开临时工程副本
  -> Profile 预检注册模板
  -> 应用允许的参数
  -> Rebuild / Solver
  -> CST Result Template / 原生 .rd0
  -> Completion
  -> Python 读取并校验结果
  -> Ack
  -> Save / Quit 或继续下一 Warm Task
```

结果选择顺序固定为：

```text
native CST result -> Python-derived result -> optional runtime VBA
```

## 3. 已完成阶段

| 阶段 | 已验证内容 | 真实 CST 证据 |
|---|---|---|
| P2.5 | Python/VBA v1 Codec、Completion/Ack、标准生命周期 | Contract Gate 通过 |
| P3 | Pillbox 临时副本、literal/expression、Rebuild/Solve/Flush、一个 `.rd0` | `503.782 MHz` |
| P4 | 同一 CST 进程串行双任务、独立结果、Ack 栅栏、Stop | 双任务 Gate 通过 |
| P4.5 | HOM 固定结构、仅变频率范围的 Cold/Warm 对照 | Warm 总墙钟约 `1.563x`；P5 扩展 Gate 约 `1.445x` |
| P5 | 五个 HOM 原生标量严格读取及 Cold/Warm 一致性 | Frequency、Q、R/Q 0/5/10 mm 一致 |
| P5.5 | x/y/z 任意积分轴运行时 R/Q；固定模板与动态 VBA 路由 | z 轴 5 mm 与原生模板一致 |
| P5.6 | CST 官方 iterator 盘点注册模板；`EvaluateResultTemplates` 当前 Run 评估 | 5 个 M0D 模板，评估前后 `765.981 MHz` |
| P6 | `hom-2022-v1` 最小 Profile；求解前能力预检和 fail-fast | 正负两个 Gate 均通过 |
| P6.5 I | Profile 接入有界 HOM Warm Worker；会话级单次预检 | 五项结果一致，Warm `1.379x`；缺模板在首个 Solver 前失败 |
| P6.5 II | 同一 Profile 驱动原生读取、结果分类和 R/Q 路由 | 变体 Profile 测试通过；真实多轴 Gate 保持一致 |
| P7 | Profile、严格标量读取、Provider 选择抽成通用核心 | 基础 `ProjectProfile` Worker、fail-fast、多轴 Gate 均通过 |
| GUI P0 | offscreen Qt 安全网、启动条件、线程信号和按钮锁定 | GUI `8 passed`；完整默认测试通过 |
| GUI P1 | 显式 RunState、组合式 Worker、后台准备和集中状态渲染 | GUI `10 passed`；失败可重试、重复启动被拒绝 |
| GUI P2 | 标准停止、非阻塞受控关闭、阶段与进度显示 | GUI `13 passed`；关闭等待全部线程结束 |
| GUI P2.5 | 真实 GUI/Controller/Manager 配合 Fake Worker 的全流程 Gate | 成功、失败、运行中关闭三条流程通过 |
| GUI P2.6 | GUI 可调 Worker 并发数，运行请求冻结配置并传入 Manager | 默认为 1；用户可按本机资源和许可证显式调高 |
| GUI P3 | 类型化算法/PPS 设置、稳定 method key、正确 Qt 模型通知、版本化 JSON | 新旧 JSON 兼容；P3 与 GUI 定向测试通过 |
| GUI P4 | 统一浅色工程工作台主题、语义操作样式和运行状态反馈 | 离屏渲染成功；主题与既有 GUI Gate 通过 |
| GUI P5 | 固定坐标主窗口改为响应式双栏工作台 | 缩放布局与 UI 源文件编译 Gate 通过 |
| GUI P6 | 对话框事务、运行期冻结、已有项编辑、父子生命周期和明确源码命名 | GUI 功能 Gate 36 passed |
| GUI P6.5 | 真实后端启动、可移植 PyInstaller 配置与独立目录打包 smoke | 打包程序退出码 0，无 CST/UI 残留 |
| GUI P7–P9 | Application Service、生产后端和生命周期收口 | GUI/CLI/测试替身均直接使用现代后端协议；旧 Engine 适配器和 `cst_tools_main` 门面已删除 |
| P10 | 生产算法替换旧 Manager API | 默认、TM020、WTC 使用 `CSTManager`、`SimulationTask`、`execute/run_batch` |
| P11 | HOM 扫描完整性修复 | 窄区间逐个求解 Mode 1、微小容差推进、有限重试和原子 checkpoint |
| P12 | GUI 生产 Worker 迁移 | 默认后端使用长驻版本化文件协议 Worker；Completion/Ack 栅栏，标准 Save/Quit，保留声明式运行时 VBA 后处理 |
| GUI P13 | 现代运行工作台 | 可调整双栏、状态徽标、阶段摘要、显式安全停止、日志治理与键盘焦点反馈；GUI Gate 45 passed |
| P13.5 | CST 工程参数预处理 | 在独立工作副本中缺失时添加 `fmin/fmax/nmodes`，通过原子 History 步骤绑定 Solver，显式完成标记、Save/Quit，源工程保持不变 |
| P14 | 可恢复 HOM 扫描会话 | 不可变 `scan_manifest.json`、协作式停止、禁止停止期派发/Worker 轮换、ACK 阶段 Stop、独立 Windows 进程组、`INTERRUPTED` 状态、残留会话自动发现及 GUI 恢复 | Pillbox“运行中停止→Save/Quit→新会话恢复完成”Gate 通过，`1 passed in 84.90s` |
| P14.5 | CST 后台进度 | 增量 tail 每个 Worker 的 `cst.log`，解析 Mesh、Refinement、Eigenmode Pass 和局部百分比，经 Worker/Manager/Backend/Qt signal 显示；不使用 PIPE，不把 Pass 百分比称为总进度 | 真实 Pillbox 日志、频段身份、局部百分比及安全退出 Gate 通过，`1 passed in 56.95s` |
| P15 | CST 后端版本切换 | 自动发现本机全部 CST 安装、GUI 显式选择并持久化、运行期冻结；Manifest 绑定版本和可执行文件 | 多版本发现/校验、后端状态门和 GUI 切换测试通过 |
| P15.5 | HOM 多阶段异常恢复 | 真实 HOM 顺序求解 10 个 Mode 1 窄窗口结果；Mode 3 后安全暂停、Mode 7 控制器丢失、Mode 9 CST 进程树死亡并从 Mode 8 快照重算 | 10 个频率严格递增、7 项后处理齐全、两类恢复凭据正确、无交互式 CST 残留 |
| P15.6 | 确认快照生产接力 | 成功结果发布 `ProjectSnapshot`；仅顺序 HOM 任务显式请求同槽快照接力；标准批量任务保持独立；HOM checkpoint schema 3 持久化并校验快照，续跑前由快照重建 Worker 池 | 单元 Gate 覆盖 Mode 8→9 轮换、标准批处理隔离、显式恢复、快照篡改拒绝和生产算法续跑 |
| 标准模式解析 Gate | 四 Worker 批量改变 Pillbox 半径，按 TM010 解析模型优化至 500 MHz；注入 Worker 异常、Solver Failure 和重试耗尽后恢复 | 54 次任务、6 轮；229.48730469 mm、499.99509991 MHz；轮换始终回到基础工程，不启用快照接力 |
| 标准模式真实 CST Gate | Gate 固定使用 1 个 Managed Worker；按真实 Frequency 优化 Pillbox 半径 | CST 2022 单 Worker：3 次求解、1 轮；230.8125 mm、499.792534459 MHz；标准退出且无残留进程 |

P11 已移除大区间多模饱和二分方案；默认 PPS 恢复为 `iModeNumber=1` 的非 `_All` 方法。严格同频简并模态仍需要专门的局部多模 Gate，当前不能宣称已覆盖。P11 尚未执行完整频段的真实 CST 找全验收。P12 Managed Worker 双任务真实 Gate 已通过：同一 CST 会话连续完成两个任务，Completion/Ack 和 Stop Ack 正常，进程以退出码 0 结束且未强制清场。P14 已验证 Pillbox 的安全停止和新会话恢复生命周期，但不等同于复杂 HOM 工程 500–1000 MHz 全频段验收。

P14 的普通“安全停止”在 Stop Ack 超时时只返回 `RECOVERY_REQUIRED`，不再自动终止 CST。GUI 的“恢复会话”会扫描项目运行目录中的 Managed Session，补齐遗留 Completion 的 ACK，并通过 Stop Request/Ack 完成 Save/Quit。强制结束已拆为显式 `emergency_terminate()`，调用后工程必须保持 `RECOVERY_REQUIRED`。

异常恢复进一步区分两类会话：仍存活的 CST 必须完成 Stop Request → Completion ACK → StopAck → 进程退出；PID 已明确死亡的隔离 Worker 会话写入 `abandoned-dead` 恢复凭据，并从最后一个原子 checkpoint 重算未确认区间。所有会话收口后，`project.ini` 才从 `RECOVERY_REQUIRED` 持久化为 `INTERRUPTED`。存活但无响应的进程不会被恢复流程自动强杀。

真实十模式 Gate 同时证明：安全暂停后应以最近一次成功任务生成的 `project.cst` 快照作为恢复输入，而不是重新复制最初 clean 工程；异常死亡后的 Worker 工程不可信，必须回退到死亡前最后一个已确认快照。该规则现已进入生产 Manager 和 HOM checkpoint，而不再只存在于 Gate 驱动代码。空窗口以 `frequency=-1` 明确识别并推进，不得作为模式写入 checkpoint。

## 4. `hom-2022-v1` Profile

Profile 当前仅覆盖一个经过验证的 HOM 工程：

- CST：2022；
- prepared 工程：`project/HOM analysis/HOM analysis_clean.cst`；
- Warm 任务允许修改：`fmin`、`fmax`；
- 必需模板：Frequency、Q-Factor、R/Q 轴上、R/Q 5 mm、R/Q 10 mm；
- 原生结果：上述五个 `Mode 1.rd0` 标量；
- 动态 VBA：任意轴/任意位置 R/Q、Shunt Impedance、Total Loss、Voltage。

Profile 验证使用 CST 官方 `ResetTemplateIterator/GetNextTemplate`，比较 result name、template type、template name 和 folder。缺失能力返回 `PROFILE_CAPABILITY_MISSING`，且必须在参数更新、Rebuild 和 Solver 之前终止。

## 5. Result Template 边界

- `.r0d/.r1d` 是模板定义 artifact，不是物理结果；
- `.rd0` 是当前运行产生的标量结果；
- CST 2022 公开 VBA API 支持模板枚举和 `EvaluateResultTemplates`；
- CST 2022 没有公开的模板新增、复制或删除 VBA API；
- 官方旧 `Import Result Templates` 宏已废弃，复制/粘贴由 GUI 提供；
- 直接生成或修改 `.r0d` 不能证明模板已注册；
- 模板安装属于 Profile 制备/发布，不属于每任务运行协议。

官方 `3D Eigenmode Result` 模板本身支持 x/y/z 积分轴，但当前 prepared HOM 工程只注册了 z 轴 0/5/10 mm 三条 R/Q 积分线。未注册的轴或位置继续由 `EigenResult_Complex` 在同一次求解结果上计算；求解后禁止通过工程参数变化驱动模板，因为 `Update Params` 会使结果失效。

## 6. 尚未完成

- `local_cstworker/worker.vb` 尚未迁移到当前最小文件协议；`CSTManager` 之上的维护中算法已使用现代任务 API；
- GUI 和默认 CLI 已不再提供旧 Engine 兼容入口；
- 当前暂不扩展到 default、TM020、WTC、Pillbox 或复合 Enlarged/HOM Profile；
- 没有自动安装 Result Template；
- 已有 HOM 运行 Manifest；没有通用 Profile Schema、动态 capability negotiation 或多 Transport；
- 没有完成 `cst_version` 只读核心的仓内提取和跨版本矩阵；
- 没有建立 20–30 点以上的 Warm 性能、内存增长和失败率统计；
- Shunt Impedance、Total Loss、Voltage 仍缺少原生/Python 派生等价性证明；
- 旧 PPS、重复 Pattern 和生产 VB 尚未删除。

这些项目不是 P6 的隐含组成部分。下一阶段只抽取已经由 HOM Gate 证明的通用核心，不以第二个 Profile 为前置条件，也不扩大为通用 ABI。

## 7. 推荐后续顺序

1. 用真实 CST 分别验证默认、TM020 和 WTC 的 `SimulationTask` 生产调用；
2. 将 Profile/Warm Worker 泛化为可接受任意任务数的生产候选 Worker，再通过 `worker_factory` 接入 `CSTManager`；
3. 将 WTC/TM020 独立优化入口收口为同一现代 Backend 工厂；
4. 保留 HOM 专属 R/Q 薄适配层，不把物理量语义下沉到通用核心；
5. 暂不做 Profile 序列化、Manifest、动态 capability negotiation、插件 ABI 或多 Profile 注册表。

## 8. 文档导航

- 当前实施记录：[最小 Python/VBA 协议 TODO](./minimal-python-vba-todo.md)
- 测试命令与 Gate：[测试指南](./testing-guide.md)
- GUI 重构路线：[GUI 重构 TODO](./gui-refactor-todo.md)
- 运行协议：[Python/VBA Runtime Protocol](./python-vba-runtime-protocol.md)
- 原生结果路线：[CST 原生结果优先 TODO](./cst-native-results-todo.md)
- 工程格式知识：[CST 项目文件知识库](./cst-project-file-knowledge-base.md)
- Result Template 格式：[Result Template 文件结构](./cst-result-template-format.md)
- CSTManager 公共接口：[CSTManager API](./cstmanager-api.md)
- CSTManager 设计：[CSTManager 设计文档](./cstmanager-design.md)
- 应用后端 API 与生命周期：[CST Application Backend](./application-backend.md)
- HOM 扫描算法：[HOM 自适应区间扫描](./hom-scan-algorithm.md)
- 历史完整 ABI 提案：[现代跨语言 ABI 设计](./modern-cross-language-abi-design.md)
