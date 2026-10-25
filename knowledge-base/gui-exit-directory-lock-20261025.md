# GUI关闭后目录占用的证据边界

2026-10-25，基线e8a5b22。[审计与待办](../docs/gui-exit-and-directory-lock-audit.md)。本轮无生产功能修改、未启动CST、未强杀进程。

用户确认被占用的是发布包解压运行目录，而非具体.cst或日志。源码RunnerClient.connect明确cwd=发布根目录；主窗口安全停止后只detach，不shutdown Runner。即使任务已FAILED或COMPLETED，独立服务仍可存活。

Windows受控实测：

- Python子进程只以空目录为cwd即可使rmdir报WinError32；通过stdin正常返回后可删除。
- FileHandler打开的日志不可删除；handler.close后即使Python仍存活也可删除。
- ThreadPoolExecutor.shutdown(wait=False)后，解释器仍等待运行中的future；三秒任务期间cwd被占用，任务完成后自然退出并释放。该探针不是生产GUI网络故障复现。
- 真实非法INI导致LocalExecution构造失败，已记录日志的两个FileHandlers未关闭；直到显式关闭仍不能删除文件。构造前尚未写日志的注入异常没有同样占用，延迟打开边界必须保留。
- HOM已有检查点但非resume触发start前置拒绝，result.log仍打开，删除报WinError32；关闭该流后释放。

轻量记录位于artifacts/gui-exit-audit-20261025/{report,exception-resources,real-invalid-config-resources}.json；artifacts不保证随Git迁移。探针子进程均正常退出，cwd临时目录已删除，日志流关闭，保留少量记录。未确认用户现场具体PID，不把机制复现当作现场唯一根因。

目录cwd占用、项目日志句柄、Runner所有权锁、CST工程锁是不同对象。关闭控制台可能仅释放shell cwd，也可能终止未退出的Python；不能据此断言CST已经安全收尾。若Runner仍计算，强制关闭/删源码包会破坏其运行前提，不属于安全释放方法。
