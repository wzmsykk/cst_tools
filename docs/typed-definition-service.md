# 首阶段类型化定义事务

更新：2026-11-03。实现位于同一个 ApplicationService、Runner start 槽和 MCP 适配器；没有第二个模型后端或求解队列。输入权威来源为[生产 Schema](../data/first_stage_contract.schema.json)，交叉规则在[定义服务](../csttool/definition_editing.py)。当前已完成Z模型的公开SDK/真实CST与几何/G03核验；指定桌面整链由用户选择稍后验收。

## 调用顺序

连接并 claim → list_installations → create_project → 轮询状态、get_operation_result → apply_model_changes → configure_simulation → save_project → inspect_model → submit_run → get_simulation_results → export_simulation_results → close_project → shutdown。

创建/编辑/配置/保存/关闭均走 `kind=definition` 的同一异步 start。受理只返回 run_id，必须等 execution_active=false 且 COMPLETED 后读取 get_operation_result；失败读取状态里的错误/生命周期与诊断。普通求解没有固定总时长限制；原生启动、编辑阶段与退出仍有界。CLI可用 RunnerClient.command 提交相同 payload；没有单独的 CLI 业务实现或完整 GUI 建模面板。

MCP五个新增工具及参数：

|工具|业务参数（另需 control_handle/request_id）|结果|
|---|---|---|
|apply_model_changes|document_id、expected_document_revision、changes、可选 invalidate_results|新草稿操作 run_id|
|configure_simulation|document_id、expected_document_revision、simulation、postprocess|新配置草稿 run_id|
|save_project|document_id、expected_document_revision、verify_reopen=true|构造副本并完成 G03 后返回 saved 文档及 definition_revision|
|close_project|document_id、expected_document_revision、disposition=save/discard_candidate|closed 文档；不会新建或强关原生实例|
|export_simulation_results|run_id、result_revision、formats=[json,csv]|同步的轻量导出结果及相对项目路径/hash/大小|

加上已有九工具，源码目录现为14工具。当前 Codex 连接实际加载的仍是九工具；新增五工具尚未在当前桌面对话调用，不能把 SDK 测试当成桌面热加载。

## 草稿与持久化边界

apply/configure 保存**声明式草稿**，不打开 CST，不声称 live getter 已确认。spec 保留参数 expression/quantity/description、组件、单个真空圆柱、背景/边界和仿真/PPS。inspect 返回的是该不可变草稿及其状态，不冒充原生三维几何回读。

每次修改要求当前 expected_document_revision，旧版本仍可只读检查，不能用于覆盖新版本。文档 revision 绑定所有元数据/spec/父版本/源文件 hash。每次保存依据该文档空工程的血缘与当前 spec，新建专用3D候选并重新构造该 A1 定义；不会对已确认结果、旧 definition 或用户原工程 Rebuild。这是首阶段单圆柱的执行选择，不是任意复杂 CAD 的增量历史编辑器。

首次保存通过新建3D对象的一次 RunScript 批量 StoreParameters，另设参数说明；宏内先发布当前 modeler PID并等待父进程核验新DE/安装/创建时间，绑定后才开始写入。空工程的 `-m -b` 在本机未执行宏；同对象第二次 RunScript 也未执行，因此身份门禁与建模合并为单次脚本。构造后的 G03 和计算继续沿用已经验证的 `Model/3D/Model.run` scope。参数赋值不进入结构历史。数值表达式编译为保留 RestoreDoubleParameter 引用的受限算术，不能替换为缓存值。单位、求解器身份、全局 WCS、组件/几何/背景/边界/Tet/频率/模式数进入检查过的 AddToHistory；检查返回，Rebuild、Save、批宏正常返回。宏字符串分段生成，避免大量参数、长表达式或中文说明突破物理行长度。

关闭后用共用只读来源核对实际保存的表达式和完整 B2 投影，再交给已有 stage_definition/verify_definition 的两会话 G03。只有该证明 ready 后才发布 saved 文档；草稿和 empty 均不可求解。close(save) 要求已验证保存，不能悄悄丢弃草稿；discard_candidate 关闭逻辑文档但保留历史和诊断。原生对象本来按操作保存关闭，逻辑 close 不等于正在运行时调用 Project.Quit。已发布的不可变定义/结果不因文档关闭撤销。

## 支持范围和错误

只支持 root MWS、mm/MHz、零中心单个 Vacuum 圆柱、XYZ轴、PEC背景、电边界、无对称、Default/Tet、固定现代 near/far 密度、nmodes=1、关闭自适应、后处理损耗设置。频率下限必须等于频段 min。Frequency 与 R_over_Q 各一个，后者中心线、轴与圆柱一致、beta=1、full。XYZ这里只是受限投影/渲染能力，真实Z模型已构造并求解通过；不扩大为三轴真实验收。

