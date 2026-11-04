# 首阶段类型化定义事务

更新：2026-11-04。实现位于同一个 ApplicationService、Runner start 槽和 MCP 适配器；没有第二个模型后端或求解队列。输入权威来源为[生产 Schema](../data/first_stage_contract.schema.json)，交叉规则在[定义服务](../csttool/definition_editing.py)。当前已完成Z模型的公开SDK/真实CST与几何/G03核验；指定桌面正常链同日已通过，见[桌面记录](codex-desktop-acceptance-20261103.md)。

GEO-1–4已在同一事务实现，当前契约及原生边界见[GEO-2–4生产实现与验收](geometry-production-implementation.md)。apply_model_changes每次GEO修改须显式geometry_profile="geometry-v1"；save_project须显式validation_target="geometry"或"simulation"。这些字段已进入实际MCP签名，不新增工具。几何目标实际保存重开/源历史/参数/实体核验后geometry_saved=true、ready=false、definition_revision=null；完整受限仿真目标通过原生几何及设置核验后才ready=true。

GEO仍使用有序features、逻辑实体集合、不可变revision、直接父身份保留及CAS/intent/commit对账。修改保留feature_id，不允许改变op/创建实体ID或任意patch；移除后保留有界身份表。草稿投影不是原生事实；任何修改重置保存/ready声明。失败整批拒绝，已提交但响应丢失补写，不重放CST；geometry-only保存可close(save)，未保存草稿只能discard_candidate。

设置按规范属性唯一归属；history_program拆Units/WCS/组件/feature及受支持SIM职责，A1也使用同一分块控制模板。声明变更生成新候选，不能追加同caption冒充替换。managed_history核对实际Model.mod及表达式，保存/重开观察使用整体计算域和实体事实；一般CSG不宣称精确CAD等价。参数/身份/原生资源责任及失败/取消详见生产实施页。

A1仍独立校准，省略validation_target默认simulation；旧A1 stamp失效且本批未更新，不借GEO许可放行。


## 调用顺序

连接并 claim → list_installations → create_project → 轮询状态、get_operation_result → apply_model_changes → configure_simulation → save_project → inspect_model → submit_run → get_simulation_results → export_simulation_results → close_project → shutdown。

创建/编辑/配置/保存/关闭均走 `kind=definition` 的同一异步 start。受理只返回 run_id，必须等 execution_active=false 且 COMPLETED 后读取 get_operation_result；失败读取状态里的错误/生命周期与诊断。普通求解没有固定总时长限制；原生启动、编辑阶段与退出仍有界。CLI可用 RunnerClient.command 提交相同 payload；没有单独的 CLI 业务实现或完整 GUI 建模面板。

MCP五个新增工具及参数：

|工具|业务参数（另需 control_handle/request_id）|结果|
|---|---|---|
|apply_model_changes|document_id、expected_document_revision、changes、可选 geometry_profile/invalidate_results|新草稿操作 run_id|
|configure_simulation|document_id、expected_document_revision、simulation、postprocess|新配置草稿 run_id|
|save_project|document_id、expected_document_revision、verify_reopen=true、可选 validation_target（GEO必填）|按目标构造/核验，仿真目标才产生 definition_revision|
|close_project|document_id、expected_document_revision、disposition=save/discard_candidate|closed 文档；不会新建或强关原生实例|
|export_simulation_results|run_id、result_revision、formats=[json,csv]|同步的轻量导出结果及相对项目路径/hash/大小|

加上已有九工具，源码目录现为14工具。2026-11-02指定桌面九工具属于历史记录；2026-11-03当前对话实际发现14工具，正常链通过，不等同全部故障门禁。

## 草稿与持久化边界

apply/configure 保存**声明式草稿**，不打开 CST，不声称 live getter 已确认。spec保留参数expression/quantity/description、组件及A1圆柱或GEO有序features/实体集合、背景/边界和仿真/PPS。inspect 返回的是该不可变草稿及其状态，不冒充原生三维几何回读。

每次修改要求当前 expected_document_revision，旧版本仍可只读检查，不能用于覆盖新版本。文档 revision 绑定所有元数据/spec/父版本/源文件 hash。每次保存依据该文档空工程的血缘与当前 spec，新建专用3D候选并重新构造该A1或GEO定义；不会对已确认结果、旧 definition 或用户原工程 Rebuild。这是受管候选的执行选择，不是任意复杂 CAD 的增量历史编辑器。

