# 通用几何与选择集接口设计

更新：2026-11-04。GEO-1–4当前实现与验收统一见[GEO-2–4生产实现与验收](geometry-production-implementation.md)；本文保留官方语义、设计取舍与分阶段证据。§8–14是同日较早离线阶段的带日期记录，其中“尚未/禁止/待实现”不再定义当前API；§15原则已由history_program/managed_history落实。当前MCP14工具签名已接入，GEO独立许可已实际校准，A1旧许可仍失效。

## 1. 目标和最小范围

继续复用ApplicationService、Runner、文档revision、ProjectRunLock、同一发射器/检查器及G03验证链。GUI、CLI、MCP调用相同业务操作，不再建立几何管理器、选择服务、原生会话池或第二份.cst解析库。

|能力|GEO v1目标范围，均须后续校准后实现|暂不开放|
|---|---|---|
|作用域|显式document/revision；root MWS的3D modeler；mm；全局WCS；框架拥有的完整声明式模型|DS、子工程、接管活动窗口、任意已有CAD增量编辑|
|组件|显式创建根组件，先于实体创建；精确存在性检查|层级组件、删除组件、自动清空/重命名组件|
|基本体|Brick；XYZ轴Cylinder（含inner_radius=0或合法空心）；完整光滑Sphere|薄片、曲线、锥/环体、球冠、分面几何、CAD导入|
|材料引用|目标仅允许预先核实的内建Vacuum/PEC；引用而非创建材料|任意材料/材料库、各向异性和材料函数；这些归后续材料阶段|
|变换|单个实体、全局向量平移、原位变换；集合解析为有序成员，调用方显式逐实体请求|复制、阵列、自动命名、touch；旋转/缩放/镜像待独立冻结|
|布尔|两个同组件、同材料的体实体；union/difference/intersection；第二操作数消耗|keep_tool、跨组件/跨材料布尔、自动SplitShape、隐式修复|
|删除|显式删除单个活实体，保留其历史身份和消费记录|递归/级联删除、删历史节点、删除后复用ID|
|选择集|文档元数据中的命名实体集合，成员是逻辑object_id；确定性展开|面/边/点、空间谓词、正则/通配、组嵌套、自动重绑定|

这是第一批通用几何原语，不承诺全部CST建模功能。材料/边界/网格/场域仍使用各自能力门禁；能保存几何不代表能够按Pillbox的求解/后处理配置直接计算。

## 2. 官方语义核对

