# 场诊断与模式追踪现行状态

2026-11-03静态整理；原六阶段实施/失败对照、concaveL定位、效率与分批数字完整保存在[历史快照](archive/20261103-semantic-review/mode-field-selection-implementation-status.md)。本页不新增真实CST或物理校准证据。

## 已实现的分层

- 已保存结果字段导出/读取、复场加权指标与小矩阵分析，具备source/坐标/分量/单位/工件校验及缺失后分析恢复；不为补分析重放Solver。
- 可选Managed场诊断与标量求解结果分开，诊断失败不伪造完整分析，也不反向抹掉已成功求解。原生场位于配套结果目录，仅复制.cst不能读出旧E/H场。
- 共同物理域、独立支持/材料掩码与体积权重已接入；固定PEC背景、内部显式真空solid的第一版有自动预检/登记及小网格Pillbox双网格证据。自动登记额外要求六面electric、无对称/端口且采样盒覆盖显式Vacuum实体；磁边界不在自动登记支持范围。不是任意CAD、多材料或开放域支持。
- 固定锚点单模MAC/最多四个参考模式的显式模组白化Gram-SVD、频率门禁和歧义/病态拒绝已实现；匹配成功仍不授予physical_identity_confirmed或成员极化身份。HOM顺序谱枚举不因低MAC自动丢模式。
- Managed/GUI可选登记与matching默认关闭、单Worker且标准退出后串行处理；没有隐式候选搜索、自动合并HOM或全功能COMSOL工作流。

## 原生作用域与生命周期

生产Managed/预处理在已加载工程Model/3D/Model.run中运行，避免空工程OpenFile混合作用域。concaveL表达式保留；具体旧错误及已排除路线见[作用域对照](concave-expression-scope-rebuild-fix.md)。保存场导出正常返回批执行器，身份/源hash/完成标记/工件和实际退出分别核验；不能以退出0抹去旧生命周期错误。

## 仍需独立验证

三层mesh/采样及更多模族阈值、复杂CAD/多材料共同域、更多极化/XYZ/积分位置、完整算子效率与冷缓存、真实求解失败/更多指令级中断、候选请求自动调度。旧ROI效率和部分Pillbox双网格结果不代替上述门禁。原始大文件已清理的记录须重生成，不按旧路径声称仍可访问。

使用入口：[真空追踪](vacuum-mode-tracking-v1.md)、[自动域预检](vacuum-domain-registration.md)、[Managed/GUI可选链](managed-vacuum-domain-gui.md)、[算子路线研究](postprocess-operator-execution-plan.md)。原计划是设计，不把其待办勾选复制成当前实现结论。
