# 工程预处理诊断与退出边界

2026-10-14：修复发布版786f943预处理失败后temp为空的问题。

## 原因及行为变化

旧实现使用TemporaryDirectory，异常时自动删除副本和宏；subprocess.run的180秒总超时还会终止直接启动的进程。因此空temp不是“未启动CST”的证据，也无法从该堆栈判断加载、历史执行或重建具体卡在哪里。

现实现仍使用`-m -b 副本.cst`，不更改原工程，不强杀，不自动重试：

- 每次创建`temp/cst-preprocess-<随机ID>`，日志与异常打印该绝对路径。
- `preprocess-report.json`映射原工程、目标工程、参数JSON及成功/失败；`stage.txt`区分parameters、bind-history、rebuild、save、export-parameters；`session-status.json`记录启动PID、创建时间、已观察子进程、未确认归属进程和退出状态。
- `cst.log`重定向标准输出/错误；`runner-output.txt`保留校验用输出；`completion.txt`与`parameters.txt`仍是完成/参数契约。
- 加载和非计算阶段按180秒无文件变化门禁，完成标记后退出60秒有界；历史执行、重建、保存不设总超时，避免大型工程正常操作被误杀。没有新进展时这些阶段可能长期等待，需人工正常中止；本改动不宣称具有任意卡死检测。
- Python异常后保留整个工作副本及Model/3D/Model.run，不删除仍可能被CST使用的文件；下次启动扫描旧进程身份，已观察进程仍活跃则拒绝再次提交。
- 成功要求本次关联进程退出确认、退出码、成功标记、宏输出和必需参数全部通过。其他独立实例不属于本次退出门禁，不论启动时间或用户。随后清理本次大副本/同名结果目录，保留根目录Model.run与轻量诊断。失败副本需要确认所有相关进程正常退出后人工清理。

`CstProjectPreprocessor(timeout=180)`现在表示受控阶段空闲门禁，而非整个预处理总时限。测试注入runner获得timeout=None；此注入不提供真实进程退出证明。现有参数表达式与历史绑定方式不变。

## 验收及TODO

### 独立CST实例的归属门禁修正

以下启动前基线方案是中间版本记录，已由后续“共享服务器任务级归属”取代；不是现行阻塞规则。

用户报告旧preprocess-fix包因其他独立CST实例被误拒绝；本机未取得其session-status.json，因此用户提供的实例归属信息与本地源码缺陷分别记录，不宣称复现真实现场。

预处理在Popen前记录CST进程基线（PID+create_time），wait_probe的preexisting_processes仅由调用者提供，不能在启动后现采并当作基线。基线独立实例记录在session-status.json，不进入foreign_processes、不等待它退出、不关闭它。已证明为本次子进程的身份始终归owned，仍须正常退出。

foreign_processes每次重算，仅包含当前仍活跃、非基线且未证明归属的实例，避免累积已结束记录；PID复用但create_time不同不享受基线豁免。启动后新独立实例仍保守拒绝，须检查诊断，不按进程名猜归属。失败重提不检查preexisting_processes，只检查owned及未归属记录的当前身份。

独占验收工具exclusive_probe原有“启动前必须没有CST”规则不变；其他wait_probe调用不传基线时无豁免。此修正不解决厂商进程转交的所有情况，仍需真实并存实例/新未知实例/子进程退出验收，不取消完成标记与产物检查。

本批全套离线510 passed、19 integration deselected，覆盖启动前采集、独立实例豁免、PID复用拒绝、未知实例退出不残留、本次子进程未退出仍拒绝；未启动真实CST。旧包生成的失败回执无启动前基线，不能倒推证明其foreign实例独立，旧回执的活跃身份恢复检查仍保留，需人工核对后按恢复流程处理，不自动删除回执以绕过门禁。

### 共享服务器任务级归属（现行）

预处理wait_probe传入task_project=独立副本绝对路径。已观察父子关系、CST进程命令行中精确匹配该副本路径，才归owned；保存PID+create_time，关联孤立实例及其可观察子进程也须退出。不得用同用户名、进程名、出现时间作为任务关联证据。CST名称只用于筛选路径检查候选，不足以建立归属。

全机foreign_processes与preexisting_processes仅作诊断，不参与预处理成功或重提门禁；同用户新开实例、其他用户实例、未知但无任务关联的实例均不关闭、不等待、不阻塞。全机扫描AccessDenied与无关联实例cmdline不可读可跳过；已确认任务关联进程无法检查则仍保守失败，不伪造退出。启动器PID复用不继承原归属。

旧失败回执的foreign没有证明关联，故不再阻塞重提；owned活跃身份仍拒绝，不删回执。完成标记、输出参数与保存副本检查保持原样。独占验收工具exclusive_probe仍要求整机空闲，仅限串行验收，不作为生产预处理限制。