最多128个大小写不重名参数，表达式4096字符/既有算术 AST 预算；不支持任意函数、VBA、路径或脚本。quantity 是工程单位语义声明和几何参数引用的检查依据；不是完整符号量纲代数。新几何对象只允许一次，后续改 R/L 参数，不追加第二个圆柱。频段、求解模式和 PPS 严格按 Schema，未知字段和非有限值拒绝。

- INVALID_ARGUMENT / UNSUPPORTED_CAPABILITY：输入或范围未支持，原生执行前拒绝。
- STALE_DOCUMENT / DOCUMENT_CONFLICT / DOCUMENT_CLOSED：版本/对象状态不符，不覆写。
- SETTING_UNVERIFIED：模型不完整、实际持久值不同或 G03 未证明；不发布 ready。
- RUN_RECONCILIATION_REQUIRED：已有意图、未提交候选或事实不全，不能重放原生步骤。

## 故障、恢复和停止

意图 → 副本/检查 → G03 → 不可变文档 → definition-commit → current → definition-result。意图和 commit 在 control/runs/<operation>；副本在已有 definitions/verification-* 路径，纳入原生命周期扫描。所有写入沿同一个 ProjectRunLock，G03在锁重入边界外调用，最终再次检查版本，防止验证期间丢更新。

同 request_id 重传由 Runner 命令记录返回同 run，不重复创建、重建或求解。已提交但 current/response 缺失，由 reconcile_edit 核验 commit、操作和父版本后补写；发现更新版本不回退指针。未提交候选不自动重做宏或提升。显式 recover 确认全部归属会话退出后，可将未提交操作标记 OPERATION_ABANDONED、保留候选诊断；已提交的缺口必须核对补写，不能弃用。后续显式新编辑仍须检查真实会话已结束。停止在原生调用前/返回后和发布前响应，不强占正在阻塞的 CST 方法，也不伪造关闭证明。

## 结果上下文与导出

新单次结果 schema_version=2：派发前冻结积分轴、中心偏移、几何端点、beta、full、模式1、频率 Hz→MHz 及 `abs(V)^2/(omega*W)`/QFactor.GetTotalEnergy 来源，保存算法文件 hash 和可取得的实际生成宏。假 Worker 没有宏时明确 unavailable；真实宏缺证不能借用当前模板声称实测。读取/导出核对已冻结文件，不能用后来的实现覆盖历史来源。

导出是 Runner 鉴权写命令 export_simulation_results；需要控制租约，活动/待恢复状态拒绝，输出来自已经采用的 result_revision。现有确定性写入使响应丢失后的同 ID 重试不重复求解；JSON/CSV相对路径仍是服务器本地工件，不宣称 resources/read 或远程下载已实现。频率和 R/Q保留现有字段供消费，冻结 postprocess_definition 不依赖当前窗口。

## 当前验收

[定义事务测试](../test/definition_editing_test.py)、[来源测试](../test/result_provenance_test.py)、[官方 SDK 测试](../test/mcp_sdk_test.py)、[公开串行工具](../test/support/validate_typed_definition.py)。52项服务/草稿/来源测试、79项生命周期/Runner等回归和6项 SDK/适配测试分批通过，集合重叠，不能相加为全仓回归；最后渲染细化另复验。

Codex 当前对话的九工具空工程创建/检查/同ID重发和正常退出通过，见[轻量证据](../knowledge-base/mcp-codex-g02-public-20261102.json)。后续已排除该失败实例并完成14工具 SDK公开链的真实构造/求解/采用恢复/导出/退出，详见[最新验收](typed-public-acceptance-20261103.md)。指定桌面完整 G01–G08 仍待验。

最新生产G03增加实体存在/材质/体积、结构盒/计算盒和六边界原生观察；只用官方允许的查询，没有调用受限的GetLooseBoundingBoxOfShape。布尔CStr严格接受True/-1，false/未知拒绝；体积以mm³和解析圆柱容差1e-6核对。保存构造还核对参数expr与descr；原生参数说明不只停留在框架spec。

单次发布与回执采用之间允许存在故障缺口；先持久结果，再校验已登记接收回执并写algorithm_adopted。已发布结果恢复也核对ACK/关闭/原生档案/接收值与身份后补标记，不重新计算、不改变结果revision。详见[真实收口](typed-public-acceptance-20261103.md)。

## W0调用与持久化边界补充

[W0核查](winwrap-w0-contract.md)明确参数表表达式与历史重放分别验证，AddToHistory立即执行且相同标题可能合并，不是原子事务；失败候选不得发布。MacroCheckThis仅为待CST宿主校准的语法检查候选，当前生产API和ready条件不变；未知诊断能力不会降级成通过。

## Windows后台创建/构造

生产默认公共空工程创建与类型化候选构造使用临时非活动桌面，身份核验后设置quiet，观察用户前台事件并保留详细窗口诊断；不改变公开业务Schema。详情见[验收及剩余入口](cst-background-acceptance-20261103.md)。无法创建桌面时失败，不自动回退到用户桌面；未知交互/退出仍按现有恢复边界处理，不以隐藏窗口代替成功。G03独立CLI尚未迁移，不承诺整个save发布链已无窗口。