首次保存通过新建3D对象的一次 RunScript 批量 StoreParameters，另设参数说明；宏内先发布当前 modeler PID并等待父进程核验新DE/安装/创建时间，绑定后才开始写入。空工程的 `-m -b` 在本机未执行宏；同对象第二次 RunScript 也未执行，因此身份门禁与建模合并为单次脚本。构造后的 G03 和计算继续沿用已经验证的 `Model/3D/Model.run` scope。参数赋值不进入结构历史。数值表达式编译为保留 RestoreDoubleParameter 引用的受限算术，不能替换为缓存值。单位、求解器身份、全局 WCS、组件/几何/背景/边界/Tet/频率/模式数进入检查过的 AddToHistory；检查返回，Rebuild、Save、批宏正常返回。宏字符串分段生成，避免大量参数、长表达式或中文说明突破物理行长度。

关闭后用共用只读来源核对实际保存的表达式和完整 B2 投影，再交给已有 stage_definition/verify_definition 的两会话 G03。只有该证明 ready 后才发布 saved 文档；草稿和 empty 均不可求解。close(save) 要求已验证保存，不能悄悄丢弃草稿；discard_candidate 关闭逻辑文档但保留历史和诊断。原生对象本来按操作保存关闭，逻辑 close 不等于正在运行时调用 Project.Quit。已发布的不可变定义/结果不因文档关闭撤销。

## 共享WinWrap生成与门禁（W1–W3）

历史、算术/参数引用、字符串赋值及声明已迁入winwrap_emitter，复用同一A1允许表。控制模板复用为A1/GEO分块执行，保留0+和24字符分段；GENERATED_CODE_INVALID在参数与辅助名称冲突、未知节点或800字符保守物理行预算超限时返回。保存预检在写原生执行意图前完成发射，长输入拒绝而不截断；冲突旧草稿须新建文档并显式重命名参数及引用，不原地迁移或提供旧发射器兼容开关。当前A1保存还需独立检查、data版本门禁及会话内MacroCheckThis；源图/实际XYZ/G03与故障拒绝见[W23实施](winwrap-w23-implementation.md)。其它宏不由此授予通过。

## 支持范围和错误

A1范围为root MWS、mm/MHz、零中心单个Vacuum圆柱；GEO扩展及独立门禁见生产实施页。A1支持XYZ轴、PEC背景、电边界、无对称、Default/Tet、固定现代 near/far 密度、nmodes=1、关闭自适应、后处理损耗设置。频率下限必须等于频段 min。Frequency 与 R_over_Q 各一个，后者中心线、轴与圆柱一致、beta=1、full。XYZ这里只是受限投影/渲染能力，真实Z模型已构造并求解通过；不扩大为三轴真实验收。

说明当前只接受非代理字符的BMP文本及无首尾空白形式，保存后仍逐项核对；emoji样本失真/末尾空白消失已留证，拒绝而非自动替换或strip。

最多128个大小写不重名参数，表达式4096字符/既有算术 AST 预算；不支持任意函数、VBA、路径或脚本。quantity 是工程单位语义声明和几何参数引用的检查依据；不是完整符号量纲代数。A1单圆柱仅创建一次；GEO多feature按独立顺序/消费规则处理。频段、求解模式和 PPS 严格按 Schema，未知字段和非有限值拒绝。

- INVALID_ARGUMENT / UNSUPPORTED_CAPABILITY：输入或范围未支持，原生执行前拒绝。
- STALE_DOCUMENT / DOCUMENT_CONFLICT / DOCUMENT_CLOSED：版本/对象状态不符，不覆写。
- SETTING_UNVERIFIED：模型不完整、实际持久值不同或 G03 未证明；不发布 ready。
- RUN_RECONCILIATION_REQUIRED：已有意图、未提交候选或事实不全，不能重放原生步骤。

## 故障、恢复和停止

意图 → 副本/检查 → G03 → 不可变文档 → definition-commit → current → definition-result。意图和 commit 在 control/runs/<operation>；副本在已有 definitions/verification-* 路径，纳入原生命周期扫描。所有写入沿同一ProjectRunLock；几何目标原生验证在初始锁内，仿真目标由公共verify_definition重新持锁核对catalog并验证；最终再次检查版本，防止丢更新。

