# L4 Runner / GUI 生命周期事实与诊断

L5真实Controller退出发现终态标签可能早于线程释放。HTTP快照增加execution_active，GUI保持收尾状态；关闭确认不由GUI标签推断，见[六类验收](controller-exit-l5-acceptance.md)。

L5真实停止/ACK补验修复：Completion清理后，当前任务未采用的成功received/acknowledged也进入恢复发现；显示received-result-not-reconciled而非伪称Completion存在，result_state为received-unadopted。标准进程关闭仍可独立为confirmed-closed，详见[真实记录](stop-ack-l5-acceptance.md)。

2026-10-24：源码接入；未执行真实CST或WinWrap，不代表L5通过。

## 事实传播

`LocalExecution.lifecycle_facts`读取Managed会话，共用L1–L3的`evaluate_closure`。
Runner在原生进度事件中最多每5秒采集一次，并在执行及日志收尾后再采集一次；无进度事件期间不承诺实时刷新。
HTTP/持久`control/status.json`及运行outcome增加`lifecycle`（schema_version=1），GUI透传，不解释日志文字推断成功。
重连可读取旧观测；Runner重启标为historical并显示UTC观测时间，不能当当前进程探测。
新开始/恢复清除旧运行诊断，覆盖范围和模式数不由该诊断接口重置。

每会话分别含任务结果、模型状态、进程状态、退出码及分类、标准收尾、处置、缺证据、工作区和回执/退出观测路径。
路径是定位入口，可能尚不存在，不表示已验证产物可用。所有会话参与汇总，HTTP详情最多100项，待恢复优先，显示省略数量。
采集遍历会话但不读大场、不算产物哈希，也不在GUI线程执行进程探测。

`session_safety`值：unknown（存在未知进程）、running（存在运行进程且无未知）、confirmed-closed（所有会话标准关闭，或无Managed会话）、exited-unverified（已退出但标准收尾未确认）。
预处理另行检查，未确认退出时强制unknown。项目RECOVERY_REQUIRED与该物理安全摘要独立；进程标准关闭但Completion未对账仍须恢复。
显式放弃的死会话可以不再需恢复，但不会被展示为标准退出。退出1仍拒绝。

Python结果登记显示最新任务receipt的received / acknowledged / algorithm_adopted，验证task/session身份后仅作登记观测。
这不是快照哈希、后处理或采用条件的重新验收；不会ACK、导入、重复采用、恢复或修改HOM覆盖。无可靠证据显示unknown，缺receipt显示not-received。

## 异常与界面

Runner保留`error_diagnostic`，包括最多16层异常原因与每层最后16个源码位置；cleanup_diagnostic单独保存，不覆盖首个原因链。
GUI错误提示显示最内层原因及源码，后台管理窗口显示完整链与收尾事实，沿用只读可选中文本、滚动及原日志入口。
旧Runner没有新字段时显示尚未采集，不伪造安全状态。新字段为增量兼容，不热更新运行中旧后台。
采集失败显示unknown和采集原因，原有项目恢复/停止门禁不因展示字段而清除。

## 验收入口与限制

[事实及诊断测试](../test/lifecycle_diagnostics_test.py)、[GUI管理测试](../test/gui_runner_test.py)、[Runner测试](../test/runner_test.py)、[恢复测试](../test/runner_recovery_test.py)。
覆盖标准关闭但待对账、异常退出、未知/活跃、异常链跨JSON、登记只读、GUI详情和持久Runner结果。
本轮准确测试数字见current-status；测试假进程/假执行器不证明真实CST关闭、现场GUI视觉或WWB行为。

本轮离线回归724 passed、21 deselected，主窗口独立34 passed；最后增补专项40 passed（重叠）。全仓采集先于最后三项新增测试，新增内容由专项覆盖，不合并为最终全仓计数。XML在artifacts/close-l4-{offline,window,focused}-20261024.xml，不保证随Git迁移。早期首个新增测试因直接调用Runner._execute而未建立StopIntent失败，修正测试夹具后通过；未用修改生产逻辑掩盖该失败。
后续L5需串行副本及真实阶段故障矩阵，不启动原工程、不强杀。
