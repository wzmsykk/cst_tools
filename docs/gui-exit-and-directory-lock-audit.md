# GUI退出、异常收尾与发布目录占用审计

2026-10-25，源码基线e8a5b22。用户现象是发布包解压后的运行目录在GUI关闭后仍被占用，关闭控制台后才释放。本轮只审计与复现，不修改生产退出行为，不启动CST，不结束用户进程。

后续修正已实施：[现行退出契约与清理](gui-exit-resource-cleanup.md)。下文保留e8a5b22时的审计事实和当时未完成项，不作为修正后接口定义。

## 结论

关闭GUI、停止计算、退出Runner、退出启动控制台是四个不同动作。当前实现保证了部分任务安全边界，却没有在退出用语和交互中完整区分这四件事。尤其“安全停止后退出”实际不退出Runner，用户容易理解为整个程序已经退出。

发布目录被占用，首要检查进程当前目录，而不是先怀疑CST未释放.cst。RunnerClient.connect明确用源码/发布根目录作为子进程cwd；win.bat只是`python gui_app.py`，没有控制台目录迁移或独立生命周期说明。仍在发布目录中的Runner、GUI Python、cmd/PowerShell都可能阻止目录删除。

这并不证明用户现场唯一占用者就是Runner：尚未拿到现场PID/句柄清单。关闭控制台可能使GUI Python或相关进程退出，也可能只是释放shell自身当前目录。应先区分占用者，不能通过关闭控制台推断已完成CST正常收尾。

## 当前调用链及直观一致性

|场景/选择|实际调用与效果|是否符合直觉|
|---|---|---|
|仅关闭界面，后台继续|MainWindow.closeEvent → RunnerController.detach：停止轮询、排队release、停止线程池接收新任务；Runner/CST不停止|运行中合理；空闲或失败时“后台继续”表述过泛，未说明仍占用发布目录|
|安全停止后退出，正在运行|request_stop → 持久停止意图/HTTP stop → Runner/Backend → Manager.stop → Worker协作停止和协议收尾；settled后再次close|等待CST收尾正确；完成后仅detach，没有Runner shutdown，与“退出整个程序”的理解有差距|
|安全停止后退出，已完成/FAILED且安全|不再停止任务，关闭GUI本地日志并detach；独立Runner保持空闲运行|错误消失不等于服务退出，仍可占用目录|
|安全停止过程中收尾失败|Runner变RECOVERY_REQUIRED，GUI再次close被拒绝；仅状态栏/日志说明先恢复，需重新关闭后显式选择仅关闭界面|保护未明会话正确，但退出意图失败的反馈不够直接，容易被认为退出失灵|
|RECOVERY_REQUIRED后仅关闭界面|允许detach，保留后台事实；不声称任务停止|必要且合理；不能以GUI退出作为CST安全关闭证明|
|后台管理→退出后台|request_shutdown → shutdown_and_wait；要求无活跃工作、非RECOVERY_REQUIRED、控制权可用；等待OS所有权锁释放|这是当前真正退出Runner的入口，隐藏在另一操作中，与主窗口退出割裂|
|状态未知/失联时安全退出|不能确认停止；连接/控制权门禁可能拒绝，仍可选择仅关闭界面|保护合理，错误应明确“未退出哪些进程/可采取什么动作”|

源码入口：

- [MainWindow.closeEvent、_runner_close_choice、_finishPendingClose](../GUI/main_window.py)。
- [RunnerController.request_stop、request_shutdown、detach](../GUI/runner_controller.py)。
- [后台管理按钮与确认](../GUI/runner_management_dialog.py)。
- [Runner._execute、command、LocalExecution.close](../csttool/runner.py)。
- [CstApplicationBackend.execute_run](../csttool/application_backend.py)的finally负责停止Manager及释放项目运行锁；[CSTManager.stop](../csttool/cstmanager.py)停止各Worker、等待执行池并报告错误，不用杀CST代替收尾。
- [RunnerClient.connect、shutdown_and_wait](../csttool/runner_client.py)显式设置发布目录cwd，关闭时核对RunnerOwnership释放；[win.bat](../win.bat)仅调用Python。

## Windows受控复现

轻量证据：`artifacts/gui-exit-audit-20261025/report.json`。使用独立Python子进程，通过stdin协作正常返回；不杀进程。测试目录均位于本轮artifacts内，探针目录随后删除。

