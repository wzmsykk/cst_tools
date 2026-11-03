# COMSOL MCP 对代码生成防线的参考

> 适用性复审（2026-11-03）：按原日期/样本/固定来源保留的研究，不是通用格式规范、现行运行合同或新实测。现行实现见[当前状态](current-status.md)、[功能索引](feature-index.md)及对应API；不重算或追认旧证据。

日期：2026-11-03。这是社区项目的固定版本源码审阅，没有运行 COMSOL；不将社区 MCP 称为 COMSOL 官方产品，也不把源码路径存在当作端到端验收。此前能力对齐见[功能目标](comsol-mcp-functional-alignment.md)，本次重点是语言边界和失败语义。

## 实际执行链

|项目及固定版本|所查实现|可借鉴与边界|
|---|---|---|
|wjc9011/COMSOL_Multiphysics_MCP，`53c9ca4cd9f16187b1e5e4fa97cff6dca716ed9d`|session 导入 MPh、创建 `mph.Client`；geometry 通过 `model.java.component(...).geom(...).feature().create(...)` 和 `feature.set(...)` 操作对象|所查建模路径不生成整段 Java 源码，因此没有再嵌套一层 Java 调用语法；但 feature 类型、属性名、单位和表达式仍需验证|
|Ching-Chiang/comsol-mcp，`ccca65aa8277d1205c5de5fb6221e460aca5997a`|连接层创建 `mph.Client`；`create_feature` 显式传 component/geometry/tag，调用 Java 对象，属性从 `properties_json` 解析后应用，可选运行几何|显式作用域、操作与 rebuild 分开值得参考；JSON 字符串属性袋不等于严格业务子 Schema，也不证明修改原子性|

源码：[wjc session](https://github.com/wjc9011/COMSOL_Multiphysics_MCP/blob/53c9ca4cd9f16187b1e5e4fa97cff6dca716ed9d/src/tools/session.py)、[wjc geometry](https://github.com/wjc9011/COMSOL_Multiphysics_MCP/blob/53c9ca4cd9f16187b1e5e4fa97cff6dca716ed9d/src/tools/geometry.py)、[Ching connection](https://github.com/Ching-Chiang/comsol-mcp/blob/ccca65aa8277d1205c5de5fb6221e460aca5997a/comsol_mcp/_connection.py)、[Ching geometry](https://github.com/Ching-Chiang/comsol-mcp/blob/ccca65aa8277d1205c5de5fb6221e460aca5997a/comsol_mcp/_tools_geometry.py#L49-L86)。本表只覆盖所查路径，不宣称仓库不存在其他执行通道。

COMSOL Java 对象方法调用与 CST 的 AddToHistory 内层 WinWrap 程序并不等价。本项目需历史重放的设置仍要保留历史，不能为了消除字符串代码就全部换成一次性直接调用。结构化参数中的表达式也仍然是宿主模型语言，不能被 Python 输入类型自动证明合法。

## 不应照搬的失败处理

1. wjc 的 `geometry_add_feature` 先创建 feature，再逐项 set；属性异常记录到 `failed_properties`，最终仍可返回 `success=True`。这只能说明部分操作成功，不能作为模型可求解或定义发布成功。CST 应在候选副本中完成全部设置、保存重开和验证后再发布；失败保持旧定义可用，不采用半成品。
2. wjc 异步 solver 的 0.1/0.2/0.3 是阶段常量；源码在这些标签之间没有相应独立建模/网格调用，随后才执行 `model.solve`。cancel 仅设置标志，阻塞求解前后检查，不能据此认定实际求解已中止。[solver.py](https://github.com/wjc9011/COMSOL_Multiphysics_MCP/blob/53c9ca4cd9f16187b1e5e4fa97cff6dca716ed9d/src/async_handler/solver.py#L97-L178)。CST 继续保留请求停止、实际停止、收尾回执、进程退出各自的证据。
3. Ching 异步求解持有 runtime lock，在 daemon thread 执行并返回 job_id。但 `try model.solve(label) / except model.solve(study)` 会把首次实际求解异常也纳入回退，不只处理标签解析错误；CST 应先解析唯一身份，再只提交一次求解，避免异常后隐式重复计算。[solver tool](https://github.com/Ching-Chiang/comsol-mcp/blob/ccca65aa8277d1205c5de5fb6221e460aca5997a/comsol_mcp/_tools_solver.py#L158-L222)。
4. Ching `_timed_call` 使用 future timeout 和 `shutdown(wait=False)`；从这些语句不能证明底层 Java 调用已取消。其注释对 daemon/不阻止进程退出的表述也不能替代线程实现与实际退出测试。CST 的等待超时不能改写为已关闭，仍须核验对象和进程归属。

## 对 CST 的设计结论

保留[W0–W3](winwrap-codegen-safety-plan.md)顺序，具体收敛为：

- MCP、GUI、CLI 共用类型化业务操作；先核实 CST 官方对象方法是否满足作用域和持久化要求，适用时直接调用。
- 必须写历史时，由同一个小型发射器处理字符串、表达式和调用形式；固定已验模块传数据，避免由 AI 每次临时组织 WinWrap 程序。
- 建模候选只有全部属性成功、表达式保留、历史持久化及原生读回通过才能发布；部分成功需要显式标识并阻止发布。
- 对象/tag/作用域解析失败与实际求解失败分开，不通过再次 solve 猜测接口；语法错误不进入加密或扩窗恢复。
- Job ID、线程、锁和超时只能解决局部调度问题；沿用本项目已有 RunStore、结果采用和收尾协议，不另建 COMSOL 风格内存队列。
- Skill 提供经过校准的调用卡片和流程；工具端强制 Schema、scope、持久化与结果核验。两者不替代 WinWrap 原生门禁。

本次只补充设计依据，没有增加 API、兼容适配或运行逻辑。仍待核实原生 WinWrap 编译/错误采集能力并实施 W0–W3；真实桌面整链验收仍按原计划待办。
