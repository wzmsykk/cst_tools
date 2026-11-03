# 项目定位与变更工具

权威登记为[project-map.json](project-map.json)，结构由[Schema](project-map.schema.json)约束；[feature-index.md](feature-index.md)只生成。功能、工具、人工动态关系和文档角色分开，登记不授予执行权限、语义正确或实际调用证明。稳定设计见[实施体系](project-documentation-tooling-plan.md)，逐批过程见[复审前快照](archive/20261103-semantic-review/project-map-guide.md)。

## 日常入口

```powershell
python scripts/project_inspect.py query --feature F135
python scripts/project_inspect.py query --path csttool/native_definition_builder.py
python scripts/project_inspect.py query --symbol run_new_definition
python scripts/project_inspect.py query --question "quiet"
python scripts/project_inspect.py changes --base HEAD
python scripts/project_inspect.py delete csttool/native_definition_builder.py
python scripts/project_inspect.py graph --path csttool/native_definition_builder.py --limit 40
python scripts/project_inspect.py inventory
python scripts/project_inspect.py tools
python scripts/project_inspect.py validate
```

输出为JSON，包含Git提交、工作区、契约hash、命中原因、全部阅读入口、测试候选、登记关系和未知。问题查询只是字面匹配；多个选择器按并集聚合，不是AI语义检索。符号重名列出全部声明和歧义，不凭名字挑选。路径或功能未映射返回退出2；结构或运行错误退出1；正常查询退出0。delete始终是预检，safe_to_delete=False，不删除任何文件、不授权删除。

inventory包含全范围文件分母及每个旧路径→保留路径/责任/处置记录；根目录分类不代表功能关系已审查。vendor、二进制、模型、跟踪的历史artifacts与不改动的utils分别登记；无显式F关系的文件显示unmapped，不能当无影响。

graph输出AST候选和显式登记关系，提供总数/截断标记；import、注册、调用候选和真实分发分开。无法静态决定的接收者、反射或注入目标保持未知；不会导入被分析模块。跨语言VBA/COM/原生库内部不由Python AST解析器解释，须读登记合同及真实验收。

## 修改与同步

1. 检查工作区，查询功能/源码/消费者和必读合同；缺口先补查，工具结果不代替判断。
2. 修改实现、对应API/设计/测试和project-map.json。每个source的symbols属于该文件，不能将多个文件的符号混在第一个源码下。
3. 当前状态、TODO与证据按AGENTS同步；文档角色不明确的条目标为unreviewed，不按文件名自动升级为现行规范。
4. 显式生成派生索引：`python scripts/project_inspect.py render --write`。不带--write只打印预览；查询及validate不自动重写索引或人工关系。
5. 运行validate和`test/documentation_index_test.py`、对应功能测试。source_fingerprints仅记录采集时输入；变化提示复审，不自动刷新关系或宣布语义有效。完成复审后显式更新相应采集hash及证据。

查询、inventory、graph、changes、delete、tools和validate均不运行测试、构建、CST、COM、部署或网络，不创建缓存文件。建议将需要保留的JSON通过调用方显式重定向到本轮artifacts；工具不代替调用方清理这些报告。render --write只更新固定派生Markdown；构建/真实探针仍独立显式执行。

## 覆盖和错误边界

路径/符号/章节有效、派生索引一致，只是结构事实。工具的动态目标列表可以是候选或未知；没有运行记录就不标记runtime_proven。人工登记关系有适用基线，内容hash变化只提示复审。旧记录属于原日期/版本，不因本次生成工具而成为新代码验收。

文档清单保留已核角色与未核角色，不把自动分类当完成人工整理。工具清单中未审查的外部副作用入口明确禁止自动调用；参数提取只是AST事实，不证明参数组合安全。范围外、缺失或历史文件仍显示原因，不静默按测试选择器忽略。


## D2实现与验收边界（2026-11-03）

CLI固定UTF-8输出，便于Windows重定向/机器读取。query报告匹配理由、声明位置/歧义、正向与反向候选、必读文档和非执行的验证计划；未登记的Python/VBA声明也可定位，但仍返回未映射。AST绑定始终是候选，不能证明对象身份、回调实际投递或清理已执行。解析失败单独报告。

changes对指定Git提交比较当前已暂存/未暂存/删除文件，并纳入未忽略的新文件；一次解析共享给各文件影响结果。它只报告当前工作树的候选，不重建旧版本调用图。graph支持路径筛选与非负输出上限；空范围返回2，截断提供总数。delete永远不批准删除，其已知引用仅来自静态候选和人工登记；字符串、嵌入宏、文档和外部消费者须另查。

没有当前根目录Git时，inventory/query等使用源码包release-manifest.json的files范围，不借用父目录Git；changes拒绝这种环境。源码包缺少全仓测试或文档时，validate诚实报告缺失，不把局部包冒充全仓通过。render不带--write只输出预览，带--write才改派生索引。




## D3工具清单与人工动态关系

以下实现/验收叙述属于2026-11-03 D3批次；本页保留现行工具合同，不将原批次结果冒充后续变更验收。

唯一登记仍在project-map.json。`python scripts/project_inspect.py tools` 返回工具条目及范围覆盖；`query --path pack.bat`等路径查询同时返回registered_tools。路径没有F功能映射时仍返回2，不把工具条目冒充功能覆盖。query/graph同时检索人工关系source、targets及consumers；工具只返回登记，不导入或调用它们。