同 request_id 重传由 Runner 命令记录返回同 run，不重复创建、重建或求解。已提交但 current/response 缺失，由 reconcile_edit 核验 commit、操作和父版本后补写；发现更新版本不回退指针。未提交候选不自动重做宏或提升。显式 recover 确认全部归属会话退出后，可将未提交操作标记 OPERATION_ABANDONED、保留候选诊断；已提交的缺口必须核对补写，不能弃用。后续显式新编辑仍须检查真实会话已结束。停止在原生调用前/返回后和发布前响应，不强占正在阻塞的 CST 方法，也不伪造关闭证明。

## 结果上下文与导出

新单次结果 schema_version=2：派发前冻结积分轴、中心偏移、几何端点、beta、full、模式1、频率 Hz→MHz 及 `abs(V)^2/(omega*W)`/QFactor.GetTotalEnergy 来源，保存算法文件 hash 和可取得的实际生成宏。假 Worker 没有宏时明确 unavailable；真实宏缺证不能借用当前模板声称实测。读取/导出核对已冻结文件，不能用后来的实现覆盖历史来源。

导出是 Runner 鉴权写命令 export_simulation_results；需要控制租约，活动/待恢复状态拒绝，输出来自已经采用的 result_revision。现有确定性写入使响应丢失后的同 ID 重试不重复求解；JSON/CSV相对路径仍是服务器本地工件，不宣称 resources/read 或远程下载已实现。频率和 R/Q保留现有字段供消费，冻结 postprocess_definition 不依赖当前窗口。

## 当前验收

[定义事务测试](../test/definition_editing_test.py)、[来源测试](../test/result_provenance_test.py)、[官方 SDK 测试](../test/mcp_sdk_test.py)、[公开串行工具](../test/support/validate_typed_definition.py)。52项服务/草稿/来源测试、79项生命周期/Runner等回归和6项 SDK/适配测试分批通过，集合重叠，不能相加为全仓回归；最后渲染细化另复验。

2026-11-02指定Codex对话的九工具空工程创建/检查/同ID重发和正常退出有历史通过记录（不是本次实时工具盘点），见[轻量证据](../knowledge-base/mcp-codex-g02-public-20261102.json)。后续已排除该失败实例并完成14工具 SDK公开链的真实构造/求解/采用恢复/导出/退出，详见[最新验收](typed-public-acceptance-20261103.md)。指定桌面正常链已通过[同日验收](codex-desktop-acceptance-20261103.md)，完整故障矩阵仍待验。

最新生产G03增加实体存在/材质/体积、结构盒/计算盒和六边界原生观察；只用官方允许的查询，没有调用受限的GetLooseBoundingBoxOfShape。布尔CStr严格接受True/-1，false/未知拒绝；体积以mm³和解析圆柱容差1e-6核对。保存构造还核对参数expr与descr；原生参数说明不只停留在框架spec。

单次发布与回执采用之间允许存在故障缺口；先持久结果，再校验已登记接收回执并写algorithm_adopted。已发布结果恢复也核对ACK/关闭/原生档案/接收值与身份后补标记，不重新计算、不改变结果revision。详见[真实收口](typed-public-acceptance-20261103.md)。

## W0调用与持久化边界补充

[W0核查](winwrap-w0-contract.md)明确参数表表达式与历史重放分别验证，AddToHistory立即执行且相同标题可能合并，不是原子事务；失败候选不得发布。MacroCheckThis核心宿主校准已通过14个无求解样本；W2/W3已在受限A1保存链接入独立检查、版本门禁和会话内历史检查，详见W23实施记录；未知诊断能力不会降级成通过。

## Windows后台创建/构造

生产默认公共空工程创建与类型化候选构造使用临时非活动桌面，身份核验后设置quiet，观察用户前台事件并保留详细窗口诊断；不改变公开业务Schema。详情见[验收及剩余入口](cst-background-acceptance-20261103.md)。无法创建桌面时失败，不自动回退到用户桌面；未知交互/退出仍按现有恢复边界处理，不以隐藏窗口代替成功。G03独立CLI尚未迁移，不承诺整个save发布链已无窗口。
