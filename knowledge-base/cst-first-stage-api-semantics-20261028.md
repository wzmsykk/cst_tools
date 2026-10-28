# CST首阶段接口语义与持久化核查

日期：2026-10-28，CST2022本机安装版帮助；静态只读，不新增真实CST证据。目标是支撑[首阶段统一契约](../docs/mcp-first-stage-interface-contract.md)，不是完整CST API审计。固定来源和原文件SHA256在`artifacts/first-stage-cst-contract-20261028/sources.json`，提取文本同目录；不保证随Git迁移。

## 官方文档来源

基准：`D:\Program Files (x86)\CST Studio Suite 2022\Online Help`。

|编号|相对路径|核查用途|
|---|---|---|
|B01|advanced/vbaapplicationobject.htm|Application.NewMWS/OpenFile/Active3D与QuietMode/Quit|
|B02|Python/source/cst.interface.html|DE新建、Project.save/close、modeler与schematic分别归属|
|B03|mergedProjects/VBA_3D/common_vbaapp/common_vbaappapplication_object.htm|实际标题Project Object；参数、历史、重建、保存/Backup及GetOwnProject|
|B04|mergedProjects/VBA_3D/common_vbabasicsolids/common_vbacylinder_object.htm|Cylinder前提、WCS、Axis/range、segments、Create|
|B05|mergedProjects/VBA_3D/special_vbalayer/special_vbalayerocomponent_object.htm|Component.New/DoesExist、隐藏不入历史|
|B06|mergedProjects/VBA_3D/common_vbawcso/common_vbawcso_wcs_object.htm|显式global/local、IsWCSActive|
|B07|mergedProjects/VBA_3D/special_vbasolver/special_vbasolver_background_object.htm|背景类型和计算域padding|
|B08|mergedProjects/VBA_3D/special_vbasolver/special_vbasolver_boundary_object.htm|计算盒六边界及对称setter/getter、结构盒/计算盒区别|
|B09|mergedProjects/VBA_3D/common_vbaunitso/common_vbaunitso_units_object.htm|工程长度/频率及SI转换|
|B10|mergedProjects/VBA_3D/special_vbamesh/special_vbamesho.htm|MeshType、StepsPerWavelengthTet、统计查询|
|B11|mergedProjects/VBA_3D/special_vbasolver/special_vbasolver_solver_object.htm|FrequencyRange副作用和GetFmin/GetFmax|
|B12|mergedProjects/VBA_3D/special_vbasolver/special_vbasolver_eigenmodesolver_object.htm|方法/mesh参数、频率下限/模式数量、结果查询|
|B13|mergedProjects/VBA_3D/common_vbasolido/common_vbasolido_solid_object.htm|实体材料/体积/归属与查询时机限制|
|B14|mergedProjects/VBA_3D/special_vbapostproc/special_vbapostproc_qfactor_object.htm|场、损耗/能量计算与后处理副作用|

## 文档定义与设计决定

- B04要求组件/材料先存在；Cylinder.Reset为对象局部重置，不是工程重置；Segments=0是光滑解析面，不是0段导致无实体。坐标/range受WCS影响，生成器须显式global。
- B07背景定义包围结构的介质和扩展空间，不等于B08的六面边界；两者必须分别设置。B08.GetStructureBox不含扩展空间，GetCalculationBox含计算域，不能用其包围盒代替真空材料掩码。
- B03.AddToHistory立即执行并返回bool；相邻同caption会移除旧块。标题不是任意历史节点更新API。B03.StoreParameters支持互相依赖的参数批量提交，但没有对失败回滚或跨文件事务的保证。
- B03.Rebuild完整重放历史并删除结果；RebuildOnParametricChange只承诺保留适合参数变化保留的结果，不能笼统称无损。参数表独立持久，不能在几何历史里反复重设旧常量。
- B10.Mesh.StepsPerWavelengthTet描述最大边长相对最高频率波长；LinesPerWavelength明确仅Hex适用，不能作为Tet同义替代。该页面没有Mesh.Reset，不能按习惯给所有对象加Reset。
- B11.FrequencyRange官方明确会更改mesh并删除旧结果，可能询问保存。首阶段配置只作用无结果候选；不在已算场工程上直接调用。
- B12.SetFrequencyTarget限定下限、按升序计算；SetNumberOfModes输入int；GetNumberOfModesCalculated读结果实际数，不能用于证明请求设置。SetModesInFrequencyRange仅JDM适用。
- B13.GetLooseBoundingBoxOfShape是非紧全局包围盒，而且不能在history rebuild或structural macro执行中调用。这是建模验证器必须遵守的新边界；不能拿query名称推断任意阶段可用。
- B14.QFactor.Reset重置自身设置/结果，Calculate按当前场重算Q/损耗/能量；SetHField可指定本征模，缺相应E场时对电磁能量有等同假设。R/Q输出须说明能量/归一化来源，不从理想PEC模型推断默认电导的Q为物理真值。
- B02.Project.close明确不保存；先save再close，DE.close是应用层。B03.Project.Quit的保存提示条件不同。不能机械互换或在批任务中直接退出sheet。

## 与当前实现的差异及待验证项

当前预处理以MeshSettings.SetMeshType("Tet")/Set("StepsPerWaveNear","cell")绑定密度；本轮在本机Online Help的htm/html搜索未找到MeshSettings/StepsPerWaveNear定义（仅代表本次查找范围）。不据此说该扩展无效，但它不能代替B10明确文档契约。新A1选择文档化Mesh.Meshtype/StepsPerWavelengthTet路线，生效及保存重开还待真实探针。

既有预处理AddToHistory返回未检查仍待修；本轮不改代码。多数原生getter（mesh类型、频段、六边界、单位）已找到；method/target/requested modes/adaptation/Tet密度的全量配置读回没有在所读页面完整找到，禁止编造getter或settings database key。新契约SETTING_UNVERIFIED据此阻断“已验证ready”。

创建bootstrap拟使用所选安装自带Python/cst.interface，只创建保存空壳并正常关闭；编辑重建再用已加载工程Model.run。该选择避开当前现代Python ABI与CST2022扩展冲突，但未运行创建/保存/关闭。没有把旧官方Python探针或Managed历史验收算作本路线新证据。

Cylinder文档签名写Double，但官方示例range包含表达式字符串；这不构成所有Double参数都接受任意表达式的保证。新生成器优先在正确参数scope求值，通过RestoreDoubleParameter等读取参数数值、保留工程表达式引用；具体表达式编译/历史重放需要测试，不能为省事扁平化参数表。任意表达式求值不等于刷新依赖，旧concaveL实测边界仍以原日期记录为准。

本轮只证明文档定义与静态设计约束。材料Vacuum存在性、几何构造、设置生效、真实求解、R/Q与标准收尾均须在新Gate单独验证。

本轮定向离线53 passed（1.93s）及文档请求Schema17正例/25反例通过，报告保存在artifacts/first-stage-cst-contract-20261028与first-stage-contract-offline-20261028.xml。新操作未实现，这些数字不证明官方创建/新网格路线或真实收尾通过。

后续同日补核：[五项设置读回](cst-settings-readback-20261028.md)找到AKSGetNumberOfModes候选，并用cst_version核查4文件7scope的持久配置；没有把它误列为已验证Default/Tet getter。设置验证器按持久历史/live/行为分层，部分缺口仍待校准。