|对照|进程存活时|正常释放后|证明范围|
|---|---|---|---|
|子进程cwd=空测试目录，没有打开普通文件|删除目录报WinError32|子进程正常退出后可删除|当前目录本身即可造成目录占用|
|FileHandler持有单个日志，cwd在别处|删除日志报WinError32|handler.close后即可删除，此时Python仍存活|日志句柄与进程当前目录是独立原因|
|ThreadPoolExecutor有运行中future，shutdown(wait=False)后主程序返回|Python仍存活，cwd目录不可删除|约3秒任务完成后Python自行退出，目录可删除|wait=False不保证解释器立即退出；不是GUI现场卡死复现|

RunnerController.detach使用shutdown(wait=False,cancel_futures=False)。已经运行的观察请求、排队动作及release可能继续执行，Python退出仍会等待线程。观察路径含connect（启动等待默认15秒）和有界HTTP请求；不能把GUI窗口消失当作Python PID已消失。当前没有独立的“GUI本地清理已完成”确认阶段。

本机进程快照只看到审计命令本身的PowerShell/Python以工作区为cwd，没有取得用户现场发布包进程证据。进程open_files清单不一定包含目录句柄，空清单不足以排除cwd占用。

## 两个已复现的异常资源缺口

1. **LocalExecution构造失败**。__init__先创建ApplicationLogSession并把handlers注册到全局logging，再构造GlobalConfigManager/Backend。真实非法current.ini触发MissingSectionHeaderError；Runner._execute尚未得到executor赋值，finally不会调用其close。实测application.log和application.jsonl仍打开，删除报WinError32；正常关闭这些handlers后释放。日志延迟打开：直接在任何日志产生前注入异常不会得到同样占用，不能泛化为所有构造失败必然占用。证据`real-invalid-config-resources.json`。
2. **HOM开始前失败/未进入start**。set_job_manager立即打开result.log；start的ready/已有检查点/manifest/恢复快照检查位于关闭日志的try/finally之前。已有检查点且非resume时实际抛错，log仍打开，删除报WinError32。准备完后、start前收到停止也有同类生命周期风险。该文件没有实际写入用途（仅open/close），宜删除这种无用长生命周期句柄，或统一由显式算法close管理。证据`exception-resources.json`。

这两个缺口直接占用的是项目日志，不能把它们直接当作发布根目录被锁的唯一原因。当前LocalExecution.close也缺少算法资源关闭；其overview.update抛错时，backend.close_logging会被跳过，虽然外层finally仍关闭主日志，应一并纳入异常清理设计。

## 建议的退出契约与修正顺序（尚未实施）

1. 主窗口明确区分“仅关闭界面，保留后台”和“停止任务并退出后台及界面”；取消单列。空闲/FAILED且安全时，完整退出应直接走有界shutdown_and_wait；运行中先stop、确认execution_active=False及安全门禁，再shutdown，再关闭本地GUI。不能继续把stop称为整个程序退出。
2. 出错时按事实处理：已知安全失败可以完整退出；未知/活跃CST不能宣称安全退出，显示保留的进程/会话/日志路径，提供重新恢复和仅关闭界面。完整退出失败应显式显示哪一步失败，不能仅闪过状态栏或持续隐式重试。逻辑对账失败与CST仍运行应分开；任何放宽Runner shutdown的规则必须另有安全测试，不能仅删除RECOVERY_REQUIRED门禁。
3. 资源收尾覆盖部分构造、准备失败、算法前置检查失败、停止及重复关闭。构造采用try/except补偿或ExitStack；清理步骤独立try/finally，保持首异常并附加清理异常。关闭不需要的result.log，GUI所有选择统一关闭其本地handlers，绝不关闭仍运行Runner的日志。
4. GUI detach应取消尚未开始且未授权保留的观察/排队动作，处理running future/release失败，保留已持久化的停止意图；不通过强杀解决线程等待。需子进程实测“窗口消失→Python PID退出”的上界。
5. 发布程序更新/删除前确认Runner已退出，并让启动shell离开发布目录（cd到外部目录或关闭空闲shell）。若未来使用中性cwd，应同时处理源目录导入和懒加载，不能让运行中Runner依赖可随意删除的源码包。不要把chdir当作后台安全退出的替代品。

验收补充：RUNNING/FAILED安全/RECOVERY_REQUIRED/连接未知/停止失败/服务关闭响应丢失/多窗口只读/重复close；分别检查窗口、GUI PID、Runner PID、CST状态、控制权、cwd和可删除性。GUI/offscreen测试与实际Windows目录句柄测试分开计证，完整CST故障关闭仍需后续串行副本验收。

本轮既有GUI Runner/Runner进程/文档与日志索引回归28 passed（39.91s），报告artifacts/gui-exit-audit-20261025/regression.xml。该回归不表示上述未实施修正已通过；没有新增真实CST或现场GUI退出验收。pytest临时目录结束后清理，原有无关修改保持不变。
