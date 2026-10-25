# GUI重新打开：自动找回项目与连接后台

2026-10-25。自动恢复的是项目选择、设置显示、后台连接和历史运行事实；不会自动start、recover、重新预处理或重新求解。Task/ACK、检查点及安全门禁不变。

## 用户流程

1. 正常入口gui_app.py启用每用户记录；手动选择项目目录后保存到`%LOCALAPPDATA%/CSTTools/gui-session.json`。只保存schema_version与项目绝对路径，不保存令牌、进程安全结论或自动执行队列。源码发布包升级/移动后仍使用同一用户记录。
2. 再次打开时，窗口完成初始化后找回目录，读取原HOM scan_manifest.json/pps.json显示频率、mesh、worker数、源工程及后处理设置。读取失败记录警告，仍允许连接后台查看事实；不改项目原文件。
3. 后台存活时自动连接原实例，回放原时间/源码上下文的日志、确认覆盖/已计算上界、模式数、当前CST进度和错误。其他窗口控制租约仍有效时只读，不自动claim。
4. 后台已退出时沿用RunnerClient的单次启动及所有权门禁，允许启动Runner以读取原status/checkpoint/log；没有计算命令。上次Controller中断或RECOVERY_REQUIRED仍要求显式恢复。用户之后点击“继续未完成”才进入续算。
5. 已有检查点/运行清单的项目禁用“开始新扫描”，提示继续或选择新目录；服务端仍保留检查点防覆盖与项目运行锁。恢复连接不能被当作已有结果已完成对账的证明。

首次升级前没有记录时需手动选一次目录；不会全盘猜测项目。目录已删除、盘符离线或记忆文件损坏时显示手动选择提示，不自动创建丢失目录、不清空原记忆文件。该文件是GUI偏好，不是配置/检查点的替代品。

## 实现入口

- [GuiSessionStore](../GUI/session_store.py)：读取/校验选择，利用既有原子JSON写入保存；跨平台无LOCALAPPDATA时使用用户.config/CSTTools。
- [RunnerBackend.restore_last_project](../GUI/runner_backend.py)：恢复已选项目并只读原清单/后处理；session_store显式注入，普通测试构造不接触用户实际记录。
- [MainWindow._restore_previous_project](../GUI/main_window.py)：延迟到界面/信号创建后填充路径和设置、触发现有Controller观察。打开窗口前主动选择其他项目不会被延迟回调覆盖。
- [gui_app.main](../gui_app.py)：正常启动启用记录；--smoke-test禁用自动恢复，避免发布检查意外连接用户真实项目。

连接失败不替换未知/存活后台、不盲目重复启动；已有连接失联仍沿用显式重连规则。无CST安装时仍可查看后台日志/状态，实际启动/续算仍受现有安装和项目校验限制。原始未保存的编辑草稿不恢复；以项目持久文件显示，不把GUI旧值覆盖到工程。

## 验收与边界

[GUI/存储测试](../test/gui_session_restore_test.py)覆盖记录跨Backend、损坏/丢失路径不创建工程、原设置不被改写、RUNNING/INTERRUPTED/RECOVERY_REQUIRED自动显示状态和旧日志、不发送计算/恢复命令，以及烟雾入口隔离。

[真实进程测试](../test/gui_session_process_test.py)连续打开两个独立Qt GUI进程，自动找到同一正在运行的假Runner及原run_id，start仍一条，无自动recover；后台已退出时新GUI自动启动Runner读取磁盘中断状态/日志，无start/recover、无temp求解会话。使用[Qt探针](../test/support/exit_gui_probe.py)，项目偏好均显式放测试目录，不写用户真实AppData。

最终测试数字、报告与清理以current-status为准。真实进程是Qt GUI/Runner Python，计算为fake或未提交，并非真实CST重新连接/求解验收。原有退出时stop/shutdown/detach语义保持；未完成项目只找回和展示，不自动计算。

本轮最终离线810 passed、21 integration deselected（204.81s），主窗口另34 passed（1.49s），文档/日志索引3 passed（1.05s，重叠），烟雾启动通过。报告artifacts/gui-reopen-{offline,main,index}-20261025.xml；轻量进程日志及summary.json另留artifacts/gui-reopen-20261025，本轮pytest临时项目结束后清理。未提交、未重打包。

2026-10-25显示分层更新：[默认HOM工作台](gui-hom-workspace.md)展示确认覆盖/模式及指标；完整日志和后台管理收纳到详细页，日志保留与重连回放逻辑不变，本地检查点只读观察不提交任务。
