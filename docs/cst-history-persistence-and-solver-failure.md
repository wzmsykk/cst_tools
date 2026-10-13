# CST历史持久性边界与真实求解失败对照

日期：2026-10-13。版本：CST2022.5。原工程只读，全部测试使用新副本；没有强制结束进程。

## 文档定义

安装帮助的EigenmodeSolver Object明确：Start完成成功返回1，失败返回0；GetNumberOfModesCalculated是结果中实际算出的数量，可能少于请求数，应在查询前读取。不能以少于nmodes直接判失败。

Eigenmode Solver Overview明确Default/Tet不支持开放边界，这类边界需General (Lossy)。Boundary Object列出Xmax及GetXmax等设置和查询方法。由此选取“有效模型＋Default/Tet＋open边界”作为求解器拒绝条件，而不是无模式区间、资源耗尽或杀进程。

Project Object定义：Rebuild重放History List并删除结果；RebuildOnParametricChange(False,False)只更新受影响的块，True则完整重放；AddToHistory立即执行内容并保存为历史块，返回Boolean。相邻同caption会替换旧块，因此应检查返回值，不能把caption当作全局唯一的更新接口。

Project参数由StoreParameter/StoreDoubleParameter等单独维护。Global Data的标准参数依赖及结果失效机制不适用，文档明确警告可能产生难以发现的不一致，应优先使用项目参数。

依据（本地安装版）：

- `Online Help/mergedProjects/VBA_3D/special_vbasolver/special_vbasolver_eigenmodesolver_object.htm`
- `Online Help/mergedProjects/3D/special_overview/special_overview_eigenmodesolverover.htm`
- `Online Help/mergedProjects/VBA_3D/special_vbasolver/special_vbasolver_boundary_object.htm`
- `Online Help/mergedProjects/VBA_3D/common_vbaapp/common_vbaappapplication_object.htm`
- `Online Help/mergedProjects/3D/common_macro/common_macro_history_list.htm`

## 持久性实测

探针：`test/support/validate_history_persistence.py`。证据：`artifacts/history-persistence-18ad6d40/report.json`及states.tsv。完成标记、退出0、所属进程退出和源哈希不变通过；没有运行Solver。

|状态|Xmax|Gap|concaveL表达式/数值|新参数probe_boundary|Global Data|
|---|---|---|---|---|---|
|初始|electric|150|(Leq-Gap)/2 / 55|不存在|initial|
|直接setter及StoreParameter|open|140|同表达式 / 60|1|kept|
|完整Rebuild|electric|140|同表达式 / 60|1|kept|
|AddToHistory后|open|140|同表达式 / 60|1|kept|
|历史完整Rebuild|open|140|同表达式 / 60|1|kept|
|Gap恢复150＋部分参数更新|open|150|同表达式 / 55|1|kept|
|完整参数更新|open|150|同表达式 / 55|1|kept|
|历史恢复原边界＋Rebuild|electric|150|同表达式 / 55|1|kept|

因此直接边界修改的即时有效不等于可重建。项目参数在本例不需要把每次数值变化也追加到历史；应让历史引用参数，避免每任务追加固化数字、覆盖后续扫描值。Global Data保留不意味着几何和结果自动刷新，不能用它绕过参数失效机制。

### 对本项目的边界划分

|修改类型|处理策略与证据边界|
|---|---|
|几何、边界、网格及求解器设置，需在重建后保持|进入历史或由稳定历史引用参数；本轮直接验证边界，其他设置须逐项确认，不能只凭同属设置推断|
|已有项目参数的值和表达式|StoreParameter维护参数表；历史使用参数名/读取当前参数值，不写死结果。本轮Gap及新参数均保留，concave表达式未扁平化|
|全局数据|独立存储，本轮Rebuild/参数更新保留；不自动失效结果，不推荐作为扫描计算参数|
|后处理积分位置、采样和导出选项|本项目运行时函数参数/导出配置，不等同于结构历史；需要结果存在，重建删除结果后不能继续假定可用。各导出对象的保存/重置范围仍需另测|
|Result Template定义与生成结果|定义是否进入历史、是否随参数重算与旧结果是否保留是不同问题；本轮没有新证据，不能概括为“永远保留”|
|脚本变量、任务文件及Python配置|属于会话或框架状态，不因保存.cst就自动成为可重建工程设置|

