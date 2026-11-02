# B2 保存设置的受限历史投影

2026-11-02。MCP共用底层实施批次，接续[B1来源](saved-project-source.md)。首阶段完整历史子集现已补齐，详见[51项命令与身份校验](a1-history-command-profile.md)；不是任意VBA解释器、生产MCP服务器或完整设置验证器。B3执行快照、B4真实副本与G03仍未完成。后文“第一版”验收是本日较早批次记录。

## 接口与作用域

`csttool.settings_projection.project_saved_settings(source, encoding=None)`接受B1的不可变`SavedSource`，从同一scope的Model.mod和Parameters.json取数据。必须由有效历史显式声明mm/MHz和HF Eigenmode类别；删除旧frequency_unit参数，不信任调用者字符串。缺失为unresolved，其他单位/类别unsupported；保存声明不是live查询。simulationproperties可缺失并记录optional-metadata-missing，存在却非法则拒绝；Last Solver Type不能补身份。

`project_history`是已抽取文本/参数的低层入口，供受控生成结构和离线测试使用；它不是MCP工具，不接受文件路径或执行脚本。require_identity默认false供既有局部oracle，正式文件入口固定开启。调用者提供的source_hash不能代替B1来源核验，正式文件调用走前一入口。scope必须存在于显式清单，无root回退或SP别名补全。参数大小写不敏感，拒绝重复名，仅使用同scope依赖。

`Projection`保留status、只读fields/origins、reasons、scope/source_hash/parser_profile；`publish_ready`始终false，`live_value`始终null。resolved仅表示列出的字段可确定；`missing_fields`列出未取得的首阶段配置，包括Reset后缺失字段。不能用resolved直接允许提交计算。

B3更新：新增只读exact_values，保留solver.frequency_target.value_mhz及solver.frequency_range的上下限Decimal求值字符串；展示float不再作为执行快照预期的精度来源。原表达式与精确求值分别保留，EigenmodeSolver.Reset同步清除其精确值。[B3工厂](execution-snapshot-verification.md)核对发布定义hash/scope后冻结预期；尚未接入实际采集或RunStore。

## 支持子集及安全性

- 词法识别VBA双引号与转义、字符串外注释/冒号、Rem、续行、平衡With；完全注释的停用内容不提取setter。来源保留原始UTF-8字节区间、行号、step导航、scope、工程/成员/参数hash；step仅依据`'@`标题导航，不是官方历史ID。未知旧编码不替换继续。
- 支持模式数、Hex/Tet方法槽位、活动求解网格、frequency target开关/表达式、Tet/Hex自适应开关、现代Tet near/far/version/policy、旧密度。MeshSettings分区选择不更改活动solver mesh。选中method同时引用方法写入与网格选择两处来源。
- EigenmodeSolver.Reset只清除自身已知字段，保留Project类别、Solver频段及mesh通道，不填默认。Cylinder.Reset只清待创建属性；Mesh.Reset/MeshSettings.Reset已移除推测性支持，直接拒绝。现代/旧密度并存返回ambiguous，不猜优先级。
- 算术只遍历AST白名单：数字、参数、加减乘除、有限整数幂、正负号及单字符串参数RestoreDoubleParameter；不使用eval。保留原表达式；CInt包装只接受整数输入。不模拟完整VBA函数、单位表达式或舍入。
- 依赖环/缺名为unresolved；缓存与40位Decimal推导不相等为stale。这是保守拒绝，暂不推断CST缓存数值格式的舍入误差；表达式不改写固定值。
- 控制流、动态执行、别名和未审查调用均拒绝，清空当前报告的所有字段；不能返回未知调用前的旧值。没有“通用忽略无关命令”规则。MeshAdaption3D两项已区分为策略，不能据此推断solver开关。

资源上限：历史2MiB/20000语句、参数4096项、表达式4096字符/256 AST节点/64层依赖或语法深度、幂指数绝对值≤32，数值数量级≤100。超限拒绝，不截断；这些是初始实现限制，不是CST格式极限。无写文件、宏调用、CST启动、后台接入或新依赖。

## 验收与未完成

`test/settings_projection_test.py`实际运行V06 H01–H26、S01–S07、M01–M02共35项语义oracle；另验证D04缺失可选元数据行为、B1组合读取、来源字节定位、未知代码污染、Reset通道隔离、单位/编码/JSON拒绝及预算。原cases.json仍保留B0历史not-run标记，不将其改成运行时状态数据库；本批结果以测试及报告为准。

本批离线75 passed（2.40s）：54项新投影测试、17项B1、4项B0结构/来源检查。报告`artifacts/b2-projection-final-20261102.xml`。首轮43 passed/5 failed暴露错误分类被ValueError覆盖及对象名数字遗漏，已修正重跑；首轮报告保留，不能当最终结果。无真实CST验收。

文档同步后最终合并验收77 passed（3.65s），包含上述75项及2项文档索引检查，报告`artifacts/b2-verified-20261102.xml`；数字重叠，不累加。本轮pytest临时目录已清理，保留轻量XML；可再生成合成容器，不保留临时源文件路径可用性。

完整旧Pillbox仍因模板附带的其他命令而unsupported；Units.Geometry/Frequency已支持。Enlarged完整历史仍因未知编码unsupported。这些真实源测试仅证明保守拒绝，不证明任意工程设置已读回。五个原始历史摘录未修改。

本批已补首阶段完整人工历史的精确允许表与持久units/solver身份锚点，见[新增验收](a1-history-command-profile.md)。D组来源故障仍由B1实际测试覆盖，不宣称已逐项执行全部D oracle。下一步B3实现attempt/revision/数据库hash绑定与数值格式profile，再做B4受控副本。任意旧历史/其他单位和编码支持不属于已完成范围。MCP宿主握手/公共服务/建模到结果尚未接入；本模块不暴露任意VBA接口。

出错恢复：修正来源、scope、明确单位或经审查的语法后重新只读投影；不自动求解、不修改参数或项目状态，不放宽Runner退出/恢复门禁。GUI/CLI暂未迁移到此模块，不建立第二条执行链。artifacts报告不保证随Git迁移；临时模型均为测试合成容器，可重新生成。
