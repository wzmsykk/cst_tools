# GUI完整退出与异常资源清理

2026-10-25实施，替代[退出审计](gui-exit-and-directory-lock-audit.md)描述的旧行为。Task/ACK/VBA协议不变，不修改CST安全门禁，不自动结束未知进程。

## 操作与错误恢复

- **仅关闭界面（保留后台）**：不停止任务或shutdown Runner。丢弃尚未发布的界面排队动作，尽可能取消未开始future；串行等待在途通信及release结束，再关闭本地日志和窗口。release失败记录租约回退，持久停止意图不删除。保留后台时发布目录可能继续被占用。
- **停止任务并退出后台及界面**：活跃任务只发一次停止请求，等待execution_active解除及Worker正常收尾，再shutdown_and_wait核验后台OS所有权释放，最后关闭客户端通信池、本地日志和窗口。空闲/已完成/已知安全FAILED直接退出Runner。等待CST求解不设固定总时间，通信/退出仍有界。
- **取消**：保留现状。

连接未知、其他窗口控制、RECOVERY_REQUIRED、停止或shutdown失败均不宣称完整退出：取消退出意图，主窗口顶部持续显示原因及恢复/申请控制权/仅关闭界面的下一步。该提示独立于阶段快照，不会被轮询覆盖。用户可重新选择仅关闭界面，不被错误永久绑在后台上。当地日志清理失败也保留窗口并允许重试，后台已退出的事实不回滚。

shutdown响应丢失仍核对所有权，不重复启动服务、不强杀。旧Runner需安全停止后更新，不热替换会话代码。服务端RECOVERY_REQUIRED门禁保持，不把逻辑失败简单等同于可以跳过物理安全核验。

## 源码与资源归属

- [MainWindow](../GUI/main_window.py)：_close_runner_window编排各阶段，_finishPendingClose等待下一阶段，_close_local_resources幂等释放本地资源，_exit_failed提供持久反馈。
- [RunnerController](../GUI/runner_controller.py)：shutdown成功发settled唤醒关闭链；detach不再立即让Qt退出，而是停止接收动作、收口在途通信及release后才closed，避免窗口消失而Python等待线程池。
- [LocalExecution](../csttool/runner.py)：构造用ExitStack补偿已建立的日志/概览/Backend资源；正常close中概览发布失败也执行全部资源清理，错误不被当作正常完成。
- [ApplicationLogSession.close](../csttool/logging_config.py)与[Backend.close_logging](../csttool/application_backend.py)：每个handler都尝试移除/关闭；失败保留异常链及可重试状态，不因首个失败跳过其他handler。
- [HomScanAlgorithm](../csttool/hom_scan_algorithm.py)：移除从未写入内容的result.log长期开启，消除start前置检查/恢复失败或准备后停止留下该句柄的路径；get_value读取也改用with，不新增另一份重复日志。

错误反馈采用可复制、换行、有可访问名称的窗口内说明；不依赖自动模态弹窗。本轮offscreen测试曾在QMessageBox展示处触发原生access violation，失败不计通过；改为持久说明后故障路线复验，不据此宣称所有Qt原生崩溃均解决。

## 目录占用与兼容边界

Runner仍以发布根目录为cwd，不能在运行时随意删除它依赖的源码。完整退出释放本应用GUI/Runner的cwd及文件句柄；仅关闭界面有意保留后台占用。

后台管理显示Runner PID/cwd、GUI PID/cwd、启动父进程PID和终端目录提示。Runner HTTP快照runtime新增可选cwd，读取失败为null；旧后台缺字段显示未知。没有枚举或结束其他用户进程。

若用户自己打开的cmd/PowerShell仍停留在发布目录，应用退出后终端仍可能占用，需要cd到其他目录或关闭空闲终端。应用不能改变父进程cwd，不能以杀终端代替CST收尾。Windows cmd /c的临时启动链由测试验证会随正常Python退出自然结束；不承诺结束外部交互终端。

## 测试

[资源测试](../test/exit_resources_test.py)：真实非法INI、HOM已有检查点前置拒绝、概览/Backend清理异常、单handler关闭异常，核验Python仍存活时日志可重命名/删除。

[GUI测试](../test/gui_runner_test.py)：空闲/FAILED/运行中完整退出、重复关闭、服务关闭失败、未知/只读/需要恢复、仅断开、尚未发布start取消、本地日志关闭失败重试。日志恢复测试同步等待通信真正结束后再接受重复close。

[进程测试](../test/exit_process_test.py)通过[真实Qt探针](../test/support/exit_gui_probe.py)运行独立GUI和Runner Python，执行器明确为fake，绝不启动CST。覆盖空闲、运行中、实际假Worker失败、仅关界面、shutdown HTTP响应丢失、Windows cmd /c启动链。退出前目录重命名被cwd阻止；完整退出后GUI/Runner自然结束且目录可重命名/删除。仅关GUI后Runner存活并占用，正常shutdown后释放。所有测试服务正常退出，不kill。

最终数字、轻量报告与清理结果见current-status；artifacts不保证随Git迁移。此真实GUI/Runner进程验收不等同真实CST故障收尾或现场桌面视觉验收，后两者仍需后续串行副本/人工补验。

本轮最终离线797 passed、21 integration deselected（107.89s），主窗口另34 passed（1.34s），最终文档/日志索引及资源专项8 passed（2.37s，重叠）。汇总artifacts/gui-exit-fix-20261025/summary.json，原始XML为artifacts/gui-exit-offline-final-20261025.xml和artifacts/exit-main-20261025.xml；六例GUI/Runner日志及退出事实已另留轻量副本。

已清理本轮.pytest-exit-*目录（只读测试夹具用原生Force删除，先核实任务结束和绝对路径，不终止进程），保留成功/失败轻量记录。offscreen截图字体集合为0、未绘制文本；受限及正常用户权限均如此，不能以此宣称现场视觉通过，记录visual-boundary.json。
