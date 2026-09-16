# CST Tools 当前状态与实施路线

状态日期：2026-09-17
当前基线提交：`51b00ff Add minimal HOM project profile P6`

本文是项目当前状态的权威入口。历史设计文档仍保留其分析价值；若与本文或[最小 Python/VBA 协议 TODO](./minimal-python-vba-todo.md)冲突，以本文和已经通过的真实 CST Gate 为准。

## 1. 当前结论

项目不再以“先建设完整 Python/VBA Operation ABI”为近期目标。当前方案是：

1. 保留 Warm CST，用于结构不变、主要改变频率范围的批量 HOM 任务；
2. 优先读取 CST 原生 `.rd0` 结果；
3. Python 负责结果读取、严格校验、任务身份和调度；
4. VBA 只保留 CST 内必须执行的状态变化和复杂运行时后处理；
5. Project Profile 声明 prepared 工程、允许修改的参数、注册模板和结果能力；
6. 不把 CST Result Template GUI 操作包装成运行期 ABI。

当前实现是独立、安全、可验证的增量路径，尚未替换 legacy `worker.vb` 和生产 `CSTManager` 后端。

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

当前默认测试基线为 `76 passed, 11 deselected`。P6 定向真实 CST Gate 为 `2 passed in 292.90s`。

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

- legacy `CSTManager/local_cstworker/worker.vb` 尚未迁移到当前最小协议；
- Profile 尚未扩展到 default、TM020、WTC、Pillbox 或复合 Enlarged/HOM；
- 没有自动安装 Result Template；
- 没有通用 Profile Schema、Manifest、动态 capability negotiation 或多 Transport；
- 没有完成 `cst_version` 只读核心的仓内提取和跨版本矩阵；
- 没有建立 20–30 点以上的 Warm 性能、内存增长和失败率统计；
- Shunt Impedance、Total Loss、Voltage 仍缺少原生/Python 派生等价性证明；
- 旧 PPS、重复 Pattern 和生产 VB 尚未删除。

这些项目不是 P6 的隐含组成部分。没有新的失败样例或第二个真实 Profile 前，不扩大为通用 ABI。

## 7. 推荐后续顺序

1. 将 `hom-2022-v1` 预检复用到 HOM Warm Worker，会话启动时检查一次，任务仍只传 `fmin/fmax`；
2. 用同一 Profile 同时驱动 Warm Worker、原生结果读取和运行时 R/Q 路由，删除剩余 HOM 硬编码入口；
3. 选择第二个确有业务价值的 Profile（优先 WTC 或 TM020）重复原生结果盘点，而不是先设计通用 Schema；
4. 两个 Profile 出现真实共同需求后，再提取最小 Profile 序列化格式；
5. 最后才评估 legacy Manager 切换和旧 VBA/PPS 删除。

## 8. 文档导航

- 当前实施记录：[最小 Python/VBA 协议 TODO](./minimal-python-vba-todo.md)
- 测试命令与 Gate：[测试指南](./testing-guide.md)
- 运行协议：[Python/VBA Runtime Protocol](./python-vba-runtime-protocol.md)
- 原生结果路线：[CST 原生结果优先 TODO](./cst-native-results-todo.md)
- 工程格式知识：[CST 项目文件知识库](./cst-project-file-knowledge-base.md)
- Result Template 格式：[Result Template 文件结构](./cst-result-template-format.md)
- CSTManager 公共接口：[CSTManager API](./cstmanager-api.md)
- CSTManager 设计：[CSTManager 设计文档](./cstmanager-design.md)
- 历史完整 ABI 提案：[现代跨语言 ABI 设计](./modern-cross-language-abi-design.md)
