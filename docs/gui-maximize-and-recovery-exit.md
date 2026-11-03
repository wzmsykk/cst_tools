# 最大化布局和待恢复状态退出修正

> 适用性复审（2026-11-03）：原批次实施/故障/验收记录；旧当前、未提交、待做及现场进程状态不代表本次实时事实。现行实现见[当前状态](current-status.md)、[功能索引](feature-index.md)及对应API；不重算或追认旧证据。

2026-11-02。现场截图中顶部退出错误提示占据大块空白，工作区被挤至下半部；完整退出又被RECOVERY_REQUIRED无条件拒绝。本批修复这两个代码问题，未宣称现场所有恢复失败原因已查明。

## 布局根因与修正

MainWindow在pageLayout索引1插入exitFailureLabel后，仍对索引1设置stretch=1，因此错误提示被分配剩余高度。改为indexOf(workspaceSplitter)选择实际工作区；错误标签使用Maximum垂直sizePolicy、wordWrap和自然文本高度。错误仍持续可见，不因tab或状态轮询消失。

几何测试在1480×920、2048×1200及回缩中切换两个tab，验证工作区伸展=1、错误标签=0、短提示小于100像素且工作区超过中央高度65%。这是尺寸/布局检查；实际桌面最大化、混合DPI与字体仍需现场确认。offscreen两页截图保留于artifacts/gui-layout-20261102，字体未被绘制，只支持布局几何观察，不计完整视觉验收。

## 完整退出的边界

待恢复表示项目或结果需要对账，不必然表示还有CST进程。移除MainWindow、RunnerController、后台管理按钮及Runner对RECOVERY_REQUIRED的无条件拦截。GUI允许请求正常退出，由Runner在命令处理锁内重新读取Managed会话的物理状态及预处理进程身份；运行线程/停止投递仍活跃时仍拒绝。

所有项目CST会话均已确认exited，且预处理没有未确认的活进程/未知记录时，可退出空闲Runner并关闭界面，即便采用记录、未完成启动意图或检查点尚需恢复。退出不执行结果对账、不启动求解、不改变项目INI、检查点、确认结果和恢复标记；下次打开仍需恢复。丢失正常退出证明的已知exited会话不因此伪装成标准关闭，逻辑标记保留。

任一会话running/unknown、身份不明、文件不可读或预处理安全不明则拒绝完整退出，显示具体会话/归属原因；可以重新核实或仅关闭界面保留后台。仅关闭界面仍不表示后台退出或发布目录释放。不强杀、不伪造成功、不删除证据。预处理检查复用同一函数preprocessor_recovery_required，按项目配置解析runtime目录；缺owned的未确认报告显式拒绝。

## 实现与验收

MainWindow.__init__修布局、_close_runner_window编排；RunnerController.request_shutdown和RunnerManagementDialog.refresh放行请求；Runner.command负责最终安全核验，服务端不信任GUI缓存的安全状态。

离线核心36 passed（54.56s），真实HTTP/恢复退出/预处理未知报告专项7 passed（2.17s，与核心部分重叠）；GUI Runner流程21 passed（91.79s），布局/恢复显示2 passed（0.51s）。证据artifacts/exit-{core,accept,gui}-20261102.xml及layout-fix-20261102.xml；artifacts不保证随Git迁移。独立GUI/Runner进程及Windows目录释放验收另记最终结果。本批没有真实CST启动或操作现场F盘，不能追认其进程安全已核验。

独立GUI/Runner进程验收7 passed（37.06s），artifacts/exit-process-fix-20261102.xml：空闲、运行、假Worker失败、仅关界面、shutdown响应丢失、Windows控制台、RECOVERY_REQUIRED七场景；完整退出后运行目录可重命名并删除，恢复场景INI字节保持，均正常关闭测试服务。仅测试Python/fake执行器，不等于真实CST退出或现场问题实测修复。轻量进程日志/探针记录保留在artifacts/gui-layout-20261102/exit-evidence，本轮pytest目录已清理；原临时路径不可直接复用。未提交、推送或重打包。
