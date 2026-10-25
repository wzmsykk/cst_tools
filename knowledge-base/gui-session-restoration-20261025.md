# GUI重新打开与后台状态恢复

2026-10-25，[设计/使用/测试入口](../docs/gui-session-restoration.md)。不启动真实CST，无工程修改/强杀。

此前日志/状态恢复要求用户先重新选择项目；缺少跨GUI启动的目录入口。新增每用户gui-session.json只记忆项目绝对路径，生产入口重开后沿用已有RunnerClient连接和日志分页读取。它不能证明运行已停止、CST已关闭或结果已采用；这些仍由Runner/检查点/会话门禁确定。

真实进程对照：两个独立Qt GUI自动找回同一正在运行的假Runner，instance_id/run_id不变，持久start命令一条、无自动recover。Runner已退出时自动启动服务只读取原中断状态和磁盘日志，无start/recover且无temp求解会话。测试记录在artifacts/gui-reopen-process-20261025.xml，artifacts不保证随Git迁移。

保存目录迁移/删除或盘符暂时离线时不自动新建项目；损坏偏好文件保留并提示手动选择。无旧版记录时必须先手动选择一次，不能声称从任意磁盘自动发现全部后台。

HOM显示设置只读scan_manifest.json/pps.json，不恢复尚未保存的GUI草稿，不反写工程。原CST安装不可用时设置显示可能不完整，但仍可观察现有后台；实际续算受既有安装/项目校验限制。发布烟雾模式禁用选择恢复，防止测试自动连接用户项目。

尚未做真实CST重连和正常桌面字体/视觉验收，独立进程测试仅证明Qt GUI/Runner控制链与无重复命令。
