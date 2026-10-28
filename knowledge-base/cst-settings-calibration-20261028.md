# CST设置受控副本校准（2026-10-28）

## 范围和证据身份

本轮获得V01–V06受控副本授权；只在Pillbox副本进行设置、保存、Backup、重开查询及指定的表达式Rebuild，不调用Solver.Start。原工程不写入，不连接全局Active3D，不强杀进程。运行工具：[calibrate_cst_settings.py](../test/support/calibrate_cst_settings.py)，入口`main`、宏生成`render`、归属/退出核对`run`；安全测试：[cst_settings_calibration_test.py](../test/cst_settings_calibration_test.py)。工具是验收探针，尚未接入公共设置验证器。

安装执行文件`AMD64/CST DESIGN ENVIRONMENT_AMD64.exe`文件版本2022,5,0,0。源`model/Pillbox.cst` SHA256为`f3a4673772d576730373a6310b5a10f7ab5ba79dad9014c2540ddb8ab0de1133`。原文件保存版本2020.0不等于本轮执行版本。主要证据`artifacts/settings-calibration-c22dc303`，每次会话保留report.json、session-status.json、states.tsv、expressions.tsv、probe.bas、cst.log及source-check；这些artifact不保证随Git迁移。

先执行16组累积历史设置，每组唯一历史标题和单独Backup；再逐个复制对应快照到独立会话，查询宏不重新设置EigenmodeSolver、不追加历史。快照重开仍包含先前历史，因此属于同一源模型上的顺序变更校准，并非16个独立全新模型。原始参数表在每次宏前后逐项比较名称及表达式，不以数值相等代替表达式相同。

## 主要观察

|探针|实测|判定及限制|
|---|---|---|
|V01 method|Tet Default、General (Lossy)及Hex AKS历史均被接受并保存；GetSolverType均HF Eigenmode；Hex的Mesh.GetMeshType返回PBA|持久命令有证据；active_solver、PBA或模式数不能证明实际算法选择，缺独立method读回|
|V02 target|固定GetFmin=400/GetFmax=1200时依次写启用0、启用480、禁用480；保存历史保留这些差别|证明全局频段不能替代target，尚无独立target读回；不能据模式位置反推设置|
|V03 modes|Default/Tet、General (Lossy)/Tet、AKS/Hex分别SetNumberOfModes 1/2；Solver.AKSGetNumberOfModes当场及重开均分别1/2|本机三个分支的请求模式数查询已校准；不是实际算出模式数，不扩展为所有CST版本/方法保证|
|V04 adaptation|true/false命令被接受、保存；每个case的基础命令先设False，True case再覆盖|开关持久定义有证据，无独立live开关读回或实际自适应行为证据|
|V05 density|legacy 4→6，现代Tet near/far仍10/4；现代显式8/3可读回；新→旧6、旧6→新8/3均8/3|新通道读回有效，但不能建立旧单值到near/far的等价映射，也不能宣称旧命令对最终网格完全无效|
|V06 scope/history|共享读取器在Enlarged分开4个scope，FMF为Frequency Domain、其他Eigenmode；识别Pillbox停用模式数12块；CRC损坏拒绝；损坏JSON与缺失都返回{}|这是现有容器/导航层证据。Reset、条件宏、表达式的最终语义解释器与严格JSON状态仍未实现，不能宣布V06整项通过|

V05的新读回调用为当前项目`GetOwnProject.MeshSettings`对象，先`SetMeshType "Tet"`选择配置分区，再`Get("StepsPerWaveNear"/"StepsPerWaveFar"/"CellsPerWavelengthPolicy")`；本轮以late binding捕获错误。键来自已有CST录制历史，不从语义臆造。选择分区不等于切换活动求解网格，Hex case显示的10/4也是Tet分区值，不能当作Hex密度。此Get尚未在已核查官方帮助找到，应登记为本安装版本实测接口，不能改写为官方跨版本保证。

对保存快照按成员比较：上述method/target/adaptation/density变更对之间，仅Model.mod及Model.bwc有字节差异。Model.mod是保存历史；本轮没有从其他成员找到五项独立设置字段，也不将Model.bwc字节变化猜测为设置。详情member-differences.json。

## V06及诊断边界

