# V05：Tet密度到实际网格的受控校准

## 执行范围

日期2026-10-28，安装版CST 2022.5 Release，2022-06-03，change 981760（原生output.txt）。只复制`model/Pillbox.cst`，原SHA256为`f3a4673772d576730373a6310b5a10f7ab5ba79dad9014c2540ddb8ab0de1133`。不修改参数表，宏前后比较全部参数名和表达式；设置追加唯一标题历史。没有EigenmodeSolver.Start、结果模板计算或原工程写入。

探针：[calibrate_tet_mesh.py](../test/support/calibrate_tet_mesh.py)的`cases`/`render`/`main`，复用[设置探针](../test/support/calibrate_cst_settings.py)的`run`及现有归属/退出门禁。每个case从同一原文件重新复制，避免前一case残留。设置统一为Default/Tet、nmodes=1、自适应关闭，频段沿用400–1200MHz，源参数表达式不变。现代Tet几何密度统一改成StepsPerBoxNear=2、Far=1，以减少几何约束遮蔽波长密度；这不是原模型完整mesh配置，也不是生产默认值建议。

官方Mesh帮助定义：StepsPerWavelengthTet按最高仿真频率的波长设置Tet边长尺度；MinimumStepNumberTet另有限制。Mesh.Update更新分布，CalculateMatrices按几何/材料生成网格，GetNumberOfMeshCells返回实际网格cell数。它们不等于求解器启动。观察到CalculateMatrices可以在此模型直接完成Tet网格生成。

## 证据

先导`artifacts/tet-mesh-calibration-af909286`，完整8组`artifacts/tet-mesh-calibration-20477690`。每个case保留原生Meshing successful、cells/min/max统计、当前Tet分区读数、输入配置、会话归属/退出及表达式对照。成功网格另外保存3d.slim SHA256，避免仅凭cell数认定网格相同。