上述验证覆盖完整Rebuild及两种RebuildOnParametricChange，不声称逐按钮完成GUI测试，也未验证所有设置的跨保存/重开持久性。

## 失败分类及已发现的问题

Managed新增solver-config、solver-start、solver-result阶段；记录调用Start及实际返回值。配置异常不再归为Start异常；Rebuild异常与返回False都归REBUILD_FAILED。协议仍沿用已有错误码，通过阶段与详细描述区分，不新增跨语言枚举。

|证据|真实发生的事件|判定|
|---|---|---|
|solver-failure-recovery-5c962473|nmodes=0在历史SetNumberOfModes处使Rebuild返回False；未进入Start；立即关闭时保存拒绝，退出4|重建失败；不能宣称安全保存退出通过。源未变、实际进程退出，未强杀|
|solver-failure-recovery-420778d0|同样重建失败后有效参数可恢复求解；早期open探针回读magnetic，最终求解成功|失败触发无效，不作为Solver失败证据；正常StopAck/退出0|
|solver-failure-recovery-4d229e05|Xmax=open回读通过；日志明确不支持open边界，但Start返回1；查询结果报无Eigenmode数据库，发布后处理失败|真实求解器拒绝，返回值与文档契约不一致；不是Start返回0，也不是Start抛异常|
|同一4d229e05会话后续任务|恢复electric、有效nmodes=1，成功读到频率，StopAck、退出0、源不变、无已知关闭错误|重建失败及求解器拒绝后可在同Worker恢复|

当前不能证明早期probe_open_boundary数值判断为何未触发；后续直接使用任务协议中的探针开关并回读实际边界，避免将未生效的设置算故障。不把它臆断成StoreParameter在Rebuild后丢失，本轮独立持久性探针反而验证新参数保留。

4d229e05恢复会话通过，但仍暴露漏洞：Start返回1之后若不需要任何标量后处理，可能没有查询到失败。生产Managed因此增加solver-result门禁：查询实际模式数，少于1或查询抛异常发布SOLVER_FAILED；模式数少于请求数但大于0仍允许继续。此门禁的真实重跑结果另列，不能用旧探针追认新代码验收。

## 最新历史化故障对照

证据：`artifacts/solver-failure-recovery-7eede591/report.json`。边界故障与恢复均通过AddToHistory写入副本，回读通过后才调用真实Start；采用新增solver-result门禁。

- 同一session：e951d44a-0d8c-4d01-b215-8f6bca2750d3。
- nmodes=0：REBUILD_FAILED，正确分类重建失败，正常Ack。
- Default/Tet+open：SOLVER_FAILED，`solver-result failed ... No Eigenmode results ...`；Start返回1但无结果，未发布后处理值或成功快照。
- 恢复原electric边界：Success，频率570.124959420424MHz，有成功快照；不重启Worker。
- stop_returned、StopAck、源未变均True，exit_code=0，已知收尾错误列表为空；提升权限最终只读检查无CST主实例、Modeler/Solver残留。
- 最新完整离线427通过、19排除（9.76秒）。实现和文档尚未提交。

新增solver-result门禁本例真实通过；参数/设置错误独立分类有离线覆盖，但本轮非法nmodes在历史阶段被拒绝，不能追认其为“参数设置异常”实测。坏重建后未恢复即关闭的退出4仍是单独的未修复边界。

Start返回0、Start本身抛异常两项仍需独立证据；不能把无结果查询异常或日志ERROR冒充这两个分支。正常求解总时长无限等待，启动/通信/退出仍有保护边界。
