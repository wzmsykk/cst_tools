# CST Tools对齐COMSOL MCP的功能目标

日期：2026-10-28。目标设计，未实现。本文修正此前将完整目标收窄为HOM运行控制的范围：**总体目标是面向CST的完整建模—配置—求解—分析工作流，功能层面对齐已选COMSOL MCP实现；GUI、CLI、MCP共用该底层。** 14项运行操作只是底层子集；首阶段必须完成[对话建模到结果闭环](mcp-first-stage-conversational-gate.md)，工具数量/名称不是最终约束。

现代MCP协议是接口标准；COMSOL MCP是功能覆盖参照；CST官方接口和实测决定具体可实现性。三者不混用。对齐任务能力，不机械复制COMSOL标签树、Java属性、物理接口或第三方取消机制；遇到CST没有等价能力时明确记录缺口，不把工具空壳算完成。

## 1. 固定参照与本轮核查

参照并非“COMSOL官方MCP标准”，而是两项既有设计已选的第三方实现：

- [wjc9011固定提交](https://github.com/wjc9011/COMSOL_Multiphysics_MCP/tree/0f6b2c588a08da5ac66915e4f1fce7c07966763e)：src/tools内model、session、parameters、geometry、physics、mesh、study、results及electrochemistry模块。
- [Ching-Chiang固定提交](https://github.com/Ching-Chiang/comsol-mcp/tree/ccca65aa8277d1205c5de5fb6221e460aca5997a)：comsol_mcp内connection、model、params、geometry、physics、solver、snapshot、workflow模块。

本轮读取固定提交的工具模块源码并生成函数索引，补查代表操作的参数与实现分支。索引/原始源码及SHA256在`artifacts/comsol-capability-alignment-20261028/source-index.json`；不保证随Git迁移。只读审查，不是COMSOL运行验收，也不是其全部依赖和算法的完整审计。对外注册列表须在对应模块的register和装配处确认，不能把AST中每个辅助函数当工具数量。

## 2. 功能对齐矩阵

“当前基础”描述已存在的底层代码，不等于已发布MCP工具；以下新增操作名均拟定。

|能力ID/用户任务|COMSOL源码参照|CST Tools当前基础/缺口|统一底层目标与验收|
|---|---|---|---|
|C01 连接与工程管理|comsol_start/connect/status；model_create/load/save/clone/inspect；server_connect|有CST版本发现、Runner连接、副本和快照；缺通用创建/模型目录操作|明确实例/工程ID，创建、载入、检查、保存/另存、复制和关闭自有工程；跨两个工程操作无串线，旁观实例不受影响|
|C02 参数与表达式|param_get/set/list/description；evaluate_expressions；set_parameters|可读取.cst参数、任务写参数及表达式恢复；缺统一编辑/求值接口|参数枚举/描述/批量修改/依赖求值/读回；明确3D/DS/子工程，表达式保存不扁平化。求值不等于刷新，修改须报告结果失效|
|C03 几何与选择|geometry_add_block/cylinder/sphere、boolean_union/difference/import/build；create/update/delete_feature|CST有对象/历史接口，但当前框架非通用建模服务|有类型的基本实体、变换、布尔、导入、选择集与重建；基于稳定对象引用/历史，保存重开和参数重建仍正确|
|C04 材料与物理设置|physics_add/configure_boundary/set_material、multiphysics_add；physics feature与selection|已有Eigenmode及部分边界预检；没有通用材料/端口/边界配置契约|先覆盖电磁材料、背景、边界、端口/激励及求解器种类；读回实际设置、作用域及许可前提。COMSOL声学/流体/PDE/电化学不凭同名照搬，列出CST模块对应性|
|C05 网格|mesh_list/create_sequence/create/info；ensure_mesh|已有固定Tet密度、可选不改mesh、收敛分析|统一查询/配置/生成/质量与统计/收敛记录；区域选择和局部加密独立审查；不把cells-per-wavelength当全部mesh控制|
|C06 求解与研究配置|study_create/list/solve/solve_async；configure_solver；solutions/datasets_list|已有HOM、标准批次、专用优化代码；缺通用study定义和配置目录|建立simulation definition：solver、频率/时间/模式设置、mesh、PPS、参数任务；提交、查询、合作停止和失败恢复共用现有执行权威|
|C07 扫参和优化|param_sweep_setup、study相关操作；COMSOL优化是否暴露单列核查|已有标准批次、HOM以及WTC/TM020；新优化能力仍受O表阻断|有限参数组合生成、批任务与注册优化策略；记录展开数量/预算/定义哈希，续跑不改问题。不能把HOM扫频等同通用参数扫描|
|C08 结果目录、数值与表达式|results_evaluate/global_evaluate/inner_values/outer_values、datasets_list|已有原生标量/PPS、R/Q XYZ、HDF5、模式匹配；缺通用目录和受控表达式求值|显式工程/子工程/任务/数据集/模式、单位及revision；标量、曲线、场点/积分/重叠各有Schema。CST仅0D/1D官方Python读取与三维场通道分开|
|C09 数据与图像导出|results_export_data/image、exports_list/plots_list|有诊断ZIP、部分数值/场导出；未建立图像/绘图统一目录|数据/图片导出、已有绘图/导出项枚举，受控工件引用；大文件不塞工具响应。图像必须真实生成并核对来源/视图，不把已有截图当新求解结果|
|C10 快照/版本与可见工作流|model_save_version、save_main_model_snapshot、commit_current_main_model、model_tree|已有快照/hash、cst_version分析基础及GUI对比|工程树/历史/变更摘要、保存/重开、版本比较与受控迭代；公开事实来源，不另造与cst_version重复的私有格式解析器|
|C11 可靠执行与诊断|后台study状态、workflow_info、mcp_tool_audit|已有Runner/ACK/采用/收尾/恢复，可靠性结构较完整但有pending门禁|全部上述能力共用命令、授权、控制权、日志/源码映射、结果采用和资源归属；不采用内存daemon线程作为唯一任务权威|

C01–C11全部是总体目标项，不因第一版未做就移出目标。每个物理模块若没有CST等价接口，要写明unsupported及原因/替代工作流，不承诺复制COMSOL全部物理方程和许可产品。需要确定每项对应官方CST对象、参数及实际效果后才能冻结执行Schema。

## 3. 共用底层的必要扩展

仅“提交一次HOM配置”的服务不足以覆盖此目标。统一契约扩展为三个生命周期对象，仍在同一个公共应用服务内：

1. **工程定义**：project/document/subproject、对象树、参数、材料、几何、边界、网格、求解与后处理定义，带document_revision；只改变模型定义不等于已经求解。
2. **变更操作**：typed change set、expected_document_revision、影响摘要、重建/结果失效计划。先在副本应用、核对历史/读回、保存并发布新revision；失败保留原定义和诊断，不假定CST内部多步修改具备事务回滚。
3. **执行与结果**：基于不可变definition_revision启动run/task，绑定参数、结果revision及工件。正在计算时禁止原地修改其定义；编辑分支生成新revision，不覆盖已确认结果或当前Worker。

document_revision（工程定义）、checkpoint_revision（扫描状态）、result_revision（结果快照）分别使用，不以一个mtime或run_id代替。既有统一契约的控制/幂等/Error/Artifact继续共用；不为几何操作另造任务库、进程管理或日志框架。GUI/CLI/MCP调用相同工程编辑和结果服务，不能GUI仍直改文件而MCP走新模型库。

操作族拟定为project、parameters、geometry、selection、materials、boundaries/ports、mesh、simulation、results、artifacts。每族按实际任务拆具名工具和有类型Schema；不提供`call_any_api`、任意VBA/Python或任意property字典作为“已对齐”的捷径。表达式是CST受控计算表达式，不是Python解释器。

首版一个服务进程仍绑定一个项目授权根，可有显式受控文档/子工程对象；多项目通过同一服务实现的不同实例承载，不引入全局“当前模型”。完整多工程目录/跨工程引用在C01子契约中设计，不能暗自借用Active3D或随机连接。

## 4. 分层路线与完成定义

|阶段|交付与依赖|不得扩大宣称|
|---|---|---|
|A0 全目标静态设计|本矩阵、官方CST对象对应、作用域/副作用、定义与变更契约；SDK宿主证据|本轮仅确立覆盖和框架扩展；C01–C10新操作Schema尚未全部冻结|
|A1 对话驱动最小完整闭环|从空白Pillbox建模→仿真设定→真实求解→Frequency/R/Q→结果文件→安全收尾；统一公共服务|通过标准是[首阶段G01–G08](mcp-first-stage-conversational-gate.md)，只读或HOM控制子集不足以通过|
|A2 扩充工程编辑与建模|C01–C05和C10最小完整子集：新建/打开→表达式参数→实体/布尔→材料/边界/端口→mesh→保存/重建|必须是实际CST对象操作，不能仅改配置JSON或生成未执行脚本|
|A3 通用执行与分析|C06–C09：已建模型提交、参数扫描、注册优化、结果目录/曲线/场算子/图片导出|每种求解器/后处理单列可用前提；专用优化缺口和场域限制仍独立验收|
|A4 扩展对齐验收|在A1闭环基础上增加多模型/算例、场/图片、参数修改再求解、版本比较及三入口一致|原模型/旁观CST不受影响；核对实际产物、唯一采用、表达式、历史重建和标准退出|

M4/M5及真实CST门禁不废弃：它们是A1或相应能力的验收子项。真实求解、创建CST实例或修改用户模型仍须另行授权；本轮仅静态设计。

## 5. 下一轮静态工作

- C01/C02先冻结工程身份/生命周期、参数读写/求值/结果失效和change set接口，清楚区分官方Python的modeler/schematic与VBA作用域。
- C03–C05逐对象读CST官方帮助与可见底层：Solid/Brick/Cylinder/Material/Boundary/Port/Mesh等实际命令、历史行为和读回能力；查不明就登记unknown，不按COMSOL方法名猜CST对等。
- C06定义simulation对象，区分单次求解、HOM窗口扫描、通用参数扫描和优化；补全各种输出的数据集/模式/参数组合身份。
- C08/C09按算子及端到端效率选择原生结果、VBA积分或场导出/Python分析，复用既有性能设计；通用曲线/绘图/图片导出仍待专门子契约。
- 更新统一接口及删除表时将工程编辑功能的旧GUI/cst_version调用点纳入，不再设定最终14工具上限，不新增重复解析库/兼容框架。

本轮检查只证明参照源码中存在相应操作和现有CST差距；并未运行COMSOL或CST，也未证明所有第三方操作正确。功能对齐按上述端到端任务完成情况验收，不以工具数或同名函数数计完成率。

A1静态子契约已冻结：[工程创建/参数化建模/配置/single-simulation/结果输出](mcp-first-stage-interface-contract.md)，官方来源和持久化边界见[本轮核查](../knowledge-base/cst-first-stage-api-semantics-20261028.md)。九操作复用公共身份/控制/幂等；不再仅靠14控制操作实现首阶段。partial readback及新创建通道仍是未验实现门禁，不把字段冻结当功能可用。
