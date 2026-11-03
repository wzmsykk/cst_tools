# B2 首阶段完整历史命令与身份校验

2026-11-02，`cst-a1-history-v2`。[投影API](settings-history-projection.md)的本批更新；源码`csttool/settings_projection.py`，固定允许表`COMMAND_ARITIES`共51项。完整指首阶段受控历史子集，不指任意CST模板或现有工程全部历史。

## 命令允许表

每项先验证明确对象和参数个数，再解析参数值；不是按对象名豁免。下列字符串枚举/名字须为VBA字面量，禁止把变量名或函数调用当字符串常量。

|对象/命令|参数数与限制|处理与官方依据|
|---|---|---|
|全局`ChangeSolverType`|1，`"HF Eigenmode"`|写solver.family；官方Project Object B03。历史本身处于已明确的3D scope。表内project仅为内部分类，不承诺VBA存在名为Project的全局变量；不接受`Project.ChangeSolverType`或`With Project`别名|
|Units.Geometry/Frequency|各1，仅mm/MHz|写units.length/frequency；B09。注释头中的length/frequency不是权威|
|WCS.ActivateWCS|1，仅global|记录全局坐标前提；B06，不允许local/Restore等路径|
|Component.New|1，安全名字，最多一个组件|记录创建声明；B05。不是运行时存在性查询|
|Background.Type|1，仅pec|记录背景类型；B07|
|Background.XminSpace/XmaxSpace/YminSpace/YmaxSpace/ZminSpace/ZmaxSpace|各1，算术结果须0|分别记录六面padding；B07，不猜ApplyInAllDirections等同六面设置|
|Boundary.Xmin/Xmax/Ymin/Ymax/Zmin/Zmax|各1，仅electric|记录六面计算盒边界；B08|
|Boundary.Xsymmetry/Ysymmetry/Zsymmetry|各1，仅none|记录三轴对称；B08|
|Cylinder.Reset/Create|0|Reset仅清除待创建对象配置；Create验证后记录单个圆柱声明，保留属性与Create两处来源；B04|
|Cylinder.Name/Component/Material/Axis|各1|名字为安全ID；组件须由此前New声明，材料仅Vacuum，axis为x/y/z；B04|
|Cylinder.OuterRadius/InnerRadius/Segments/Xcenter/Ycenter/Zcenter|各1|半径>0、内半径0、光滑segments=0、中心均0；B04及A1限制|
|Cylinder.Xrange/Yrange/Zrange|各2|仅与axis相同的范围，hi>lo；拒绝未用轴range，避免按名称猜作用；B04|
|Solver.FrequencyRange|2，0<min<max|保存MHz频段和表达式；B11。其修改会影响mesh/结果，首阶段历史顺序要求在网格配置之前|
|Mesh.MeshType|1，仅Tetrahedral|记录生成网格类型，和EigenmodeSolver选用网格、MeshSettings配置分区分别保存；B10|
|MeshSettings.SetMeshType|1，Tet/Hex/All/Unstr|只选择编辑分区；本子集Set必须在明确Tet分区；依据已有版本限定校准，不声称找到官方完整文档|
|MeshSettings.Set|2，仅Version、StepsPerWaveNear、StepsPerWaveFar、CellsPerWavelengthPolicy|Version仅1；密度正数；policy仅cellsperwavelength。依据[V05](../knowledge-base/cst-tet-density-mesh-calibration-20261028.md)；不自动合并near/far|
|Mesh.StepsPerWavelengthTet|1，正数|仅保留legacy通道；B10。与现代通道并存仍ambiguous，不默认覆盖/等价|
|EigenmodeSolver.Reset|0|清除本征模对象的已知投影值；保留Project控制的solver.family、Solver控制的frequency_range和独立mesh通道；B12，不补默认|
|EigenmodeSolver.SetNumberOfModes|1，正32位整数|保留表达式；受限CInt/RestoreDoubleParameter；B12|
|EigenmodeSolver.SetMethodType|2，明确Hex/AKS或Tet/Default、General (Lossy)|独立方法槽位；B12；不是活动solver类别证据|
|EigenmodeSolver.SetMeshType|1，Tetrahedral Mesh/Hexahedral Mesh|选择求解mesh，导出对应selected_method；B12|
|EigenmodeSolver.SetFrequencyTarget|2，布尔和算术值|启用与存储值分开，带全局频段时检查0≤value≤max；B12。不能拿全局min替代target|
|EigenmodeSolver.SetMeshAdaptationTet/Hex|各1，布尔|保存开关；B12；策略命令不替代开关|
|EigenmodeSolver.SetConsiderLossesInPostprocessingOnly|1，布尔|记录损耗设置；B12；不据此推断实际Q或损耗物理结论|
|MeshAdaption3D.SetType/MinPasses|各1，HighFrequencyTet/正整数|已知策略，不写solver自适应开关；官方MeshAdaption3D页面已补核。参数同样严格求解，不能忽略调用表达式的副作用|

