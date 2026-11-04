# B2 保存设置的受限历史投影

2026-11-04：受管历史现由history_program原子分块，managed_history核对实际Model.mod；A1允许表范围仍独立，GEO设置组合/观察/许可见[GEO-2–4生产实现与验收](geometry-production-implementation.md)。旧离线GEO阶段文字只作历史记录。
2026-11-02。MCP共用底层实施批次，接续[B1来源](saved-project-source.md)。首阶段完整历史子集现已补齐，详见[51项命令与身份校验](a1-history-command-profile.md)；不是任意VBA解释器、生产MCP服务器或完整设置验证器。B3原生采集/RunStore、生产G03及G04公共单次子链已接入，见[当前状态](current-status.md)；不代表全部设置或任意工程均通过。

## 接口与作用域

`csttool.settings_projection.project_saved_settings(source, encoding=None)`接受B1的不可变`SavedSource`，从同一scope的Model.mod和Parameters.json取数据。必须由有效历史显式声明mm/MHz和HF Eigenmode类别；删除旧frequency_unit参数，不信任调用者字符串。缺失为unresolved，其他单位/类别unsupported；保存声明不是live查询。simulationproperties可缺失并记录optional-metadata-missing，存在却非法则拒绝；Last Solver Type不能补身份。

`project_history`是已抽取文本/参数的低层入口，供受控生成结构和离线测试使用；它不是MCP工具，不接受文件路径或执行脚本。require_identity默认false供既有局部oracle，正式文件入口固定开启。调用者提供的source_hash不能代替B1来源核验，正式文件调用走前一入口。scope必须存在于显式清单，无root回退或SP别名补全。参数大小写不敏感，拒绝重复名，仅使用同scope依赖。

`Projection`保留status、只读fields/origins、reasons、scope/source_hash/parser_profile；`publish_ready`始终false，`live_value`始终null。resolved仅表示列出的字段可确定；`missing_fields`列出未取得的首阶段配置，包括Reset后缺失字段。不能用resolved直接允许提交计算。

B3更新：新增只读exact_values，保留solver.frequency_target.value_mhz及solver.frequency_range的上下限Decimal求值字符串；展示float不再作为执行快照预期的精度来源。原表达式与精确求值分别保留，EigenmodeSolver.Reset同步清除其精确值。[B3工厂](execution-snapshot-verification.md)核对发布定义hash/scope后冻结预期；现已由公共采集及RunStore接入。

## 支持子集及安全性

- 词法识别VBA双引号与转义、字符串外注释/冒号、Rem、续行、平衡With；完全注释的停用内容不提取setter。来源保留原始UTF-8字节区间、行号、step导航、scope、工程/成员/参数hash；step仅依据`'@`标题导航，不是官方历史ID。未知旧编码不替换继续。
- 支持模式数、Hex/Tet方法槽位、活动求解网格、frequency target开关/表达式、Tet/Hex自适应开关、现代Tet near/far/version/policy、旧密度。MeshSettings分区选择不更改活动solver mesh。选中method同时引用方法写入与网格选择两处来源。
- EigenmodeSolver.Reset只清除自身已知字段，保留Project类别、Solver频段及mesh通道，不填默认。Cylinder.Reset只清待创建属性；Mesh.Reset/MeshSettings.Reset已移除推测性支持，直接拒绝。现代/旧密度并存返回ambiguous，不猜优先级。
- 算术只遍历AST白名单：数字、参数、加减乘除、有限整数幂、正负号及单字符串参数RestoreDoubleParameter；不使用eval。保留原表达式；CInt包装只接受整数输入。不模拟完整VBA函数、单位表达式或舍入。
- 依赖环/缺名为unresolved；缓存与40位Decimal推导不相等为stale。这是保守拒绝，暂不推断CST缓存数值格式的舍入误差；表达式不改写固定值。
- 控制流、动态执行、别名和未审查调用均拒绝，清空当前报告的所有字段；不能返回未知调用前的旧值。没有“通用忽略无关命令”规则。MeshAdaption3D两项已区分为策略，不能据此推断solver开关。

资源上限：历史2MiB/20000语句、参数4096项、表达式4096字符/256 AST节点/64层依赖或语法深度、幂指数绝对值≤32，数值数量级≤100。超限拒绝，不截断；这些是初始实现限制，不是CST格式极限。无写文件、宏调用、CST启动、后台接入或新依赖。

## 验收与当前接入

该模块已由[公共single-simulation服务](single-simulation-service.md)复用；生产G03及新Managed组合真实子链见[G04记录](single-simulation-g04-acceptance.md)。模块本身的静态/快照报告不单独证明live设置、求解、结果或退出。未知编码/历史及未校准组合继续保守拒绝。

原批次离线数字、故障修正、B4正常/失败/旧库副本及清理记录完整移至[历史验收](archive/20261102-progress-consolidation/settings-history-projection.md)。旧not-run/下一步只在原批次成立；当前未完成项查[TODO](minimal-python-vba-todo.md)。

## GEO离线program投影（2026-11-04）

同一模块新增project_geometry_history(blocks, parameters, scope=..., available_scopes=...)，复用词法/有界算术、Projection和命令profile入口；详见[GEO接口](geometry-selection-interface-design.md#13-geo-2离线历史发射投影检查与源映射)。输入是框架拥有的caption/body块，不是SavedSource或任意Model.mod。默认project_history/project_saved_settings仍只处理A1；没有自动探测/放宽原保存投影。GEO report的missing_fields按几何字段判定，publish_ready始终False；语义、独立文本检查及原生校准各自需要，不能将resolved当成编译/构建/保存证据。
