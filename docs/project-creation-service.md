# G02空工程创建与文档事务首子集

日期：2026-11-02。已接入公共ApplicationService、既有Runner异步执行槽及MCP适配器，不新建调度框架。本篇记录空工程创建子集；后续已接入[类型化建模/配置/save/close事务](typed-definition-service.md)，空文档仍不能直接仿真。

## 公共入口

- MCP `list_installations()`只读后台授权安装引用；不接受客户端任意exe路径。
- MCP `create_project(control_handle,name,installation_ref,request_id)`固定MWS/mm/MHz，返回既有命令受理回执run_id；需控制租约，request_id复用用于响应丢失。正常工具不会同步等待整个CST过程。
- `get_operation_result(run_id)`读取创建结果，未发布返回OPERATION_NOT_READY；`inspect_model(document_id,document_revision)`只读不可变源/元数据并核对hash，不启动CST。
- 底层提交为 `kind=definition, operation=create_project, name, installation_ref, module=mws, units={length:mm,frequency:MHz}`；未知字段拒绝。由同一Runner start槽执行，停止/恢复/状态沿用既有控制链。
- HTTP只读路径：/installations、/definition-result?run_id=...、/model?document_id=...&document_revision=...；沿用Bearer和client_id验证。GUI/CLI尚未增加完整建模操作界面。

## 真实CST通道与作用域

使用所选CST2022安装的AMD64/python/python.exe及python_cst_libraries，隔离现代MCP Python与旧扩展ABI。Bridge仅接收服务器生成的目录/库路径/nonce，调用文档定义的DesignEnvironment.new()、pid()、new_mws()、Project.modeler.add_to_history、save(include_results=False)、Project.close及DE.close。保存后才关闭；不连接any/active，不使用全局OLE Active3D，不开放任意脚本输入，不求解。

安装版Python帮助明确new()启动quiet/script模式；quiet不等于所有窗口都不存在。单位设置进入模型历史。空工程只核对该受控生成单位块保存成功，不向完整B2投影填造缺失solver/几何，不把它当完整G03。文档状态empty、ready=false，后续仍须typed建模/配置与G03。

通过官方de.pid()得到实例PID，桥接进程等待owner绑定nonce后才new_mws/save；现代父进程核对PID、创建时间及exe位于所选安装目录，将其作为bound_roots纳入公共wait_probe。中断时可由现有定义会话事实/恢复观察；不能按裸PID结束进程。Python/Qt环境分离并保留许可证环境。普通创建/通信/退出有界，无Solver总超时问题。

## 发布、幂等、错误和恢复

同一ProjectRunLock覆盖创建事务。先写control/runs/<operation>/definition-intent，再创建新的受控候选，验证源CST与正常退出，最后保存control/documents/<id>/<revision>.json、current及名称登记。revision绑定document/project/name/安装引用/单位/空状态/源SHA256。旧源文件、已发布版本不覆盖，重名DOCUMENT_EXISTS；同operation不同payload返回REQUEST_CONFLICT。

同请求重放读取已发布结果，不再次new_mws。失败前有意图则同operation不能盲目重做，副本/日志保留。已提交名称/文档但最终definition-result写入失败时，reconcile_project_creation只核对既有文档/关闭事实并补写，绝不重复创建。未发布候选继续明确保留并阻断该操作，不自动将失败候选提升为可用文档。恢复暂停不丢弃证据。

停止为合作意图：原生启动前/正常关闭后的检查点响应；不承诺强行打断native new/save调用。停止期间创建好的未发布副本保留。MCP适配器刷新不会主动停止独立Runner/CST，但当前适配进程的控制句柄失效，需要重新连接。

## 验收

[真实轻量证据](../knowledge-base/cst-project-bootstrap-g02-20261102.json)：artifacts/project-create-9cfc72e4；官方CST2022自带Python新建、单位历史保存、close/退出核验、源只读检查及重放一致；0次Solver。该条为当时owner API/原生bootstrap证据；后续当前桌面九工具create/inspect已通过，见最新类型化验收。候选和原始日志在artifacts，不保证随Git迁移。

离线测试覆盖重复操作、冲突/重名/路径与未知字段、失败保留、不可变检查、提交后的发布缺口补写、同Runner槽及带认证HTTP读取。首批目录9项是原5项加4个创建/检查辅助工具；当前源码已扩展为14项，新增完整typed操作见当前服务。

后续：typed参数/几何/配置/G03发布与关闭已实现，见当前服务；通用结构inspect、指定桌面整链仍待验；首阶段单圆柱的原生材质/体积/盒/边界和SDK真实计算已经通过。当前Codex九工具创建/检查已通过，不能扩展成新增五工具已在宿主调用。

最终扩展回归96 passed（63.46秒，artifacts/g02-final-20261102.xml）；阶段诊断修改后22项定向复验通过（4.34秒，g02-stage-20261102.xml）；官方SDK/stdio5项另验。阶段现在分别上报create-environment/new-mws/units-history/save/project-close/de-close，仅阶段变化才更新状态，不刷重复日志。集合重叠且代码时点不同，不相加。

创建会话在生命周期中独立标记为G02，标准关闭时显示saved-empty-project，未确认时显示candidate-state-unknown，不冒充冻结定义G03。最后展示/身份/索引复验12 passed（1.93秒，g02-display-20261102.xml）。

## 原生后台启动补充

Windows2022默认原生new(options=["-i"])在临时非活动桌面执行，nonce/PID/安装核验后set_quiet_mode并读回，再创建MWS。进程/桌面资源正常释放，窗口诊断写入候选目录；见[后台验收](cst-background-acceptance-20261103.md)。这不是Linux gui_linux或真正headless；不修改外部API，不静默回退到用户桌面。
