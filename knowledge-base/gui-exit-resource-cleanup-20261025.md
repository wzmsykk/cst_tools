# GUI退出修正与资源释放实测

2026-10-25，[现行设计/API/验收范围](../docs/gui-exit-resource-cleanup.md)。未启动真实CST，不修改用户原工程，不结束用户进程。

修正前证据保留在[目录占用审计](gui-exit-directory-lock-20261025.md)。本轮使用ExitStack覆盖LocalExecution部分构造及正常close异常；真实非法INI产生错误后application.log/jsonl可在同一Python进程内重命名，HOM前置拒绝不再打开无用result.log。

完整退出成为stop→安全收尾→Runner shutdown/OS所有权确认→GUI通信池收口→本地日志关闭；仅关闭界面保留后台。后者不承诺释放发布目录，因为Runner本身仍以该目录为cwd。后台管理新增可读取PID/cwd及启动父进程PID，不自动改变外部shell目录或终止它。

QMessageBox错误提示在offscreen回归中两次触发原生access violation；未将其当业务失败或成功。改为窗口内持久错误说明后，停止/关闭失败路线通过。尚未证明Qt所有原生退出问题根因消除，现场视觉仍需验证。

初版进程夹具的空发布目录缺少data/defaultPPS.json，导致GUI启动失败；修正为包含真实data资源，不改生产资源路径，也不把该失败计通过。初版失败用例直接放检查点被服务端合法门禁拒绝，改用真实假Worker的非法R值触发实际FAILED。实际Windows目录释放使用重命名而非删除非空目录，避免把“目录非空”误当句柄占用。

跨进程用例：GUI/Runner都为实际Python进程，执行器fake，覆盖空闲/运行中/FAILED/仅关界面/丢失shutdown响应/Windows cmd /c。完整退出后两个PID正常结束且目录可重命名；仅关界面后后台仍存活且目录占用，标准shutdown后才释放。不通过kill获得成功。

独立交互式cmd/PowerShell若仍在发布目录，应用无法让它释放cwd；需要用户cd离开或正常关闭终端。此限制与CST收尾、日志句柄分开解释，不承诺“窗口消失必能删除所有目录”。

最终报告与清理数字见current-status；轻量报告在artifacts，默认不随Git迁移。当前离线证据不代表更新后的真实CST故障关闭已验收。

offscreen布局截图在受限与正常用户权限均无文字，实测QFontDatabase字体集合为0；没有把空白截图计为视觉通过，也未将offscreen变量传给CST。正常桌面环境字体/布局仍需验证，visual-boundary.json保留此边界。
