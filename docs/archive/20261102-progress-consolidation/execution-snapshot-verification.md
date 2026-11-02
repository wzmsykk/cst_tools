# 历史快照：execution-snapshot-verification.md

归档日期：2026-11-02。保留归档前内容及阶段措辞，不作为现行接口或当前验收结论；相对链接已重定位。现行入口：[当前状态](../../current-status.md)。

# B3 执行配置快照验证内核

2026-11-02。公共实现`csttool/execution_snapshot.py`，GUI/CLI/MCP将共用本模块，不新增CST调度、数据库私有格式解析器或协议服务。[原生采集与RunStore/B4子集](../../native-execution-capture.md)已接入；默认Managed/HOM、公共single-simulation定义服务及完整B4/G03仍未完成，publish_ready不解锁。下文较早B3验收和后续范围按分批记录阅读。

## 来源与信任边界

预期配置必须由执行所有者从冻结定义取得，不可从读回值反推。`ExecutionBinding`绑定project_id、attempt_id、definition_revision、database_sha256、cst_build和精确scope；`ExecutionConfig`保存method、mesh、target开关/高精度值、自适应开关和请求模式数。`ExecutionExpectation`另存独立结果状态、带时区的attempt观测窗口、原target表达式和定义文件hash。构造器拒绝错误类型，不能把1当True或把缺少结果状态当失败。

`expectation_from_projection`检查B2的source_hash与所有者给定的发布定义hash及scope匹配，要求mm/MHz、显式HF Eigenmode及六项执行配置。B2新增只读`Projection.exact_values`保存target的Decimal求值字符串；工厂从它冻结预期，而不是从展示float重建高精度值。原表达式单独保留，Reset也清除本对象对应的精确值。

这些库对象不是MCP工具输入：本模块不能认证未来RunStore记录是否真实、哪个进程生成了数据库、宏是否确实在本次Start之后采集。调用者必须建立这些权威事实。哈希相等也不能独自排除“旧数据库被错误标上新attempt”；生产采集必须绑定正确阶段与不可变attempt工件，B4/公共服务接入需验证此边界。当前不提供以客户端自报expected覆盖冻结定义的接口。

## 三个只读入口

|入口|作用|不能证明的内容|
|---|---|---|
|`validate_execution_snapshot(expectation, snapshot, profile_id=...)`|核验结构、六维绑定、profile、时间/阶段、原始值与配置比较；不访问文件|绑定输入的真实性、数据库文件本体或实时CST状态|
|`read_snapshot_record(path, max_bytes=65536)`|严格UTF-8 JSON，拒绝重复键/非有限数字/错误顶层、过度嵌套、超预算；重复读取字节并核对文件身份|不是Model.db读取器，不采集CST字段；OS访问错误仍由调用者处理|
|`verify_execution_artifact(expectation, snapshot, database_path=..., max_bytes=64MiB)`|先做语义验证，再对真实数据库流式hash两次，核对stat身份与绑定hash；成功设置database_verified=true|没有文件锁，不负责确认生产者关闭或证明哪次attempt写入文件；不保证函数返回后文件永远不变|

路径必须由所有者解析为已关闭工件，不是暴露任意路径的MCP能力。JSON预算可显式设为1字节至1MiB，数据库预算须为正整数；超限拒绝，不截断。函数均不修改源文件、不启动CST、不补算、不采用结果、不改Runner状态。数据库消失/权限等错误unresolved；变化或hash不符stale；预算超限rejected。

后续后台接入应将文件读取/hash放在控制锁之外，再核对所有权与revision，不能让大工件I/O阻塞status、停止或恢复暂停。本模块尚未接入Runner；字节预算不是对故障文件系统阻塞时间的保证。

快照JSON恰含binding、phase、observed_at、values；phase只接受post-attempt，带时区观测时间须落在所有者提供的attempt窗口内（窗口须包含采集完成阶段，而不是仅Solver.Start调用区间）。values恰含六个已知键，所有值均保留原始字符串：SolverTypeTet、FrequencyTargetActive、FrequencyTargetValue、AdaptionActiveTet、Modes、MeshType。不给任意数据库key扩展口，不从空串补Default/False/0。

## 固定profile及精度