|官方对象/方法|文档定义|设计约束|
|---|---|---|
|Brick.Reset/Name/Component/Material/Xrange/Yrange/Zrange/Create|组件和材料须已经存在；范围受当前WCS影响；示例允许Zrange表达式|先核组件/材料；显式global WCS；各轴min<max，保留表达式|
|Cylinder.Axis/Outerradius/Innerradius/*center/*range/Segments/Create|axis决定使用哪一个轴向range；center受WCS影响；Segments=0为光滑表示，>2为分面|只发射轴向range和两个横向center，不用三个center与range重复定义轴向位置；v1固定segments=0|
|Sphere.CenterRadius/TopRadius/BottomRadius/Center/Segments|CenterRadius定义半径；Center受WCS影响；示例Top/BottomRadius=0|v1完整球固定axis=z、top/bottom=0、segments=0；不猜任意球冠参数|
|Solid.Add/Intersect/Subtract|结果存于第一个实体，第二个被删除|target ID存活，tool ID标为consumed；不是返回两个新对象|
|Solid.Insert|差运算但保留第二个实体|有文档入口，不把它等同于Subtract；v1明确不开放keep_tool|
|Transform.Transform("Shape","Translate")|作用于Name等指定对象；MultipleObjects=False会替换原对象，True创建副本；GroupObjects是与原对象并体语义|原位平移显式关闭copies/unite/touch/picks；不用GroupObjects创建命名选择集|
|Transform.AddName|仅适用于文档列举的组合，例如实体CommonCenter等情形|不据名字把它当通用多实体列表接口；v1逐实体发射|
|Group.Add/AddItem/Delete/Reset|类型normal或mesh；AddItem使用全局名称；Reset删除全部组及成员关系|v1集合不映射成原生Group；绝不使用Group.Reset进行清理|
|Solid names / Global names|实体名称为component:solid；全局名称附类型，如solid$component:solid|客户端传逻辑ID；原生名称只由服务器按方法要求生成；两个语法不混用|
|Pick|拓扑id与pick-list index不同；列表index从0开始且可倒序；几何产生新面/边/点时id可能改变|不提供跨revision永久face_id；不把列表索引当面ID|
|PickFaceFromPoint/PickEdgeFromPoint|点坐标明确为global|不继承当前WCS，不擅自添加文档没有的tolerance参数|
|PickPointFromCoordinates|局部WCS活跃时使用局部坐标|与前两种Point方法不能统一按同一坐标规则转发|
|Pick.ClearAllPicks|清除点、边、面拾取|仅在已证明归属的候选中管理临时状态；不是删除命名集合|
|SelectTreeItem|选择导航树项并更新视图，成功返回True|UI选中不证明实体存在、集合持久化或几何可用|
|Component.Delete|删除组件及内部所有实体|v1不提供此隐式级联；Hide/Show也不属于几何变更，其文档明确一般不入历史|
|AddToHistory|立即解释执行内容；成功才返回True；若上一块同caption，会按同内容假设移除上一块|每个几何feature有唯一服务器标题；不重复使用固定Geometry标题；False不假定事务回滚|
|Rebuild / RebuildOnParametricChange|前者重新执行历史并删除所有结果；后者保留可保留结果、其余删除|只重建新候选；不对旧定义/已确认结果或用户工程执行|

上述是文档定义，**不是新功能实测**。Shape枚举index基准、原生组保存成员、布尔异常/拆分命名、平移替换后的名称和新参数重建仍需下文校准。

## 3. 身份、坐标和定义数据

- 公共请求仍使用control_handle/request_id、document_id/expected_document_revision。客户端不能传活动工程、任意原生路径/名称或VBA代码。每份文档绑定唯一root MWS，3D对象不可投向DS。
- object_id是文档血缘内的逻辑身份，不是CST拓扑ID。组件及对象ID大小写无歧义、不得包含`: / \\ $`等原生命名分隔符；显示名独立，不能用显示名寻址。长度/字符预算是服务策略，仍需CST校准，不冒称CST官方上限。
- 同一object_id在原位平移、作为布尔第一个操作数时存活；消耗/删除后成为tombstone，不能自动指向新实体或复用ID。旧revision仍可只读查看其旧映射。
- 原生qualified name由服务器从组件和实体映射产生；不得根据视图选中、GetNextFreeName或字符串后缀猜测结果名。每次读取需绑定revision、源SHA及证据时间。
- 参数及长度表达式复用现有有预算的算术AST和名称检查；保留表达式，不以当前求值覆盖。参数表独立保存，几何历史引用参数。只做明确的字段quantity约束，不宣称完整符号量纲推导。
- 坐标固定global、长度单位mm。Cylinder.transverse_center_mm为两个表达式：axis=x对应[y,z]；axis=y对应[x,z]；axis=z对应[x,y]。轴向位置只由axial_range_mm定义。
- 变换v1仅translation_mm=[dx,dy,dz]。发射前显式WCS.ActivateWCS("global")、Transform.Reset，再设Name、Vector、UsePickedPoints=False、MultipleObjects=False、GroupObjects=False、Repetitions=1、Touch=False并执行Shape/Translate。其可用性仍需原生校准。

GEO Spec使用`parameters + components + geometry.features + selection_sets`：features是唯一几何意图、按声明顺序重放；对象存活表/原生名称表由其派生，不能再维护第二份独立几何真值。参数允许整批依赖校验；几何操作只能引用该步骤之前已创建且仍活跃的对象。不自动排序具有副作用的布尔/变换步骤。

每个变更的feature_id由服务器在受理时分配并持久绑定request_id和步骤；history caption包含该ID。参数新值重建使用同一声明步骤，不能因caption相同丢掉上一个不同操作。删除是在历史末尾声明Solid.Delete，不删除早期创建/操作步骤，否则参数重放可能丢失依赖。

## 4. 复用的公共接口

下表描述完整目标。GEO-1仅在既有公共定义事务接通严格声明契约与投影，原生保存及MCP签名扩展未开放；具体可调用边界见第8节。

|现有入口|拟扩展契约|副作用边界|
|---|---|---|
|apply_model_changes|changes增加create_brick/create_sphere、扩充create_cylinder、translate_solid、boolean_solids、delete_object、define_selection_set/delete_selection_set；沿用set_parameters/ensure_component|只产生经校验的新声明式草稿；不启动CST，不把请求值称为原生读回|
|inspect_model|原签名不变，输出增加声明feature、派生对象表、selection_sets、verification及capabilities|只读不可变文档和已保存证据；不为读取暗中开CST；预算超限用已有ArtifactRef或明确拒绝，不静默截断|
|save_project|拟增加必选validation_target=geometry或simulation|geometry目标保存几何文档，ready=false、无definition_revision；simulation目标须完成相应solver/后处理验证，才允许ready=true|
|configure_simulation/submit_run|仍使用公共冻结定义和原RunStore|不能把任意几何保存成功、选择集存在或A1旧校准，直接当可求解证明|
|get_project_status/get_operation_result/control_project|沿用既有异步槽、控制权、幂等及错误/恢复|不为几何另建队列、结果格式或停止服务|

`save_project`当前将A1几何/仿真验证一起收口。实施时必须先明确几何文档保存与仿真ready的区别，不靠放宽A1允许表让通用几何通过。几何only并不删除或撤销旧definition/result revision。

### 变更字段约束

|op|主要输入|后置条件|
|---|---|---|
|create_brick|object_id, component_id, material_id, bounds_mm={x:[min,max],y:[min,max],z:[min,max]}|新ID未使用；组件/材料存在；体积正；新实体live|
|create_cylinder|object_id, component_id, material_id, axis, transverse_center_mm[2], axial_range_mm[2], outer_radius_mm, inner_radius_mm|0≤inner<outer、轴向min<max；不传segments/局部WCS|
|create_sphere|object_id, component_id, material_id, center_mm[3], radius_mm|完整球，半径正；不传球冠/分面设置|
|translate_solid|target_id, translation_mm[3]|原位变换；名称/ID须读回确认；旧拓扑证据失效|
|boolean_solids|operation=union/difference/intersection, target_id, tool_id|两个不同live实体、同组件/材料；target保留，tool消耗；禁止隐式保留/复制|
|delete_object|object_id|只删除该实体；引用失效需在同批显式处理|
|define_selection_set|selection_id, entity_kind=solid, members=[object_id,...]|非空、唯一、均在最终模型存活；成员顺序规范化；不允许动态查询或集合递归|
|delete_selection_set|selection_id|删除文档集合定义，不调用Group.Reset或ClearAllPicks|

整批变化在副本Spec上预检：存在性、依赖/消费、参数、预算和所有最终集合成员全部有效后才接受新草稿；不能发布一半成功的变更。建议继续≤64变更/批、≤128参数；新增初始上限为128个live对象、32组件、64集合，每集合≤128成员；累计geometry.features≤512，包含删除/消费后的历史，防止只限制活对象却无限积累历史，请求/响应仍受已有字节预算约束。这些是拟定资源预算，不是CST能力常数。

### 设计示例

```json
{
  "document_id": "cavity",
  "expected_document_revision": "REVISION",
  "changes": [
    {"op":"set_parameters","values":{"R":{"expression":"5","quantity":"length","description":"孔半径"},"H":{"expression":"20","quantity":"length","description":"高度"}}},
    {"op":"ensure_component","component_id":"vacuum"},
    {"op":"create_brick","object_id":"body","component_id":"vacuum","material_id":"Vacuum","bounds_mm":{"x":["-20","20"],"y":["-20","20"],"z":["-H/2","H/2"]}},
    {"op":"create_cylinder","object_id":"tool","component_id":"vacuum","material_id":"Vacuum","axis":"z","transverse_center_mm":["0","0"],"axial_range_mm":["-H","H"],"outer_radius_mm":"R","inner_radius_mm":"0"},
    {"op":"boolean_solids","operation":"difference","target_id":"body","tool_id":"tool"},
    {"op":"define_selection_set","selection_id":"vacuum_volume","entity_kind":"solid","members":["body"]}
  ]
}
```

这是未来apply_model_changes的业务部分，control_handle/request_id仍必需，示例省略；当前工具不能调用它。之后拟调用save_project(...,validation_target="geometry")，不产生可求解definition。参数改变后重新在候选重放，不能把示例变成每轮回写固定参数的宏。

## 5. 三种“选择”的边界

1. **文档选择集**：本接口的持久语义。只保存逻辑成员，随document_revision不可变；消费时展开成明确实体引用，并再次检查成员存活。不是实时UI选择，也不是声明一个集合就获得电磁边界/网格/积分语义。
2. **原生Group**：官方支持normal/mesh类型及不同global-name成员，但所查Group页没有枚举组/成员的getter。组成员的实际存储、重建及读回路径未校准；v1不自动导出CST Group，不虚构GetMembers/Group.Type。未来若需要导出，须沿共用只读来源核查真实成员结构并单独验证。
3. **临时Pick/树选择**：只供拥有的候选会话内部操作使用。Pick语句可被包含在历史中供消费步骤重放，但Pick列表本身不授予持久、跨revision的选择身份。UI隐藏/显示或树选择不构成几何验证。

若布尔消耗/删除了集合成员，默认拒绝悬空引用；同批必须显式重定义/删除集合，不把tool静默替换成target。集合不嵌套，因此无需另一套依赖引擎。

面/边/点后续需另行冻结：引用至少绑定document_revision、对象及几何/拓扑证据；任何参数、布尔或变换后重新解析。PickFaceFromPoint只说明如何拾取，不证明唯一性；不能加一个容差字段就宣称可靠选面。GetAnyFaceIdFromSolid只是首个面，不等同top/front；Pick列表index也不是拓扑id。v1直接返回UNSUPPORTED_CAPABILITY，不用坐标猜选或最新ID重试。

## 6. 历史、验证与结果失效

|数据/操作|持久化位置和保证|
|---|---|
|参数表达式/说明|独立参数表与文档Spec；几何历史引用表达式，不在每个历史块重写常数|
|组件/创建/平移/布尔/删除/WCS|检查过的AddToHistory，必须保存重开和改参数Rebuild后仍符合对应后置条件；不是单次直接调用就算持久化|
|逻辑对象、featureID、文档选择集|同一不可变文档元数据；可由声明步骤派生映射，不伪装为CST原生Group已读回|
|Pick列表/视图状态|服务不承诺跨会话持久化；内部需要时与消费操作一同发射并清理，不改用户其它实例|
|已有结果/definition|保持不可变；新草稿撤销的是自身ready。任何重建只作用于新候选，不能因invalidate_results=true删除历史已确认产物|

保存流程仍是意图→新副本/绑定身份→发射/语法门禁→执行历史并检查返回→Rebuild→观察/保存/正常退出→共用只读投影与重开验证→发布新文档。需要仿真时再满足现有G03/定义/后处理门禁。停止或失败保留候选和已完成步骤；退出/身份未知先恢复，不重放“也许已成功”的编辑。

### 查询不能混进结构历史

- Solid.DoesExist、GetMaterialNameForShape、GetVolume等可作候选观测来源；数量/索引基准、返回单位、体类型及合适调用阶段要逐项校准。GetNameOfShapeFromIndex的基准未在所查定义中说明，不套用Pick的0基规则。
- GetLooseBoundingBoxOfShape返回global的**非紧包围盒**，不能当精确尺寸；明确禁止在history rebuild或structural macro执行期间调用。不能将它插到AddToHistory里，也不能未经校准就认定Model.run控制宏等于文档允许的post-processing。未找到/验证合法观测通道前，该字段保持unverified，不能伪造observed。
- 现A1观察器用的是Boundary.GetStructureBox/GetCalculationBox，属于整个结构/计算域，不是多实体各自包围盒；不能原样拿来给每个对象做尺寸证明。
- WCS查询还受fast opening/Rebuild信息可用性限制；文档提及的ResultTree.UpdateTree/FastModelLoad不是每种query的通用修复。v1用显式global设置减少依赖，不把推测恢复调用写入公共流程。
- 多个不连通部分可属于同一Solid（SplitShape文档有此背景）；一个名称存在、IsSolidShape=True或体积正，不证明单连通、没有hybrid或与请求几何完全一致。布尔结果类型/材料/消耗与保存历史都须分别核实。

verification逐项保留requested/observed、单位、revision/源hash及documented/native-query/persisted-history/replay等来源。声明式投影不是原生几何；Box/Volume不是任意CAD等价性证明。几何文档可发布必须满足该profile所有必需校准；仿真ready另判，不能用部分字段通过掩盖其它unknown。

## 7. 实施切口与验收顺序

|阶段|复用/修改位置及状态|完成门禁|
|---|---|---|
|GEO-0 已完成设计与来源|官方帮助核对、统一接口设计与知识记录|不将COMSOL原生能力当成CST已验能力|
|GEO-1 已完成声明契约/投影|现有GeometryChange/GeometrySpec、definition_editing、geometry_contract及共享算术|声明/参数/集合检查通过；原生能力由GEO-2独立验证|
|GEO-1.1 已完成离线历史编辑与依赖诊断|扩充同一类型化变更和公共投影，复用CAS、revision、intent/commit/result|下文H1–H7离线通过；不新增原生调用、队列或CAD内核|
|GEO-2 已实现并独立校准|共享原子发射/检查、实际Model.mod提取、native_definition_builder及两会话原生观察|O1–O8及C1–C7通过，GEO许可绑定当前源码与实际证据；A1许可不混用|
|GEO-3 已接公共适配|既有ApplicationService/Runner/HTTP/MCP入口；GUI/CLI只适配同一服务|实际SDK公开链及离线适配/故障通过；桌面新签名重新加载后对话验收独立|
|GEO-4 受限profile闭环通过|对应solver/G03/mesh/PPS及原RunStore|XYZ小网格各一次实际求解，完整核验才ready；不是多材料/任意边界/完整CAD证明|
|后续独立阶段：面/边选择|命名规则、合法原生解析和匹配数核验|坐标/容差/拓扑失效独立校准，不阻塞实体选择集首版，不冒充原生Group已实现|

|校准ID|无求解受控副本用例|必须保留的证据|
|---|---|---|
|C1|非零位置Brick、XYZ实心/空心Cylinder、完整Sphere|参数表达式/材料/组件、总数与准确名称、正体积及单位；保存重开及新参数重建；未开放index枚举|
|C2|非零global平移，故意预设local WCS|显式global生效、向量表达式重放、名称/对象映射；copies/unite关闭|
|C3|简单可解析重叠体的Add/Subtract/Intersect；不相交、相切、完全相减|原生返回/错误、目标保留/工具消耗、材料/体类型/空结果；不自动Split或修复|
|C4|多步不同命令、同caption反例及编辑后新候选重放|验证显式顺序/唯一标题与输入输出名称；不依赖UI或隐式当前位置；不是靠日志打印成功|
|C5|逻辑集合保存/重开、参数与feature修改/移除、成员消费|旧revision和身份保留不变，输出映射与声明核对，悬空集合拒绝；不声称创建原生Group|
|C6|查询阶段对照|Model.run合法整体StructureBox/CalculationBox与实体事实观察；不调用受结构宏限制的逐实体LooseBBox，不承诺紧包围盒|
|C7|第二步失败、保存/发布响应丢失、停止及退出未确认|旧定义/结果hash不变，半成品不发布，不重复原生操作，只处理拥有的副本；诊断映射至feature/输入字段|

GEO-1–4已在上述受支持范围实现与验收，当前源码及证据见生产实施页。本文件不自行授权新的求解范围、原工程修改、提交或推送；§8–14保留较早阶段的接口演进与原批次验收，不作为当前禁止表。

## 8. GEO-1已实现契约与当前调用边界

实现：[公共定义事务](../csttool/definition_editing.py)、[声明投影](../csttool/geometry_contract.py)、[唯一Schema](../data/first_stage_contract.schema.json)；离线测试：[geometry_contract_test](../test/geometry_contract_test.py)。沿用ApplicationService/Runner的definition操作、项目锁、CAS、不可变revision、intent/commit/result与丢响应对账。未增加后端、队列、私有文件解析器或几何计算内核。

- 公共服务的apply_model_changes参数显式增加`geometry_profile="geometry-v1"`；**每次GEO编辑均须带此字段**。无字段仍按现有A1契约验证。只能在没有A1几何/背景/边界/仿真配置的文档上启用，不隐式迁移或同时维护cylinder与features。
- 内部/Runner可提交`kind="definition", operation="apply_model_changes"`及上述字段；MCP工具的geometry_profile/validation_target签名尚未扩展，不能照此向当前桌面工具传参。GEO-3才同步宿主入口，不新增另一套工具。
- GEO Spec为parameters、components、geometry(profile/features)、selection_sets；features存原始表达式。服务器从父revision、完整请求及步骤确定feature_id，绑定既有幂等/CAS；同一请求重试不生成另一组feature。组件先声明，几何引用按原始顺序验证，参数可在整批中前向引用。
- 新revision附`geometry_projection`：evidence=declaration、native_verified=false，包含拟定native_name、唯一caption、参数求值后的输入、对象live/consumed/deleted和有序集合成员。**native_name是规划映射；没有创建原生对象。** 不给出布尔结果体积、精确包围盒或拓扑等价性；全相减/相切等仍待C3。
- 只接受实体选择集；同批删除/消费成员后必须显式删除或改写集合。没有隐式丢成员、Group/Pick副作用或自动重绑定。历史对象ID不复用；集合可显式同ID改写，成员排序确定。
- 参数求值复用A1有界算术；几何直接及传递依赖均须标注length，不宣称完整量纲演算。请求/存储Spec均做结构检查；限制4096字符/表达式、256 AST节点、参数依赖深度及参数/对象/集合/累计feature预算；Spec＋投影的UTF-8缩进JSON≤512 KiB，超限在intent前拒绝。文档读取继续使用共享严格读取器，仅文档上限明确为1 MiB（执行快照默认64 KiB不变），避免写入后无法重载。

### 保存与仿真状态

|事实/字段|GEO-1行为|防止的误判|
|---|---|---|
|草稿已持久化|state=draft，新document_revision可重新读取/恢复|文档持久化不等于.cst几何已保存|
|原生几何已保存|geometry_saved=false|不能用父空工程的model_path/source_sha256证明新几何存在|
|请求保存目标|save_project的Schema接受validation_target=geometry/simulation；GEO必须显式给出|未指定目标返回INVALID_ARGUMENT；不会默认升级到仿真|
|GEO原生保存门禁|两种目标均在intent/native dispatch前返回UNSUPPORTED_CAPABILITY，草稿和旧结果保留|GEO-2校准前不写假saved，不借旧A1stamp执行|
|仿真就绪|ready=false，definition_revision=null，validation_target=null|声明投影/选择集不构成求解授权|
|A1旧保存链|默认simulation目标，经现有G03才geometry_saved=true、ready=true|未扩大A1命令白名单；本批变更后旧原生stamp失效，须另行校准|
|关闭|未保存GEO拒绝close(save)；discard_candidate只关闭文档，保留不可变草稿证据|关闭不能隐式原生保存/求解，恢复不会重放未提交原生操作|

inspect_model重新投影并核对存储投影；GEO记录即使重新计算revision hash，也不能声称saved/ready/native保存。参数修改重新检查全部历史和最终集合；违反尺寸约束时整批拒绝，旧revision不变。保存的target字段表示已成功发布的目标，不能提前复制请求值。几何only原生保存后应允许geometry_saved=true而ready=false的状态，在GEO-2接入真实保存证明时实现；本批不预置可被伪造元数据绕过的发布入口。

旧WinWrap校准JSON及历史原生证据原样保留。两个A1假原生保存测试仅在测试内显式替换校准门禁；不写生产stamp，不把假peer验证当原生验收。新的真实校准未执行；旧数字仅保留其原日期和范围。

本批离线验收：几何契约/定义事务/语法检查/投影/G03假peer/创建等10模块207项通过；文档/登记/迁移/查询5模块49项通过。索引138项功能、72项工具、28条人工关系，validate无错误/警告；git diff --check通过。两组测试不证明真实CST执行，未启动CST，未刷新原生stamp。

最终几何模块复跑50项通过（包含后补的ApplicationService/Runner共用入口测试，与上述组合重叠，不累加）；专用artifacts/geo1-contract-tests临时目录及本轮只读查询/文本提取缓存在测试结束后清理，轻量依据保留于知识记录。

## 9. 顺序历史中的几何结构维护

2026-11-04设计分析。以下是GEO-1之后的维护方案，**未新增运行接口、feature编辑操作或原生验收**。现有实现依据为geometry_contract.apply_changes/project_geometry与definition_editing.changed_spec；GEO-1.1已补齐既有feature修改/移除及有界身份保留，当前接口见第12节，原生执行仍未校准。

### 9.1 唯一意图、顺序执行与派生依赖

文档维护可编辑的有序features；CST历史是从它生成的执行产物；实体结构、对象存活表、依赖关系及原生名称映射均由features推导。请求审计/幂等记录和文档revision另有既有事务职责，不把features当作只能永远追加的审计日志，也不独立维护另一份可随意修改的几何树。

例如：

```text
F1 创建腔体 body
F2 创建切割体 tool
F3 body - tool
F4 平移 body

body@F1 ──减去 tool@F2──> body@F3 ──平移──> body@F4
```

`body@F1`等是解释执行阶段的记法，不是已开放的公共ID。对外仍用body；在每个步骤内，引用解析为该步骤之前的最新存活状态。F3后tool被消费，不能继续使用；F4仍输出逻辑body，但几何已不同。依赖边用于检查和诊断，不用于擅自重排原命令；布尔与变换顺序具有意义。

### 9.2 参数修改、步骤修改与实体删除

|用户意图|维护策略|当前边界|
|---|---|---|
|改变半径、长度等参数|修改参数表，保留表达式和feature身份；重新投影所有历史及最终集合|GEO-1已支持离线校验；原生重放待校准|
|修改平移距离、创建尺寸表达式或布尔操作数|在新document revision中修改指定feature，核对下游引用，重新构造候选|GEO-1.1已接类型化update_feature，原生构造待GEO-2|
|删除最终实体|追加delete_object，保留其创建、修改和消费历史|GEO-1已有声明契约；不是删除历史节点|
|取消孔或撤销一次布尔运算|修改/移除相关feature，检查后续特征及集合；不以反向布尔补偿|GEO-1.1已接remove_feature，原生构造待GEO-2|
|调整历史顺序|显式表达顺序变化并检查依赖和语义；第一版暂不开放任意重排|不能依赖自动拓扑排序改变建模意图|

GEO-1.1修改feature时保留feature_id，独立计算content_sha256及文档revision；创建时的父CAS/请求/步骤只决定首次feature_id，不因修改尺寸再分配步骤身份。update_feature使用完整类型化replacement，拒绝改变op或创建实体的object_id；不会通过原位修改CST历史实现此声明编辑。

移除一个操作不释放对象ID。geometry.identities保存object_id→首次创建feature_id，包含已移除创建步骤；最多512项、大小写无歧义、不可重分配。新revision的身份登记必须包含直接父revision的全部登记；读取时只检查有界直接父记录，不递归遍历祖先。登记不保存另一份几何状态，存活/消费/依赖仍由当前features推导。

第一版不自动级联删除或修复下游。编辑F3造成F4输入失效时，整批拒绝并列出受影响feature/对象/集合，由调用方显式一并调整。删除和替换步骤均发生于新revision；旧revision及已确认结果不改写。

### 9.3 当前参数表不是历史时刻快照

所有几何步骤按当前revision的参数表求值。参数表独立保存、历史引用表达式；参数修改不是在几何序列中插入一次临时赋值。

```text
R=10时创建A，半径引用R
R=20时创建B，半径也引用R
```

不能据此要求重建后的A仍为10：在本声明模型中，当前R=20会作用于所有引用R的步骤。需要不同尺寸时使用R_A、R_B等明确的参数及表达式，不依赖建模过程中的临时StoreParameter状态。该规则是本项目契约选择，不概括任意用户宏的CST执行行为，也不要求把表达式改成固定值。

### 9.4 选择集与拓扑失效

实体集合引用逻辑object_id，含义是当前revision最终存活的实体。body平移后可继续属于集合；body作为布尔目标可保持逻辑身份，但不能据此沿用旧面/边证据。若实体被删除或作为工具消费，相关集合必须在同批显式更新，否则拒绝发布草稿。

同一逻辑body不意味着同一BRep拓扑。面/边选择需独立绑定revision与几何证据、明确解析和失效规则，不能根据相同实体名、旧face_id或首个面自动重绑定。当前只支持实体集合，不新增拓扑选择或原生Group持久化承诺。

### 9.5 重放、历史标题与发布边界

第一版先保证完整重放正确：

```text
编辑新revision
→ 整批检查参数、步骤顺序、消费及依赖
→ 从空基准构造受控候选
→ 按features顺序执行历史
→ 保存、重开及必要观测核验
→ 发布新revision
```

每个feature保留唯一历史caption；在新候选中按当前revision完整生成历史，不在旧工程上用同caption再次AddToHistory冒充“更新指定步骤”。官方AddToHistory定义为立即执行，且相邻同标题有重复块处理；Rebuild会重放并删除结果。来源见[官方Application帮助](../knowledge-base/vendor/cst-2022-vba-help/VBA_3D/common_vbaapp/common_vbaappapplication_object.htm)及本页第2节。失败不推断自动回滚；保留失败候选和步骤诊断，不发布半成品、不在未知状态上重复追加，沿用既有退出与恢复责任。

诊断目标是定位revision、feature_id/顺序、输入对象、参数表达式、失败阶段和下游受影响项。依赖有效仅证明声明可执行顺序成立，不证明CST几何运算成功；合法阶段的原生观察和退出证明仍独立需要。

完整构造策略适用于几何定义变化，不要求HOM每次求解都从空工程重建。HOM仅修改频率等求解参数时继续使用现有Worker复用路径；几何定义/几何依赖参数变化与求解设置变化须显式区分，不能未经核验把前者当成网格可复用的后者。

### 9.6 落实顺序与当前状态

1. GEO-1.1已实现声明feature修改、移除及引用规则，沿用现有apply_model_changes、CAS和revision，不另建历史编辑服务。
2. GEO-1.1已接依赖预检、步骤输入/输出状态与消费者诊断、移除创建步骤后的身份保留。
3. H1–H7离线覆盖：参数改动影响多个实体；取消布尔后保留目标/恢复工具的下游引用；删除与移除feature的区别；悬空集合；失效操作数；旧revision不变；重复请求及丢响应不重复应用。
4. 再纳入GEO-2受控副本：唯一标题、参数重放、部分步骤失败、保存重开与标准退出。C1–C7原生门禁仍未完成，不以本章设计代替验收。

## 10. COMSOL MCP如何维护几何历史：源码对照

核对日期2026-11-04；沿用既有参照的固定提交，不声称是最新HEAD或COMSOL官方MCP：Ching-Chiang/comsol-mcp的`ccca65aa8277d1205c5de5fb6221e460aca5997a`，wjc9011/COMSOL_Multiphysics_MCP的`53c9ca4cd9f16187b1e5e4fa97cff6dca716ed9d`。本次只读源码及COMSOL6.3官方文档，没有运行COMSOL或CST。

### 10.1 原生序列负责几何，MCP直接编辑节点

两个项目所查建模路径均调用MPh暴露的Java对象。Ching的寻址为model→component→geometry→feature(tag)，create/update/delete分别调用原生创建、feature.set及feature容器remove；可选run_geometry单独触发geom.run。其MCP层没有在这些路径中另外计算布尔结果、维护自研BRep或自行模拟内核重建。来源：[geometry工具L49–172](https://github.com/Ching-Chiang/comsol-mcp/blob/ccca65aa8277d1205c5de5fb6221e460aca5997a/comsol_mcp/_tools_geometry.py#L49-L172)。这只证明所查路径，不证明整个仓库没有其它状态层。

例如修改cyl1半径，是修改现有特征属性，而不是追加“删除cyl1→重新创建cyl1”的补偿命令。delete_feature删除的是建模步骤，不能直接对应本项目当前的delete_object（最终实体删除）。run_feature虽然名字包含feature，geometry分支实际调用整个geom(tag).run()，不能据名字宣称它支持指定几何步骤的部分构建。

COMSOL官方文档区分feature标签与构建产生的对象，提供步骤属性编辑/启停/移动/删除、构建至指定步骤或步骤之前、状态/错误信息及输出对象查询。尤其create在current feature之后插入，不保证总是追加末尾；全量run还会更新最终几何和选择。来源：[COMSOL6.3 model.geom()](https://doc.comsol.com/6.3/doc/com.comsol.help.comsol/comsol_api_general.47.35.html)。**这些是原生能力，不等于所查MCP已经全部开放。** Ching所查工具没有move或runPre接口；当前CST公共底层也未校准对应的原生步骤编辑/状态接口，不能据此推断CST一定没有这些能力。

因此应把以下身份分开：

|身份|用途|本项目处理|
|---|---|---|
|feature_id / COMSOL feature tag|定位建模步骤|步骤修改保留逻辑身份；另有内容与文档revision|
|object_id|本项目的实体消费与操作引用|依据顺序解析当前实体状态；不是直接套用COMSOL tag|
|native object name / 输出对象|内核实际几何对象|规划名称与原生观测分开，不能假定feature tag永远就是输出名|
|selection_id / named selection tag|按名称引用一组目标|实体集合与面/边规则分别维护，不能用固定数字证明长期拓扑身份|

### 10.2 布尔操作通过输入选择表达依赖

wjc的Union新建独立特征，再对selection("input").set指定输入；Difference使用input和input2。输入设置异常时删除刚建的布尔特征，避免空输入节点遗留到后续构建。这是局部失败清理，不是整次模型变更的事务回滚。来源：[geometry.py L460–570](https://github.com/wjc9011/COMSOL_Multiphysics_MCP/blob/53c9ca4cd9f16187b1e5e4fa97cff6dca716ed9d/src/tools/geometry.py#L460-L570)。

其依赖通过原生特征的选择属性表达，不能把工具参数里示例的blk1/cyl1泛化为所有特征都有同名输出。对CST而言，应借鉴“操作与显式输入引用”，而非照搬COMSOL布尔输出身份；CST已核对的Solid运算保留第一个实体、消费第二个，仍以本项目规则为准。

Ching的通用properties_json助手只逐项feature.set，未在所查助手中实现任意selection(property).set分发。因此通用属性袋存在不证明所有布尔输入选择均可正确配置。来源：[_model_ops.py L373–446](https://github.com/Ching-Chiang/comsol-mcp/blob/ccca65aa8277d1205c5de5fb6221e460aca5997a/comsol_mcp/_model_ops.py#L373-L446)。

### 10.3 命名选择保留规则，实体编号是求值结果

wjc创建组件级Box命名选择，保存坐标表达式、实体维度、几何tag和condition，再尝试selection.entities()取得当前实体编号；求值失败时返回warning而不是证明已匹配。物理边界条件可用selection().named(selection_name)绑定此名称。来源：[Box选择L715起](https://github.com/wjc9011/COMSOL_Multiphysics_MCP/blob/53c9ca4cd9f16187b1e5e4fa97cff6dca716ed9d/src/tools/geometry.py#L715)、[物理绑定L128–166](https://github.com/wjc9011/COMSOL_Multiphysics_MCP/blob/53c9ca4cd9f16187b1e5e4fa97cff6dca716ed9d/src/tools/physics.py#L128-L166)。

可借鉴的是“持久化选择意图、构建后获取成员、下游按名称绑定”。不能推断命名选择永远匹配同一物理面：几何变化后规则可能选空或选多。未来CST面/边选择若采用空间规则，需独立校准坐标/容差/匹配数及失败行为；不能把本地规则的容差参数伪装为CST原生Pick参数。GEO-1仍只支持逻辑实体集合。

### 10.4 状态和快照不等于原子修改

Ching的_run_tool取得runtime lock后调用callback，异常时包装错误，finally释放锁；它没有在该包装中恢复已成功写入的属性。_apply_feature_properties逐项set，因此后一个属性失败可能留下前面的修改。create_feature遇到已有tag还会跳过创建；所查分支不核对既有节点类型是否等于请求feature_type。wjc的通用geometry_add_feature则可能带failed_properties仍返回success=True。上述行为不能用作CST定义发布成功判据。来源：[_state.py L454–473](https://github.com/Ching-Chiang/comsol-mcp/blob/ccca65aa8277d1205c5de5fb6221e460aca5997a/comsol_mcp/_state.py#L454-L473)、前述geometry与_model_ops源码。

Ching另有快照/主模型工作流：save_main_model_snapshot保存副本并核对前后模型身份；commit_current_main_model先存快照，再保存主模型和写工作流状态。它们不表示每次update_feature都自动生成不可变revision，也不是属性失败的自动回滚。来源：[_tools_snapshot.py L95–172](https://github.com/Ching-Chiang/comsol-mcp/blob/ccca65aa8277d1205c5de5fb6221e460aca5997a/comsol_mcp/_tools_snapshot.py#L95-L172)。本次未展开审计其全部保存依赖，不宣称保存链已实测或具备分布式事务保证。

### 10.5 对现有方案的修正与收敛

1. 保留第9节“编辑features再生成历史”，补齐update/remove而不是无限追加补偿操作；对象、步骤和输出名称分层。
2. 依赖关系作为现有features的派生检查，先提供受影响步骤及选择集诊断，不自建CAD内核或另一套依赖执行框架。
3. 明确构建时的顺序/插入位置；不能把原生current位置、UI选中节点或默认第一个geometry当作隐式顺序权威。当前CST仍按已拥有候选和显式features顺序执行。
4. 编辑、构建、原生已保存及仿真ready分别表达；声明有效与宿主实际built分开。COMSOL的原生状态名不能当成已存在的CST读回字段。
5. 未来命名面/边选择持久化规则与预期匹配约束，构建后复核成员；不承诺编号永久稳定。
6. 保留本项目CAS、候选副本、发布和恢复链。社区实现的轻量直接编辑有参考价值，但锁、异常包装或快照按钮不能替代本项目已有的失败隔离责任。

本章的COMSOL参照仍是源码研究；其后的GEO-1.1已完成声明feature编辑/移除和离线诊断。原生阶段观察、面/边规则及GEO-2/3/4仍未完成，不由外部源码研究代替验收。

## 11. 调整后的执行计划与离线验收清单

2026-11-04根据第9/10节分析收敛；本节是GEO-1.1时点的推进计划快照，替代此前把历史编辑笼统放入“GEO-2前置”的安排。**GEO-1.1已按此计划离线实现，具体接口见第12节；GEO-2离线发射/检查及共用执行宏已接，实际保存提取与原生验收未完成，未启动CST。** 原有GEO-1历史验收保留原批次范围。

### 11.1 GEO-1.1先完成可维护的声明历史

- 在现有apply_model_changes内设计并落实feature更新/移除，不新增历史服务。update_feature/remove_feature已进入公共Schema；当前MCP签名尚未接geometry_profile，桌面工具扩展仍待GEO-3。
- 更新步骤保持feature_id，保留独立内容摘要/文档revision语义。采用按feature类型限定的字段修改，拒绝任意properties/VBA袋；首版不允许通过更新偷换op或创建实体的object_id，不开放任意重排。
- remove_feature与delete_object分开：前者编辑建模定义，后者是追加实体删除步骤。移除创建步骤仍需保留文档血缘中的ID占用；保留记录只描述身份，不成为第二份可变几何真值。当前布局为geometry.identities，最多512项且受512 KiB Spec＋投影预算约束；只检查直接父记录，不作无界祖先遍历。
- 从当前features顺序派生依赖和阶段对象状态；保留输入/输出映射、消费者和受影响步骤/选择集诊断。新增原生名称只是规划映射；实际输出必须在GEO-2观测，不能默认feature_id等于native object name。
- 参数更新按当前revision参数表重算全部引用，不插入历史时刻赋值。无效尺寸、失效操作数及悬空集合在整批预检拒绝；显式同批修复才可接受。
- 构建状态分层：声明已校验、原生构建/观测、已保存、仿真ready分别表达，失败标明阶段和事实来源。没有原生证据时保持unknown/unverified，不复制COMSOL的built状态名作为CST观测。

|离线用例|验收要求（GEO-1.1已覆盖；具体记录见第12节）|
|---|---|
|H1 更新创建/平移参数表达式|步骤身份保持，只有新revision改变；表达式不扁平化，旧revision和结果不改写|
|H2 更新布尔输入|按原顺序重算依赖/消费；自引用、前向、缺失及跨材料等非法引用拒绝；无隐式重排|
|H3 取消布尔与删除实体|取消操作后按剩余features重新推导对象；与追加delete_object的后置状态不同；下游须显式有效|
|H4 移除创建步骤|受影响操作/集合清单可定位，未修复整批拒绝；已用ID不因移除而可重用，身份预算有界|
|H5 参数共享与集合|同一参数变化作用于多个步骤；R_A/R_B独立表达；集合成员重新核对，无自动丢成员或拓扑重绑|
|H6 CAS/响应丢失/重复请求|沿用现有事务对账，提交前后缺口可区分；不重复应用更新/移除，不恢复成旧current指针|
|H7 预算、未知字段及副作用|限制步骤/身份保留/表达式/文档字节；错误在intent前拒绝，原生builder零派发；几何保存和ready不被误授权|

### 11.2 GEO-2再完成原生构造与事实核验

离线子阶段已在现有发射器、profile允许表、词法/算术基础和检查器接入，见第13节；共用宏的逐块MacroCheckThis/AddToHistory、参数表与标准收尾适配见第14节，不新建字符串执行入口。剩余先落实第15节的设置归属、原子分块和显式依赖，再核实实际Model.mod块提取/原生观察。随后才做授权的无求解串行副本C1–C7：构建输入输出身份、合法阶段查询、保存重开/参数重建、部分失败和正常退出。COMSOL原生步骤编辑接口只是参照；CST尚未核实等价能力时，先从空基准重建候选，避免在旧模型里猜测原位编辑API。

geometry_saved=true必须来自几何保存核验；它仍不授权仿真。旧A1校准和新GEO profile分别绑定其源码/证据；源码变化不能通过刷新记录hash消除待校准状态。任何未确认原生退出继续沿用既有恢复阻断责任。

### 11.3 GEO-3/4接入与后续选择规则

GEO-3才扩展MCP工具签名及适配器，验证同一请求从公共入口到事务/原生/发布的整链；不另建GUI/CLI业务逻辑。公开保存必须区分几何目标和仿真目标，遇到已有ID/类型不一致要明确冲突，不采用社区工具的静默复用。GEO-4按具体求解器/材料/网格/后处理兼容组合验收，之后才可扩大仿真ready范围。

面/边命名选择单列后续：保存可解释规则与预期匹配约束，构建后核验零/一/多匹配；在实际解析通道、单位和容差未校准前不开放。保持实体集合首版可推进，不将完整拓扑跟踪、远程任务或自研CAD依赖引擎并入本轮。

## 12. GEO-1.1实现与使用边界

日期2026-11-04，基线f755505上的工作区变更。实现仍在[geometry_contract](../csttool/geometry_contract.py)、[定义事务](../csttool/definition_editing.py)及[唯一Schema](../data/first_stage_contract.schema.json)，测试见[H1–H7](../test/geometry_history_edit_test.py)。没有新增Worker/会话/队列/CAD内核，没有执行CST。

### 12.1 公共变更契约

继续在apply_model_changes中显式指定geometry_profile=geometry-v1，并传document_id/expected_document_revision。新增changes元素：

```json
{
  "op": "update_feature",
  "feature_id": "f_0123456789abcdef0123456789abcdef",
  "replacement": {
    "op": "translate_solid",
    "target_id": "body",
    "translation_mm": ["R", "0", "H"]
  }
}
```

```json
{"op":"remove_feature","feature_id":"f_0123456789abcdef0123456789abcdef"}
```

replacement是完整GeometryFeature，不是patch/任意属性袋；所有必填字段须给出，仍只支持既有六类几何步骤。API新增、存储校验和replacement引用同一GeometryFeature定义，不维护两份几何允许表。目标feature必须存在，update保持其位置和feature_id；op及创建实体的object_id不可改变。两次移除同一feature、引用已移除feature或跨profile请求均拒绝，不静默忽略；操作幂等依赖既有request/operation事务，不依赖“删除不存在就算成功”。

整个changes在Spec副本上执行，然后重新验证最终有序features和集合；允许同批显式修复下游。remove_feature不把原操作变成补偿命令，也不调用CST的delete_feature。CST原生保存仍在intent前拒绝，MCP签名/GUI适配待GEO-3。

### 12.2 身份、内容和持久性

geometry.identities是必需的有界身份登记：key为逻辑实体ID，value为首次创建feature_id；移除/删除/消费后不释放ID，大小写变体也不能复用。当前features中的创建步骤必须拥有相应登记，同一creator不能分配给两个ID。每个新文档读取时验证登记相对于直接父记录单调保留，拒绝删除/重分配；直接父记录通过既有严格读取器受1 MiB上限约束，不追溯无限祖先。

feature的content_sha256来自当前类型化步骤内容，不包含feature_id；修改步骤会改变内容摘要，参数表重算而表达式不变时该摘要保持。文档revision仍覆盖整个记录，当前父/子revision的文件与已确认结果不被覆盖。几何输入求值和native_name都是声明/规划，native_build_state=unverified、geometry_saved=false、ready=false，不能称原生已构建。

**开发契约变更**：geometry.identities和扩展后的声明投影为当前必需数据。此前GEO-1开发草稿未提供该字段时明确拒绝，不静默补写或改写其hash，也未实现旧开发草稿迁移；需按原声明重建新开发文档。原始旧JSON不删除。GEO原生保存从未开放，本批不迁移或修改原.cst/已确认仿真结果。旧A1原生stamp仍失效，未改写校准证据。

### 12.3 依赖投影与错误诊断

每个投影步骤包含step_index（从0开始）、inputs（object_id、来源feature和state_before）、depends_on、outputs（本步涉及对象的状态）、parameter_names（含传递依赖）、consumers和selection_consumers。对象生存状态和这些依赖在同一顺序扫描中推导，不持久化第二份可变依赖图，不自动重排或修复。

依赖错误通过ServiceError(INVALID_ARGUMENT)返回，内部调用可读diagnostics，既有Runner/HTTP的错误字符串携带geometry_diagnostics JSON摘要；这不是新增已接入的MCP结构化错误字段。诊断包含失败阶段、feature_id/step_index、输入字段、对象、原因步骤以及受影响feature/选择集。缺失/前向/已消费/已删除引用可区分；后续受污染步骤只用于诊断，不发布半成品。

依赖issues最多保留64条，另有issue_count/issues_truncated；字符串摘要最多4条issues、8个受影响feature和8个选择集，并显式truncated。受影响步骤和选择集清单仍来自完整有界扫描，不因只保留前64个问题而丢失后续影响。数值/尺寸失败定位对应feature及字段并推导下游；参数表自身解析失败定位parameters字段，impact_complete=false，不冒称已经完成几何影响分析。结构错误、未知feature及资源预算错误使用既有INVALID_ARGUMENT，不承诺所有错误都有完整依赖图。

整批依赖/尺寸/预算错误在intent前拒绝；取消可能发生在intent后、commit前，沿用既有“未提交不得自动重放”。commit/current/result写入缺口通过原有对账补写，不重复应用；有更新revision时恢复不得回退current。保留已有项目锁和标准退出责任，没有增加原生资源清理通道。

### 12.4 离线验收记录

2026-11-04最终功能组合242项通过，其中H1–H7新模块34项；文档/登记/迁移/查询组合49项通过，两组为不同测试集合，不与GEO-1历史数字累加。注册校验138项功能、72项工具、28条关系，无错误/警告；git diff --check通过。没有启动CST或刷新原生校准。

首次组合出现既有project_creation_test的HTTP启动等待10秒超时（等待runner.json），当轮240项通过、1项失败；单独复查0.85秒通过，最终完整重跑通过。原因尚未确定，未修改测试时限或据此归因CST；如重复出现再单独诊断Runner启动。本轮专用artifacts/geo11-* pytest夹具/只读预检缓存已在测试结束后清理，保留此轻量记录；没有生成真实CST模型或场数据。

## 13. GEO-2离线历史发射、投影、检查与源映射

2026-11-04；仅完成GEO-2的离线子阶段，不代表C1–C7或原生保存通过。新增[几何降低器](../csttool/geometry_codegen.py)复用[类型化发射器](../csttool/winwrap_emitter.py)、[共享投影/命令表](../csttool/settings_projection.py)、[独立检查/源映射](../csttool/winwrap_checks.py)，没有新增执行服务、Native进程、文件格式解析器或MCP工具。接口与测试见[geometry_codegen_test](../test/geometry_codegen_test.py)。

### 13.1 离线接口和产物

|入口|输入/输出|边界|
|---|---|---|
|geometry_codegen.render_geometry_history(spec)|返回有序blocks和Projection；block={caption,history}|一个setup块，之后按当前features顺序一块一步；移除步骤不发射，更新步骤保持caption身份|
|geometry_codegen.validate_geometry_history(spec,blocks)|独立文本检查、实际文本投影、声明及符号引用对比|不通过重新发射再比较整段文本冒充独立验证；数值相同但R被替换成常数也拒绝|
|settings_projection.project_geometry_history(blocks,parameters,scope,available_scopes)|实际文本的单位、WCS、组件、步骤、输入和消费/删除状态、表达式及来源|仅root，复用原词法/算术；不是BRep/体积观测，不是保存后的Model.mod块提取器|
|winwrap_checks.check_history(source,profile=...)|复用独立词法、With/语句调用形状、精确命令arity检查|默认仍A1；GEO须显式cst-geo-history-v1，不是完整WinWrap编译器|
|winwrap_checks.geometry_definition_map(spec,blocks,macro=None)|块/行→feature及输入字段、代码hash与引号赋值范围|无macro时outer为片段；传入共用宏时outer为完整宏绝对行，assignment_outer保留原片段|
|winwrap_checks.map_native_error(raw,mapping,block_index=...)|GEO错误行减去3行检查包装后定位body|GEO必须显式给block_index且Source语句匹配，不能默认匹配第一个块；不足时保留raw、origin=null|

这些是内部Python离线函数，尚未新增对外Schema字段或桌面工具签名。可调用示意：

```python
from csttool.geometry_codegen import render_geometry_history
from csttool.winwrap_checks import geometry_definition_map
blocks, projection = render_geometry_history(spec)
mapping = geometry_definition_map(spec, blocks)
assert projection.status == "resolved"
assert projection.publish_ready is False
```

### 13.2 原语与共享profile

history_call_contract/command_arities是同一查询入口，A1的COMMAND_ARITIES保持原范围；显式GEOMETRY_COMMAND_ARITIES/profile仅含本阶段所需语句。HistoryCall、With、render_history均复用原发射器，传profile选择允许表；没有按任意对象放行。GEO参数名额外保守保留Brick/Sphere/Solid/Transform等对象名，A1默认命名策略不因此扩大；这不是CST完整保留字表。

setup发射Units.Geometry mm、WCS.ActivateWCS global及确定性组件名；每个feature caption含稳定feature_id，组件/实体规划名称与声明投影共享命名函数。基本体Reset→必要属性→Create；XYZ Cylinder只写对应轴向range及两个横向center，支持合法空心；Sphere使用官方CenterRadius和三参数Center，固定完整球axis/top/bottom/segments。平移显式关闭picked/copies/unite/touch、repetitions=1，执行Shape/Translate。布尔按Solid.Add/Subtract/Intersect消费第二操作数，删除用Solid.Delete。不会发射原生Group、Pick、Solver、Rebuild、Save或应用退出命令。

参数引用复用现有有界算术AST发射为RestoreDoubleParameter，首参数保留0+安全形式；StoreParameters及参数描述属于§14共用执行宏，不由几何body反复写参数。选择集/身份保留仍是文档元数据，不将其伪装成原生选择或已保存结果。

### 13.3 独立投影和符号保持

投影器从实际语句读取参数、Reset/Create生命周期、属性完整性/重复、正尺寸、名字/组件/材料、消费及删除顺序。声明期待来自project_geometry，独立于生成文本；对比单位、WCS、组件、步骤/操作数、解析值和最终对象状态。符号比较只消去发射器的0+保护，将RestoreDoubleParameter识别为参数引用；不做一般代数化简，也不把数值相等当作表达式保留。

生成表是语句arity入口，属性枚举和顺序仍由投影检查；独立文本检查负责原始Zrange的bare首参数括号等调用形状。两层都不等于原生编译器。只有语义Projection.status=resolved不能跳过check_history，更不能把publish_ready改成True。未知/部分失败时投影清空全部fields，保留失败块与行来源，不返回早先已解析值当成功。

本profile只覆盖本框架生成的body；数值setter使用未加引号的有界算术，不支持任意CST合法语法、变量/别名、动态代码、函数库、单位表达式、复制变换、跨材料布尔等。最多513块（setup＋512步骤）、32组件、128参数/同时存活实体、20000语句和2 MiB历史文本；复用800字符保守物理行预算。已有Schema/声明预算先行；声明合法但无法在保守行长内发射时带feature位置拒绝，不修改数学表达式来凑行长。

### 13.4 源映射和下一步边界

源图绑定spec_sha256、program_sha256以及各块body/assign_string片段hash；history含block_index、caption、feature_id、body行、输入字段及实现函数。布尔操作同时列出target/tool/operation，Cylinder横向center按轴映射到对应索引。引号转义片段复用assign_string；片段与完整宏绝对行号通过outer_kind区分，§14另记录身份注入后final_outer。错误来源缺少块身份、行不明或语句不符时不猜测映射；真实ErrObject格式、包装行偏移和回执传递仍待CST副本校准。

§14已补齐GEO可执行外层宏、参数表持久化语句、逐块AddToHistory和标准收尾接入；尚未新增保存工程的GEO历史提取器。A1生产build_candidate和G03未扩展为GEO，preflight_edit仍在GEO save写intent前拒绝。保存历史与原生几何观测仍需核实，现行推进顺序见§15；不能直接宣称可原生保存。

源码版本门禁的SOURCES增加geometry_contract/geometry_codegen；校准记录的profile仍只代表A1。包含GEO文件hash不意味着A1证据校准了GEO。旧stamp保持原样且因源码变化失效；离线测试、包内编译/GUI烟雾均不刷新原生许可。源码包测试核对包内外相同门禁判定并原样携带stamp，允许合法的stale拒绝，不要求用伪造hash让gate永远通过。

### 13.5 离线验收与产物清理

2026-11-04最终组合338项通过：功能287项（含39项GEO新测试）、文档/登记49项、源码包边界2项；子集不重复累加。覆盖XYZ空心圆柱/球/砖、布尔消费/删除、编辑后顺序/标题、同值常数丢引用、错误flag/生命周期/字段/命令、Zrange调用反例、作用域/预算、块感知错误映射和GEO保存零派发。A1回归及两类WinWrap探针离线约束同批通过；没有启动CST，没有原生编译/构建/保存证明。

源码包ZIP/哈希、编译/无Qt Runner导入、无CST的offscreen GUI烟雾及包内外校准判定一致检查通过。首次包检查在登记复审同步前提示4项changed-since-capture；已逐项人工复审并同步映射，最终138项功能/72项工具/29条关系validate无错误/警告，不涉及更新原生stamp。原凭据仍为stale拒绝。测试临时包不作为发布交付；本轮geo2-*夹具、查询缓存和临时包在测试结束后清理，轻量摘要及包hash见知识记录，原临时产物需重建。

## 14. GEO-2共用执行宏与回执

2026-11-04；本节为§13之后的实现批次，**仅离线验证，没有启动CST**。不是GEO原生保存/仿真就绪验收，原生校准stamp保持原样。

### 14.1 共用入口及持久化边界

|内部入口|职责|不得据此推断|
|---|---|---|
|definition_editing.render_edit_macro(directory,spec,nonce)|同一模板：A1单块，GEO为setup＋feature有序块|生成文本不代表原生检查或执行成功|
|prepare_candidate_artifacts(directory,spec,nonce)|新目录写edit.bas、spec.json、history-program.json、source-map.json、generation.json；A1另保留history.vb|不启动进程、不写build-intent/definition-intent、不提交revision；native_dispatched=false|
|native_definition_builder.inject_definition_ownership(...,profile,mapping)|纯文本身份注入，核对profile/宏hash，生成final_outer绝对行和hash|不连接CST，不确认进程退出|
|read_failure_context(directory,nonce,program)|核对6行阶段/块回执的nonce、索引、caption、最后已应用块|最后已应用块只是诊断事实，不是部分几何可继续执行的检查点|
|validate_candidate_completion(bundle,spec,result)|独立核对退出、完成标记、失败回执；共用B1读取参数表，精确对比表达式及说明|不提取GEO保存历史、不观察BRep、不发布saved/ready|

本轮移除内部generated_a1布尔入口，run_new_definition使用generated_profile明确选择A1/GEO检查范围；两处W3调用同批迁移。无profile的旧受控校准探针仍按原路径运行，不扩大为公共任意宏服务。公共GEO save与生产build_candidate均在原生意图前拒绝，不能用准备好的bundle绕过；MCP工具签名未变。新增模板局部名CSTToolsStage/BlockIndex/LastApplied/Caption同样保留，冲突参数拒绝，不自动改名。

generation.json的native_dispatched=false仅记录生成时快照，后续派发状态以build-intent/session-status等执行事实为准，不把生成描述符当作动态会话状态。

参数按Spec原始表达式组装names/expressions数组，仅一次StoreParameters；空参数时跳过。随后逐项SetParameterDescription，Unicode BMP说明经ChrW编码，不依赖宿主代码页。**参数表不写入结构历史**；几何体及其RestoreDoubleParameter引用仍逐块进入历史，保证重建重新取参。这里只实现写入及保存后核对流程；真实CST参数持久化仍需副本验证，不把假容器读回称为原生证明。

### 14.2 固定顺序与失败语义

初始化阶段/块诊断变量 → 既有身份绑定/quiet握手 → 参数表 → 参数说明 → 对每块依次组装history、MacroCheckThis包装模块、检查ErrObject、AddToHistory及返回检查 → Rebuild → SaveAs → completed.txt(nonce) → 返回持有对象包装器。

每块重新检查，检查未通过不调用该块AddToHistory；Add失败不运行后续块，不重建/保存成功标记。外层独立检查器核对逐块check/guard/apply次序、GEO caption唯一性、参数写入早于历史及最后一块后Rebuild/SaveAs。它只覆盖固定模板，不是完整WinWrap编译器；固定三行包装偏移仍待新GEO原生校准。

失败先捕获Err.Number/Description/Source，再进入容错文件清理，写failed.txt及failure-context.tsv：版本1、nonce、阶段、当前块索引、最后已应用块索引、caption，各占一行；前置阶段索引为-1。阶段覆盖ownership、parameters、parameter-descriptions、history-check、history-apply、rebuild、save、batch-return。identity初始化位于绑定调用前，绑定失败不会误报第0块。中途失败是整个候选失败；本轮新建副本可由原包装器保存为诊断，绝不覆盖原工程，也不从部分历史继续或发布部分结果。

syntax错误另保留原三行history-syntax-error.txt；Python仅在阶段回执nonce/块/标题一致且为history-check时，使用明确block_index定位GEO body及feature。缺回执、未知格式、语句不符或身份不一致保留raw，origin=null；不猜块或列。普通失败输出candidate-diagnostic.json，语法失败输出native-diagnostic.json，并保留关闭是否确认。无界大文件不会全量读入诊断；上下文/完成标记有大小上限，错误文本有截断预算。

### 14.3 收尾责任及采用条件

宏不调用Quit/Active3D/OpenFile，不引入第二条清理链。既有run_new_definition持有本轮project，finally中正常关闭project，核验绑定后正常关闭studio并释放COM；Python继续核验所属进程退出，释放窗口观察器及私有桌面。归属未知不把全局对象当成本轮对象，不强杀代替标准退出。此处复用的是既有实现责任，未以静态断言证明所有真实异常均可关闭。

完成采用必须同时满足：标准exit_confirmed=true、exit_code为整数0、completed nonce一致、无failed/阶段失败回执、B1完整性/作用域通过、保存参数无缺失/新增/重名且表达式与说明完全一致。已写完成但随后失败、退出未确认、陈旧nonce、部分历史成功，都不能采用。新回执不存在时允许既有成功A1候选继续按独立退出/完成/参数事实核对；失败回执缺失不会据此判成功。生产A1之后仍需原保存设置投影/G03等门禁；GEO仍整体禁止发布。

### 14.4 离线验收与下一步

新增[固定模板假peer测试](../test/geometry_execution_macro_test.py)，从实际宏赋值解码payload，再对宿主调用注入参数、说明、各块检查/应用、重建及保存故障；覆盖XYZ、空/128参数、中文引号说明、表达式原样保存、块身份丢失、陈旧/矛盾回执、保存参数改变、退出未确认、完成后失败、源图身份注入偏移及公共GEO零派发。假peer不是WinWrap解释器，不验证CST API语义或真实COM退出。A1回归及W3旧注入点同步迁移，避免ReportStage模板变化使部分失败注入静默失效。

本批最终组合**473项通过**：功能410项（含新增46项共用宏用例）、文档/登记61项、源码包边界2项；子集不重复累加。源码包内外旧校准门禁均维持stale拒绝，包内编译/无Qt导入/offscreen GUI烟雾通过。首次包检查因校准工具注入点刚修改、登记hash尚未同步而失败（changed-since-capture）；完成该调用/阶段关系人工复审和登记后，最终整组重跑通过，不改原生stamp。此前单轮假peer断言曾误将VB的CRLF与源文本LF直接比较、误写wrapper对象名及使用尾空格说明；均修正为真实契约后通过，未据此改变CST语义。

最终注册138项功能、72项工具、30条人工关系，validate无错误/警告；索引校验不代表逐句语义或原生行为认证。本轮geo2-macro-*临时宏/假容器/pytest目录与源码包在结束后清理，保留知识库中的轻量摘要/包hash，原临时产物需重新生成；没有真实场文件或CST会话。此实现批次保留实际Model.mod多块提取、合法原生几何观测与独立GEO校准门禁等未完成项；后续§15在此前增加分块规则前置，现行顺序以该节和TODO为准。C1–C7仍需授权，旧A1需针对当前生成器重校准。没有从此处开启求解或MCP GEO接口。

## 15. 设置唯一归属、原子分块与显式依赖

2026-11-04设计决策。本节确定后续发射/验证器的约束，**不代表现有生成器已完成拆块或设置归属检查**；本批只同步设计与TODO，不修改运行代码、Schema或原生校准凭据，不启动CST。第14节473项为此前实现批次证据，不覆盖本节待实现规则。

### 15.1 当前声明、执行历史与审计分离

当前revision中的参数、设置及有序features是唯一可编辑意图。CST历史是由该revision生成的执行产物；审计记录及旧revision另行保留修改过程。修改某个设置时更新其声明值和所属块内容，不以追加覆盖块表示最新配置；审计仍追加，不能因此删除旧revision或改写已经确认的结果。

几何历史保留有意的操作顺序：创建、布尔、平移和删除是操作步骤，不能一概折叠成最终属性。修改已有创建尺寸、平移距离或布尔输入，更新对应feature并保留身份；确实新增一次操作才追加feature。两次有意平移可以保留为两步，不能因写入同一实体就当成重复设置删除。参数修改保留原表达式及共享引用规则，不替换成求值常数。

### 15.2 设置唯一归属

对每个受管设置，以“明确作用域＋规范化属性”确定唯一写入归属。同一revision中不允许多个独立块竞争该属性，也不采用“最后一次写入获胜”掩盖冲突。块应生成该功能所需的完整有效配置，而不是依赖之前版本残留值的增量patch；完整性范围仅限本功能，不授权对整个求解器或工程无条件Reset。

以下是职责划分目标，不是已新增的Schema字段或已校准的CST setter映射：

|职责|拟定归属|边界|
|---|---|---|
|几何单位、全局坐标上下文|各自唯一环境块|几何块显式声明所需单位/WCS前提；不能靠偶然位于setup后推断|
|组件创建|每个声明组件的创建职责|实体只引用既有组件；不在各实体块重复创建组件|
|背景与边界|分别拥有其受管属性|背景材料/范围与边界/对称相关配置不能由其它块偷偷覆盖|
|求解器身份/方法及关联初始化|一个经核实的求解器上下文职责|先审计Reset的实际影响范围；与其它设置不可安全分离时合为必要的连续段|
|频率配置|拥有本阶段完整频率配置|范围与目标下限的配套约束统一核对；不按单个setter机械切碎|
|模式数、网格密度、自适应等|按实际独立性确定归属|名称相似不代表彼此独立；网格类型等交叉写入须合并归属或统一由单一归属发射|
|参数表/参数说明|共用宏的参数持久化阶段|不塞入每个几何块；几何历史通过RestoreDoubleParameter引用参数|

“归属”针对语义属性，不等于VBA对象名。一个功能可能需要调用多个CST对象；同一对象也可能承载多个独立功能。审计必须覆盖Reset、隐式默认值、单位/坐标上下文及版本行为；如果一个Reset会清除其它块的设置，就不能仅按方法名宣布正交。未知影响范围明确标为未核，阻止相关保存能力放行，不猜测其无副作用。

### 15.3 原子块的判定

原子块是**最小完整、可定位的功能单元**，不是单行命令或一个通用超大脚本：

1. 有稳定身份、明确职责和完整受管输入；设置块身份对应作用域/职责，几何块继续使用feature_id。caption只是可读标题，不能当作原位替换API。
2. 明确读取的参数/实体/环境前提、写入的设置、产生/更新/消费的实体以及对下游的影响。这些信息优先由类型化声明和现有投影推导，不增加一份允许人工随意修改的状态树。
3. 块内保留完成该功能必需的初始化、属性和执行动作，例如基本体的Reset→属性→Create；不能拆成跨块依赖临时builder状态的一串setter。
4. 不混入求解、结果导出、文件保存或应用退出等其它生命周期职责；这些仍由共用执行服务和包装器承担。
5. 失败能够定位块、输入及受影响项；**功能原子性不保证CST事务原子性**。执行到一半仍可能留下修改，整个候选失败，不发布部分成功，也不默认自动回滚。

不把相邻块仅因位置接近而合并，也不以固定行数定义块大小。若某功能只能在共享临时状态的连续命令中完成，把不可分割部分留在同一块；若必须保留多个可诊断步骤组成连续段，则登记该段的入口/出口和不能交错的前提，禁止未声明的临时状态越过段边界。不为此另建工作流引擎或新的运行服务。

### 15.4 显式依赖与顺序

依赖允许跨越不相邻步骤。例如后面的布尔操作可以消费较早创建的实体；不能为了强迫依赖连续而把中间无关功能塞入大块。“依赖尽量局部”是设计目标，不是禁止跨块引用的硬限制。

几何引用沿用现有“该步骤之前最新存活状态”的规则；设置引用以明确作用域和前提表达。诊断至少能够回答：本块依赖哪些参数/实体/设置，谁消费其输出，修改/移除后哪些下游受影响。前向引用、缺失/已消费实体、设置写入归属冲突、未满足的环境前提及失效连续段在执行意图前拒绝。循环参数等既有检查沿用，不另写表达式求值器。

依赖用于检查已声明顺序和影响分析，不自动拓扑排序改变建模意图，不隐式补建对象、不自动丢失选择成员。重复更新同一设置是声明版本变化；重复变换同一实体则可能是有效几何步骤，两者需按类型分别判断。

### 15.5 修改与候选生成流程

```text
定位当前revision中的设置职责或feature_id
→ 修改类型化声明（保留身份），形成新revision
→ 检查参数、唯一设置归属、顺序/消费、依赖及连续段前提
→ 按新声明完整生成有序候选历史和源映射
→ 从空基准构造受控候选，逐块检查/执行
→ 核对实际保存历史、表达式、几何/设置事实及标准退出
→ 按验证目标发布新revision，原revision与已确认结果保留
```

**禁止在旧工程中追加同caption的AddToHistory来冒充替换**，也不通过先追加反向覆盖命令来模拟声明更新。第一版不依赖尚未校准的原位历史编辑/删除API；未来若支持，须独立验证作用域、保存重建、结果失效及失败恢复，不能仅凭标题匹配放行。

规则限于框架管理的声明/生成历史。导入的任意用户历史不能按“最后一次setter获胜”自动压缩、删除或改写；无法证明其前后依赖与副作用时保持只读/明确拒绝该编辑能力。HOM仅改频率等求解参数时仍走既有Worker复用路径，本设计不要求每个扫描窗口从空工程重建；该路径的参数/设置归属迁移需另行审计，不把频率变化误当作几何定义变化。

### 15.6 实现与验收

当前history_program已拆分GEO setup与A1职责，核对规范设置写入、Reset及生命周期依赖；managed_history核对实际保存程序。共用既有发射器/执行模板/源图，没有新增执行服务。

下列O1–O8已在test/history_program_test.py及公共发布测试中验收；连续状态保留在完整块内，当前profile没有开放通用跨块builder段：

|用例|要求|
|---|---|
|O1 设置唯一归属|重复写入同一规范属性、别名和Reset间接覆盖可诊断；未知副作用不能当正交|
|O2 更新不堆叠|同一设置反复修改后，新候选仅含当前配置及唯一归属；旧revision和审计不变|
|O3 最小完整块|setup/A1按已核实职责拆分；必要初始化/属性/Create不被拆散，历史宏仍复用同一执行链|
|O4 显式依赖|非相邻合法依赖通过；前向/已消费/缺失/未满足设置前提拒绝，不自动重排|
|O5 连续段|需要共享状态的段不得插入无关块，状态不得隐式泄漏至其它段|
|O6 修改影响|原身份保留、下游/选择集影响定位，参数表达式及其传递引用不丢失|
|O7 失败与发布|块失败后停止；无部分发布/同名追加替换/隐式回滚；保持独立完成和退出核验|
|O8 跨入口和范围|A1/GEO共用检查/源图，未知用户历史不被压缩；HOM复用路径不因设计文档被擅自改写|

O1–O8离线、C1–C7及GEO-4独立原生矩阵已通过；具体范围及剩余边界见[GEO-2–4生产实现与验收](geometry-production-implementation.md)。A1更新许可本批未获自动审批，旧记录保留失效状态。