`v06-static-probe.py`只在内存构造CRC与JSON异常，未向CST提交改写私有容器。CRC错误明确为Model/3D/Model.mod CRC mismatch；WTC已有simulationproperties成员被内存替换为`{`，宽松simulation()仍返回{}，与Pillbox缺失成员无法区分。3个只读源哈希复核不变。条件宏污点、Reset缺省解析、未知scope拒绝和严格JSON状态仍须公共验证器实施后测试；不把容器基础验证冒充语义验证。

首次受限环境启动在宏执行前退出0xC0000142，日志空、无stage；归属进程全部退出，源哈希未变（settings-calibration-d8f9cf0a）。正常桌面权限相同启动成功（先4组settings-calibration-6b2c352f，再16组）。这是启动环境对照，不归因于设置API或求解失败；没有用终止进程恢复。

## 对设计的约束

1. 可将本安装版本的AKSGetNumberOfModes登记为Default/Tet、General (Lossy)/Tet、AKS/Hex请求数读回候选profile，发布时仍绑定实际执行版本、mesh/method、快照hash和宏hash。
2. Tet新旧通道继续分开表示；禁止把legacy density=n复制成near=n、far=n，禁止按最后文本或总cell数解除歧义。首阶段legacy固定密度路线尚不能因setter有文档就标记ready。
3. MeshSettings.Get可供后续验证器受控接入，不因此创建第二套容器解析器；保留未文档化/版本限定标记。method/target/adaptation仍SETTING_UNVERIFIED，G03未通过。
4. 本轮未求解、未证明网格质量/收敛/实际算法或MCP对话工作流；需要实际求解的V04行为对照仍单独计划。

## V06表达式和Reset补充

`artifacts/settings-calibration-6d669f2a`的独立副本先设置模式数表达式`nmodes+1`、target表达式`fmin*1.2`，显式调用Rebuild并检查返回，再读取AKSGetNumberOfModes=2。随后调用EigenmodeSolver.Reset，无后续模式数setter，查询返回1。原参数名/表达式表前后完全一致；新历史保留表达式。Rebuild成功不证明target的最终live值为480，因为没有该字段独立读回。

Reset=1是当前安装和上下文的观察，不外推全部默认值，也不以此为所有版本填缺省。语义读取器尚未实现，条件宏拒绝仍pending。

## 验收与产物

主批16个保存/重开对的states.tsv逐列一致，所有会话completed、exit=0、归属进程已退出、原参数表达式保持不变；对照汇总reopen-comparison.json。这里核对的是设置查询和标准收尾，不是计算结果成功门禁。静态CRC/JSON异常仅在内存；原源模型哈希复核未变。

离线安全/归属/环境及索引20 passed（2.15s），artifacts/settings-calibration-offline-20261028.xml；最终复查见后续补记。首次pytest默认sandbox临时根无法建目录，改用工作区专属basetemp后通过；此为临时目录权限问题，不是CST错误。


最终补记：V06两组重开查询也与保存前一致，共18组设置/重开对；另一次4组先导会话，总计21个正常关闭会话，1个启动失败会话亦确认退出。所有正常会话参数表达式保持不变，Pillbox原文件SHA256复核不变。最终离线20 passed（2.16s），artifacts/settings-calibration-verified-20261028.xml；diff空白检查通过。没有真实求解，V01/02/04独立字段与V05最终网格、V06完整解释器仍待实施/验收。

清理在全部归属进程退出且未观察到CST运行后进行；仅处理本轮4个明确校准根及3个pytest临时根，删除91个模型副本/配套目录目标。保留轻量report/session/status、宏、TSV日志、保存历史摘录、模型哈希清单、比较报告及静态反例源代码；原始校准.cst与配套数据已删除，重开需用探针重新生成，不能再认为原始快照可访问。清理后D盘余量23.67 GiB，未清理其他任务或系统级CST缓存。

## V05后续实际网格校准

上述设置读回之后，完成[小网格实际网格对照](cst-tet-density-mesh-calibration-20261028.md)：Version=1现代通道生效，旧4/8及混用顺序不改变网格；Version=0在当前求解配置被拒绝。不得将先前“最终网格未验证”继续作为最新结论，也不推广至所有版本/模型。

## V01/V02/V04后续执行读回

新增[实际求解配置与陈旧值校准](cst-solver-settings-readback-calibration-20261028.md)：已得到版本限定执行快照key，但求解前缺失、Save后可陈旧、Rebuild后清除，不能称当前实时getter；target有字符串精度损失。前述未求解仅为首轮批次，最新6次真实尝试与剩余边界见新记录。