按用户2022大版本行为一致的决定，唯一登记profile改为`cst-2022-root-tet-g6-v1`；root/Tet及6位g规则复用到2022各小版本/补丁，实际校准仍仅[本机2022.5](../../../knowledge-base/cst-solver-settings-readback-calibration-20261028.md)。方法1=Default、2=General (Lossy)，mesh=1为Tet，Modes仅已实测的1；非2022、其他scope/mesh/模式数或未知枚举unsupported。小版本规则复用不放宽attempt绑定中的精确build核对；安装hash保留诊断，同attempt中途变化仍拒绝。这是用户工程假设，不是所有2022版本均已实测。Modes限制不是CST功能限制，不影响旧Worker的其他能力。

调用者只能选择登记ID，不能传入方法映射、精度或容差。规范用例中的calibration_profile是人工前提，不直接注册为生产规则。当前profile来自原版本文档/静态格式及既有实测，不是本轮新CST校准。

target比较使用明确链条：保留的高精度Decimal预期→binary64→6位有效数字g格式→与原生字符串数值比较。不是根据小数点位数或“最后打印480”推导±1MHz容差。480.0001可格式化为480；480.4不能；493.827156匹配493.827而不匹配493.828。原生值本身不符合已登记6位有效数字格式、非有限或非法文本时拒绝。数值输入限128字符、数量级绝对值≤100；未知locale/格式不猜。

跨平台舍入边界等尚无本轮新原生校准，不扩张该profile适用安装；不能靠纯Python测试证明所有CST版本数值格式。disabled target仍比较其存储值，effective_lower_bound_mhz明确为null，不能把保存的480当有效下限。

## 报告与失败处理

`SnapshotReport`区分execution-snapshot-match/mismatch、stale、unresolved、unsupported、malformed和rejected。B0用例的execution-match/mismatch映射到这两个公共状态，不能映射成live-match。报告有逐字段expected/observed/matches/source_key、原始值、绑定、观测时间和表达式。绑定/枚举等无效时不发布解码字段；配置不匹配时保留可追溯比较，报告原因可多于B0最小reason集合。

result_success来自独立运行事实。false或null均可与execution-snapshot-match共存，绝不据配置匹配把失败求解改成功，也不据Start返回值造结果。publish_ready始终false，live_value始终null。database_verified只表示本次实际文件哈希核对完成，不代表求解成功、结果采用或标准退出。

stale需重新取得与正确定义/attempt绑定的证据，不能改标签后重试；缺失数据保持unresolved；profile不支持需先校准，不能自定义map放行。不得为了读设置额外求解，也不因本报告去Rebuild破坏结果。Save不刷新旧快照、Rebuild后证据可能消失的原有边界保持。

## 验收与下一步

[离线测试](../../../test/execution_snapshot_test.py)实际执行全部11项E oracle，以及绑定/时间/阶段故障、未知profile/枚举、缺失值、严格JSON、双hash变化与预算、B2精确值冻结。不是只检查用例表自身。

另从既有2026-10-28校准目录原字节复制6组database.tsv/solver.tsv，共34982字节，固定在[test fixtures](../../../test/fixtures/execution_snapshot_native/manifest.json)，每文件hash及原来源记录齐备，TSV禁止换行转换。预期取独立校准计划；离线重放涵盖Default/General、零target、禁用target求解失败、自适应和精度。重放使用显式人工绑定/时间窗口，验证原生字符串能被解析比较，**不认证历史attempt绑定或原始CST工程可重开**。原始模型/场已在旧批次清理，本轮未启动CST；现存历史数据库未复制进fixtures，也未删除。

本批文档同步前合并235 passed（4.56s），报告artifacts/b3-native-verified-20261102.xml：92项B3测试（含11项E、6项历史字符串重放）及143项前置/索引回归，数字重叠不累加。B0历史not-run标记不改为运行数据库；当前已实际执行H/S/M 35项、E 11项及D04组合行为，不能宣称56项全部通过。

文档同步后最终235 passed（5.57s），报告artifacts/b3-final-20261102.xml；diff空白检查通过。本轮已结束的pytest临时目录已清理，只保留轻量XML、源码和固定原生TSV/manifest。未删除原有校准数据库或其他任务产物，artifact不保证随Git迁移；本轮未提交或推送。

后续已按用户授权完成[RunStore绑定及B4采集子集](../../native-execution-capture.md)：正确3D scope的六字段、正常/实际求解失败及旧库重标拒绝，均由副本串行取得证据。默认生产调用方与公共定义服务仍未迁移，Save/Rebuild全部时间组合及完整G03/MCP端到端未通过；后续新求解须按明确副本范围执行，不自动追认旧证据为所有新实现通过。