工具范围：scripts/和test/support/下全部Python模块（含无main guard却有顶层副作用的模块）、第一方Python显式main入口、第一方shell脚本。vendor、历史artifacts、知识库和按约定保持不变的utils明确排除；它们仍在文件inventory中，排除不证明无外部调用。公共MCP工具由mcp_server的装饰器注册，本清单登记服务进程入口，不复制一套MCP工具定义。数量从tools命令取得；完整范围登记也不是允许执行列表。

每条工具提供用途、入口类型、字面参数、已知副作用、授权边界、未知及证据。AST只能观察字面add_argument，委托base、Qt或动态参数可能遗漏；observed_arguments和人工补充的arguments区分。工具本身也不是一律只读：打包会写ZIP并启动烟雾子进程，ANTLR --prepare下载/构建，NoUI会激活COM且可能弹窗，故障探针可kill本轮GUI/Runner，preview模块顶层即创建Qt/写图。未审查的传递副作用明确标注，不能由文件名推断安全。

人工关系逐项登记：入口、已知/默认目标、消费者、触发、线程/阶段、清理责任、证据和未知。R001–R004为GUI控制器选择/生产计时器与线程池/退出/注入Qt控制器；R005–R008为MCP注册/client_factory/HTTP分发/执行器选择；R009–R011为editor、worker工厂和Manager线程池；R012–R014为ACK/原生收尾/检查点采用；R015–R018为跨语言COM包装、WinEvent回调、logging handler及发布链。GUI生产使用RunnerController，与注入的GuiRunController分开。嵌入的PowerShell/C#/VBA及CST内部不由Python AST解释，未知始终保留。

全部Markdown有角色条目；仅已人工确认的导航/状态/维护文档标为现行职责，历史/冻结快照按来源目录标记，其他条目允许unreviewed。该清单不是文档正文审计；HTML/CHM等厂商资源不在Markdown角色分母内。

维护步骤：修改入口、参数、回调、注入或清理时，先查相关F和relations/tools，再修改对应登记及说明；人工核对后更新受影响源码hash（仅采集身份），显式render，再validate和相应测试。validate会拒绝工具入口漏登/移除未清、字面参数过期、重复工具/关系ID、关系消费者失效、Markdown缺项和派生索引过期。它不会自动补关系、改hash、运行测试或启动CST。

源码包保留原仓库登记，省略夹具或历史文档时validate仍会诚实报缺失；工具范围差异不自动删除原登记，不把局部包误判为全仓一致。运行来源可从input中的Git/manifest身份区分。



## D4故障矩阵与源码包边界

D4修复以下问题：源码包漏带离线文本夹具及base系列CLI；生成的根README未登记；Git重命名可能漏掉旧路径；fenced code中的标题误计章节；包清单缺少严格路径/形状和字节完整性核验；render写入未使用统一解析后路径保护。既有D1–D4数字保留其原批次，不升级为后续语义复审代码验收。

|故障或边界|检查与预期|
|---|---|
|目录重命名/删除|changes关闭Git重命名折叠，分别返回旧/新路径；不虚构旧版本调用图|
|过期/伪章节|ATX章节解析忽略backtick/tilde fenced块，重复slug带序号；过期锚点失败；不是完整Markdown渲染器|
|图截断/空范围|limit=0仍报告总数/截断；未知范围返回2，负数拒绝|
|过期源码hash|只提示复审，不自动改契约或hash|
|损坏JSON/manifest形状或路径|退出1并给结构化错误；拒绝越界、ADS、非规范路径及清单自引用|
|清单内容ID/文件hash不符、已列文件丢失|包校验失败；不把意图省略项与实际丢失混同|
|解析后路径逃逸|统一safe_path用于契约/manifest读取和索引写入；无需真正创建OS链接即可离线注入验证拒绝路径|
|生成README|availability=package-only，在仓库无物理文件；在源码包必须列入manifest并存在|
|本机Git与无Git源码包|只认当前根Git；包不能借父Git身份，changes拒绝无Git环境；包模式不能用于Git工作树豁免|

`python scripts/project_inspect.py validate`继续检查完整仓库契约；源码包因有意省略的vendor/开发脚本会失败。新增`validate --scope package`只适用于无根Git且有合法manifest的解压包：核对已列全部字节、整体内容ID和包内映射/符号/角色/登记，将原契约中未随包提供的引用放入omitted_references，明确repository_complete=False。清单hash证明字节一致，不认证作者或运行结果；查询的input身份也不暗示完整性已验。只读查询仍不修改manifest。若包内源码被合法修改，应视作新的待审查快照，而不是自动“修复”原清单。

当前选择保留离线文本夹具、协议样本、test/support PowerShell入口、3个base CLI和根知识库JSON；继续省略真实CST模型、原始场、厂商帮助、旧pack.bat及GUI UI再生成脚本。已生成源码包的缺省引用预期为这两个开发脚本与vendor README。随包测试不代表全部集成测试均可直接运行；D4原批次只执行指定离线工具/迁移/登记测试、ZIP/编译/无CST GUI烟雾及包命令验收，不求解、不部署、不推送。


## 文档语义复审入口

每个document条目的review记录本次适用性/当前合同核对范围、来源与剩余限制；源码/离线对照不验证旧实测真实性或外部研究。查[复审报告](documentation-semantic-review.md)，不能只因role已分类就推断每条技术陈述已对现实现验证。后续功能变更复审相关条目，不自动将旧日期替换为今天。

文档的content_sha256_at_review用于检查正文是否在复审后变动；变更后人工重核scope/checked_sources/limitations再登记新指纹，不自动续期。test/documentation_semantics_test.py校验指纹及归档正文，不能据hash相等判定语义正确。
