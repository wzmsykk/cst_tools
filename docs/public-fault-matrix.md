# 公共链故障矩阵与协议覆盖

更新：2026-11-03。覆盖G03/G04/G08及N01–N25的登记入口。桌面正常链见[实际记录](codex-desktop-acceptance-20261103.md)；本批新增故障均为离线注入，没有启动真实CST。故障注入的FakeWorker不证明CST会自然发生同一错误。

## 执行链矩阵

|边界|本批或既有可执行测试|必须保持的行为|
|---|---|---|
|G03保存/重开、nonce/设置/表达式/重复字段错误、退出未确认|definition_verifier_test、winwrap_publication_fault_test|不发布ready、不启动下一会话、不重放失败编辑|
|G04求解失败、频率或R/Q缺失|public_failure_matrix_test的failed_or_incomplete_result|不发布成功结果；已派发意图不能当成可重试新任务|
|接收前、完成已写、ACK已发但未确认、错误会话|public_failure_matrix_test的ack_not_confirmed；ack_state_machine_test|不凭完成或ACK文件存在放行；不再次派发Solver|
|ACK后写simulation-received失败|public_failure_matrix_test的controller_write_gap|缺持久接收证据，重建服务后保持待对账，不猜测补数据|
|标准关闭后写closure失败|同上|缺关闭记录不发布；不能因进程已死编造收尾证据|
|采集已完成、结果发布前写入失败|同上|新服务可依据完整档案修复；首次及再次返回一致result_revision，采用日志不重复|
|结果已发布、采用receipt未写|single_adoption_recovery_test|核验任务/会话/值/快照后补写，不改结果、不重算|
|原生receipt/snapshot/DB缺失或DB损坏、nonce/项目/定义串用|public_failure_matrix_test的archived_capture_gap|连续两次恢复均拒绝，事件日志不变，不创建Worker|
|G08停止超时/进程已退出但回执不足|winwrap_publication_fault_test、ack_shutdown_contract_test|安全状态unknown/待恢复；不用强杀替代标准退出|
|GUI/MCP客户端退出、Runner退出或重启|runner_test的killed_gui_client、real_qt_gui_process_crash、runner_crash；mcp_sdk_test的stdio EOF|客户端退出不停止独立任务；Runner重启先恢复，不重新计算|

“重建服务”测试只销毁Python业务对象并从磁盘恢复，注入写入失败后finally仍执行，**不等于进程被杀**。Runner子进程崩溃测试是独立的假任务证据；真实CST各阶段OS崩溃仍未验。ACK阶段名在新测试中用于构造未确认的回执，不冒充真实VBA时序；真实时序探针及旧证据继续由stop_ack_l5_test和对应有日期记录限定。

## N01–N25逐项覆盖与缺口

本表沿用[原规范映射](mcp-protocol-conformance.md)编号，不修改或重新认证外部标准。局部测试通过不能把整项标为符合。

|编号|已有/本批证据|仍未覆盖或首版范围|
|---|---|---|
|N01|SDK正常请求/重试业务ID路径|非法JSON、nullID、重复在途RPC ID、通知回复完整矩阵|
|N02|modern SDK与旧模式拒绝测试|缺version/capabilities及交错能力完整矩阵|
|N03|真实stdio自动发现|原始wire无需初始化的全部发现错误路径|
|N04|SDK成功/输入错误均核对complete|所有结果与错误分支|
|N05|stdio发现/EOF；内存SDK中文、反斜线、换行往返|中文wire逐字节、启动/异常stdout污染专项|
|N06|stdio EOF；独立Runner与假GUI客户端死亡测试|实际CST计算时宿主进程死亡组合|
|N07|14工具排序；错误前后目录稳定|不同服务授权配置矩阵|
|N08|目录private、ttl=0|全部可缓存响应的规范矩阵|
|N09|未知字段、错误类型和脚本注入零业务派发|复杂Schema预算/网络ref全矩阵|
|N10|结构化正常值/中文往返；服务非有限值拒绝|所有输出Schema/错误DTO完整性|
|N11|错误输入/无效句柄与后续正常调用|所有协议错误码与工具错误分层|
|N12|独立任务不因客户端退出取消的假任务证据|协议取消前后竞态、无后续进度/响应|
|N13|首版读取业务status，不将CST局部进度等同协议progress|token生命周期专项|
|N14|首版有界14工具目录|不透明游标、空cursor及更新竞态|
|N15|句柄重启失效、租约与Runner唯一性测试|全部跨实例/交错主体矩阵|
|N16|句柄上限、严格输入；既有路径安全测试|junction、限流并发和所有传递副作用全矩阵|
|N17|工具注解与服务控制权分离|全部注解与权限组合|
|N18|不主动产生input_required|MRTR扩展未启用，未来单独验收|
|N19|tools-only，不声明订阅|订阅未启用，未来另验|
|N20|SDK资源方法被拒绝，导出为本地工件|远程资源下载/提示/补全未提供|
|N21|非首版|MCP Streamable HTTP未实现；Runner内部HTTP不能算作它|
|N22|stdio依赖OS/配置边界|HTTP OAuth未实现|
|N23|不声明Tasks扩展，Runner run_id仍为业务ID|协议Tasks未实现|
|N24|响应丢失/幂等、租约、重启、重复恢复无重算的服务/Runner测试|真实发布边界控制器退出已验；实际求解中生产Runner退出及协议取消组合未验|
|N25|本批ACK/关闭/采集缺口拒绝、采用补写与桌面正常实测|15个受支持真实场景已验；未覆盖Start=0/Start异常、HOM前沿组合与全部真实故障|

## API修正与剩余验收

首次`reconcile_simulation`修复结果发布缺口后，现在同后续查询一样返回带`result_revision`的公共DTO；不改已持久结果格式，也不增加重算/自动重试。源数据不齐仍拒绝。测试定位见[新增故障测试](../test/public_failure_matrix_test.py)、[SDK测试](../test/mcp_sdk_test.py)。

现已接入[串行真实注入驱动](public-fault-injection.md)，将ACK闸点与公共控制器退出分层验收；只按对应实际报告升级覆盖，求解中生产Runner进程退出仍未由发布边界测试证明。本轮15例真实注入通过、22个原生会话标准关闭，详见[驱动验收](public-fault-injection.md)。完整N01–N25仍为部分覆盖，不能因本表登记完整而宣称符合。轻量报告写入知识库；artifacts临时模型可清理且不保证随Git迁移。

## 离线批次执行结果

新增19项服务故障测试；相关服务/G03/ACK/Runner/采集组合123项通过（83.40s），专用MCP运行环境8项SDK测试通过（3.65s）。集合各自报告，不当作全仓测试。见[轻量记录](../knowledge-base/public-fault-matrix-20261103.json)；该离线批次未运行真实CST；后续真实证据由串行驱动记录。