原生`Result/Mesh_Input.Options.tet`实测可以按CBOR定长映射/浮点子集完整解码。测试专用有界读取器[tet_options_evidence.py](../test/support/tet_options_evidence.py)拒绝截断、重复键、尾随数据、未知类型/无限长度及超预算；依据[RFC 8949 §3](https://www.rfc-editor.org/rfc/rfc8949.html#name-specification-of-the-cbor-en)。这是本样本文件观察，不是厂商保证所有.tet文件都使用CBOR；不能当成生产通用格式插件。

## Version=1结果

本组继承源工程Tet的Version=1、cellsperwavelength策略。未显式设置现代波长密度时，源值为near=10、far=4。下表步长为网格器输入中的`d/step_near_model`、`d/step_far_from_model`，单位与本模型mm一致；不是从cell数反推。

|独立case|最终near/far读数|输入近/远步长mm|cell数|最大边长查询mm|网格SHA256前12位|
|---|---|---|---:|---:|---|
|旧4|10/4|24.982704 / 62.456760|16236|44.8525|ceb35f5d90a5|
|旧8|10/4|24.982704 / 62.456760|16236|44.8525|ceb35f5d90a5|
|现代4/4|4/4|62.456760 / 62.456760|1408|102.519|ed993baeca96|
|现代8/8|8/8|31.228380 / 31.228380|8720|52.2694|d7d01dedbc4c|
|现代8/4|8/4|31.228380 / 62.456760|8720|52.2694|d7d01dedbc4c|
|现代4/8|4/8|62.456760 / 31.228380|1408|102.519|ed993baeca96|
|现代4/4后旧8|4/4|62.456760 / 62.456760|1408|102.519|ed993baeca96|
|旧8后现代4/4|4/4|62.456760 / 62.456760|1408|102.519|ed993baeca96|

先导现代4/4再次得到1408个cell及相同网格hash。成功case原生输出均为Meshing successful，宏正常结束且归属进程退出。

### 能确定的映射

本版本/策略/模型内，现代near=N、far=M分别映射到输入步长约为`λ(fmax)/N`及`λ(fmax)/M`。1200MHz对应λ约249.827mm，4→62.45676mm、8→31.22838mm、10→24.982704mm。两分区独立，不是一个旧标量的别名。

旧StepsPerWavelengthTet的4→8没有改变现代配置、输入近/远步长或生成网格字节；混用顺序也不覆盖现代4/4。这确认旧命令在**本模型Version=1配置及本次调用链**没有改变实际网格，不能推广为所有CST模块/历史工程/版本都无效，也没有证据把旧n换算成现代near=far=n。

只改far输入、near不变时，网格器输入确实变化，最终网格却逐字节一致。本源模型为PEC背景内真空Pillbox，xmin磁边界；不能用这项观察推断开边界/有外部空间工程的far无效。单一近区真空腔不能完成far主导区域验收。

GetMaximumEdgeLength分别返回102.519、52.2694等值，明显大于相应输入step。这里分别记录“输入网格尺度”和“查询的最大边长”，不声称该step已证明每条实际边的严格上界，也不据此判定网格错误；查询/网格器尺度关系仍需独立网格拓扑审查。此轮不是精度或收敛验收。

## Version=0负例

额外副本只把已存在Version键改为0，再分别设置旧密度4/8，作为探索性对照，不预设它等于某个“旧模式”。探针目录`tet-mesh-calibration-3ad349e8`及`tet-mesh-calibration-4eecea83`。

Version=0可读回，但旧4和旧8 case均生成0个cell，原生明确报：The mesh you are trying to generate is not supported by the current solver. Mesh generation is aborted. 宏仍完成，进程退出0；这直接证明不能用宏标记/退出0冒充网格成功。先导脚本曾因缺少Options文件只抛FileNotFoundError，现修正为先保存mesh统计和原生输出、检查cell>0、Options存在和Meshing successful，失败报明确诊断路径。

Version=0不是已验证可用的兼容切换开关，不能加入生产自动回退。旧密度的其他可用版本/模块边界仍未证明。

## 统一接口设计调整

A1新建工程的`mesh.cells_per_wavelength=n`明确为应用层“统一近远波长密度”请求：按已校准Version=1通道分别写near=n、far=n和cellsperwavelength策略，写入历史，并分别读回；这是一项新接口策略，不是旧API转换结论。导入工程仍完整保留不同near/far/policy/Version，不能压成标量，也不静默覆盖已有设置。

未知版本/通道缺profile仍SETTING_UNVERIFIED；不得退回旧setter、擅自切Version=0或用cell数补证。生产底层尚未按此迁移，其他method/target/adaptive缺口仍使G03未通过。

## 剩余边界

- 未启动本征模，不证明频率/RQ正确、收敛或MCP对话闭环。
- 非真空材料、开边界/外部空间、其他policy、局部加密、旧版CST及旧工程配置未校准。
- 实际最大边长与输入step关系需要另行审查，不能用密度保证固定cell数或精度。
- 原始模型副本/网格按本轮结束后清理；具体收尾、测试及保留证据见补记。

## 收尾补记

11个副本会话全部标准退出，9个成功网格、2个明确网格拒绝；全部表达式逐项一致，4个校准根source-check确认原工程hash不变。完整比较见主根acceptance-summary.json。最终安全/CBOR拒绝/归属/环境/索引32 passed（2.23s），artifacts/v05-mesh-final-20261028.xml；文档更新后索引2 passed（0.69s），diff空白检查通过。

全部CST进程已退出后，核实本轮4个校准根和2个pytest根边界，清理55个模型/配套目录目标；保留宏、会话/源hash、参数表达式TSV、保存历史摘录、网格hash、原生输出、约3KB的网格器原始Options及JSON译码。原始.cst/3d.slim网格已删除，需要重跑才能访问；artifact不保证随Git迁移。D盘余量23.65 GiB，未清理其他任务/用户原工程。