B编号沿用[官方语义核查](../knowledge-base/cst-first-stage-api-semantics-20261028.md)。本次11页原文件hash及新增边界见[核查记录](../knowledge-base/cst-a1-history-review-20261102.md)。此表是项目支持子集，不是厂商完整API目录。

明确排除Start、RunSolver、保存/导出/关闭、OpenFile、StoreParameter及任意动态代码/控制流/别名；这些不应放入首阶段结构设置历史。退出/计算仍由原有受控执行链处理。`Mesh.Reset`、`MeshSettings.Reset`、Background/Boundary.Reset未取得相应依据，不允许。

## 身份、单位与顺序

生产入口改为`project_saved_settings(source, encoding=None)`，删除旧`frequency_unit`参数，无兼容别名。调用方声明不再能补齐单位。它只从同一B1保存快照、同一scope的有效历史获取Geometry=mm、Frequency=MHz及显式ChangeSolverType=HF Eigenmode，且三项必须在求解/网格设置之前。长度单位必须在圆柱构造前声明。

缺失身份为unresolved；其他单位/solver family为unsupported。注释、停用块、其他scope、Model.prj的Last Solver Type、simulationproperties或低层active_solver输入都不能补缺。身份来源只证明保存程序的显式声明，不是现场GetSolverType、安装版本校准或重建成功。低层`project_history`为人工片段保留默认部分投影；正式文件入口固定启用require_identity，不提供关闭此门禁的参数。

保守顺序规则：mesh配置后再FrequencyRange、solver配置后再ChangeSolverType都unsupported；未知的重置/覆盖副作用不能靠最后setter猜测。非MHz/mm的中途切换即使最后改回也拒绝。所有异常清空当前字段，`failure_origin`保留导致拒绝的语句、行/字节范围与来源hash；非语句级缺失诊断的该字段可能为空或指向最后处理点。

Cylinder必须显式Reset及必需属性后Create；不采用文档默认补齐缺失值。不做实际实体布尔/体积验证，不证明内建Vacuum真实存在；这些仍由后续原生副本验收取得。`missing_fields`增加身份、全局频段、mesh生成类型、损耗、背景、边界、WCS和圆柱声明；即使缺失为空，publish_ready仍false。

## 测试、接入与限制

固定人工历史为test/fixtures/a1-pillbox-history.vb，离线测试为test/a1_history_profile_test.py及test/settings_projection_test.py；它们不是CST导出的原始历史。生产公共服务已接入B1/B2、G03与原生采集，公开类型化链已有2026-11-03记录；不能继续把B3/公共链记为尚未实现。完整旧模板、未知编码及允许表外命令仍拒绝。

[原批次完整记录](archive/20261103-semantic-review/a1-history-command-profile.md)保留2026-11-02的138/143项与当时后续计划；当前门禁见[当前状态](current-status.md)，本次只核对源码，不追认旧数字为新验收。