TODO：真实共享服务器并存实例验收；父进程极快退出且关联进程不暴露工作路径的转交仍可能漏观测，不宣称消除此边界。命令行匹配不得替代完成契约，也不能扩展为结束其他任务的权限。

本批离线514 passed、19 integration deselected，覆盖运行期间独立实例不拒绝、其他用户访问拒绝不影响门禁、精确路径不误匹配相似路径、关联孤立进程不退出仍拒绝、旧foreign回执不阻塞以及原owned活跃拒绝；未启动真实CST。测试临时目录已清理，需重新运行生成模拟产物。

### 可选保留原mesh

GUI“扫描与算法设置”勾选“预处理不修改 mesh”，或Python `preprocess(..., modify_mesh=False)` / `prepare_project(..., modify_mesh=False)`。默认True，与旧行为一致。

保留模式不新增/覆盖cell，不写MeshSettings，不改EigenmodeSolver.SetMeshAdaptationTet；只绑定HOM频率和模式数。cell不再是必需参数。仍执行历史、Rebuild与Save；不保证已有网格数据不重新生成，也不保证频率改变时原自适应策略不重新计算。

算法配置键`preprocess_modify_mesh=False`经应用后端传入项目准备；project.ini的`[mesh] fixed=False`记录策略（并非读取原工程自适应开关），HOM运行清单新增同名键，旧清单缺键默认True。继续运行恢复项目策略，禁止切换策略，须新建项目。cells_per_wavelength在保留模式只保留配置值，不应用、不作为真实网格读回值；project SHA仍约束工程身份。

GUI使用原生复选框及禁用状态，并提供边界提示。保留模式禁用网格密度输入和收敛分析；后端拒绝保留与收敛同时启用，不静默修改设置。新选项当前接入HOM GUI，优化器原有默认固定mesh行为不变。修改明细输出mesh-keep，报告记录modify_mesh。

TODO：真实CST验证已有cell表达式/自适应/非默认网格设置均未被预处理覆盖，区分设置保留与重建后网格缓存变化；离线渲染/模拟不能代替此验证。

本次全套离线506 passed、19 integration deselected。新增cell缺失接受、配置持久化、后端透传、恢复策略漂移、清单策略身份、GUI禁用/取消恢复与收敛冲突测试。未启动CST，也未对实际桌面布局做视觉验收。

### 预处理修改明细（2026-10-14新增）

`changes.tsv`每行记录CST时间、action、target、before、after、outcome；字段中的Tab和换行转义。Python在监测时转发完整行至现有日志/JSONL及GUI日志链，阶段变化输出一次，不增加周期性时长刷屏；退出或异常后补读尾部。

- fmin/fmax/nmodes：已有参数记录parameter-keep和原始表达式，缺失参数记录新增请求及读取值。
- cell：记录修改前表达式、指定值和修改后读取值；该参数按既有固定mesh策略覆盖，不是本次新增的修改行为。
- history：记录完整历史块，包括FrequencyRange=fmin/fmax、频率目标=fmin、模式数=nmodes、MeshAdaptationTet=False、MeshType=Tet及StepsPerWaveNear=cell。旧求解器设置未读取，显示`<not-read>`，不能当作前后对比。返回记录为returned-not-verified，不宣称每个setter已逐项核验。
- rebuild返回成功、Save返回、参数导出返回及宏错误分别记录。失败先捕获原始Err.Number/Description，再写诊断，防止诊断错误替换业务原因。

按CST 2022本地Application文档，GetParameterSValue接收long索引，日志通过GetParameterName寻找索引再读取表达式，不按名字调用，也不使用数值恢复代替表达式。TSV使用VBA本机ANSI编码，Python按本机编码读取；跨机器编码迁移需保留原始文件并指定原编码。此明细不是新的任务ABI，不改变成功门禁；缺日志不能当成没有修改，宏编译/加载失败可能尚未创建TSV。

本次相关离线52项通过，新增完整行增量读取/不重复输出、阶段变化和参数索引契约测试；未启动真实CST，因此不将静态VBA检查宣称为宏运行验收。TODO补真实明细、失败尾部及GUI实时显示验收。

本批次离线50项通过：预处理、阶段监测、文档索引、工程mesh设置、VBA文档契约、应用后端、保存场导出生命周期。覆盖失败留档、成功清理大副本、活跃旧进程拒绝重提、长重建与完成后退出有界。未在用户F盘部署机器重跑原模型，也未证明其超过180秒的实际原因。旧发布压缩包不会随源码修改自动更新。

TODO：真实大工程串行验收加载/长重建/保存/标准退出；故障注入加载失败和退出卡住；扩展GUI预处理阶段展示与人工正常取消入口。子进程仅能通过已观察的父子关系确认，极短启动转交仍可能导致保守拒绝；不通过猜测进程名替代归属证明。
