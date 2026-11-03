# CST后台调用改造及无求解验收

> 适用性复审（2026-11-03）：原批次实施/故障/验收记录；旧当前、未提交、待做及现场进程状态不代表本次实时事实。现行实现见[当前状态](current-status.md)、[功能索引](feature-index.md)及对应API；不重算或追认旧证据。

2026-11-03，本机Windows/CST2022.5。**新建/类型化定义构造的后台链已通过正常及可捕获语法错误验收：quiet在归属核验后调用，用户前台事件0，无人工交互，标准退出。** 使用临时非活动桌面内的真实CST GUI，不是真正headless或独立WinWrap编译器。

轻量证据：[JSON](../knowledge-base/cst-background-acceptance-20261103.json)。最终14项批次artifacts/cst-macrocheck-ce858a55；另有公共空工程批次artifacts/project-create-baaa340e。原始事件/宏/日志在artifacts，不保证随Git迁移。

## 实现

|入口/模块|改动|身份及错误边界|
|---|---|---|
|native_definition_builder.run_new_definition|默认创建临时非活动桌面；显式启动所选安装的COM服务器，使用本机注册命令的-activex及文档化-i；保持一次RunScript|显式服务器PID、创建时间、父进程和安装路径核对；宏报告的modeler/DE必须归属该服务器，拒绝其他已有实例|
|同一COM应用的quiet|RunScript通过标准COM流封送在专用STA线程执行；原持有线程在nonce归属握手后调用该Application.SetQuietMode(True)，成功返回才写quiet-ready并放行宏正文|不获取全局Active3D，不重新CreateObject猜目标；COM帮助未提供quiet读回，记录setter返回，不能标为readback=True|
|NativeProjectCreator|原生DesignEnvironment.new(options=['-i'])在临时桌面启动；公开pid及nonce核验后set_quiet_mode(True)、in_quiet_mode()核对，再new_mws|加强启动时间/基线PID核对；quiet读回False阻止继续。公共API不新增配置schema或MCP工具|
|windows_desktop_process.DesktopProcess|显式CreateProcessW，真正设置STARTUPINFO.lpDesktop；标准句柄只复制给本轮子进程，继承环境继续经过CST Qt隔离|不使用ShellExecute，不修改全局注册/系统服务；poll确认退出后释放进程句柄，close不终止进程|
|cst_background|临时CreateDesktop/CloseDesktop；用户输入桌面上的foreground/show WinEvent钩子，加50ms指定桌面窗口枚举|不调用SwitchDesktop或SetForegroundWindow；隔离桌面只观察，不隐藏/回答未知对话框；按PID+创建时间+安装路径操作/分类|

原始窗口事件仅写诊断文件，返回调用方的是计数和状态摘要，避免公共结果携带大量窗口明细。事件缓存有上限，丢弃计数不为0时不授予无抢焦点验收通过。观察器失败时保留诊断；不会把“没有记录到事件”在观察器已停止的情况下当成通过。

COM的两个nonce分别标识原生归属握手与驱动完成标记，验收各自核对，不错误要求两者相同。quiet-ready是此创建通道的本地门禁，不改变Managed Task/Completion/ACK或收尾协议。

## 最终实测

|项目|结果|
|---|---|
|最终批次|ce858a55，一新3D副本、一次RunScript、14次MacroCheckThis、0求解|
|正常与语法错误|0+正例通过；原始Zrange返回10576；明显语法错误、重复声明、缺With均返回错误对象；不依赖人工点错误框|
|正文不执行|文件标记不存在；L表达式保持`2 * W0Base`|
|quiet|在绑定原生身份后SetQuietMode(True)返回；quiet-ready nonce核对通过；无COM读回断言|
|焦点及窗口观察|用户输入桌面本轮CST foreground事件0；168个归属窗口状态事件；0观察错误、0丢失、0枚举缺口；隔离桌面窗口操作0次|
|退出|project/application Quit均返回，辅助进程退出0，exit_confirmed=True，active_pids空；无遗留CST|
|桌面资源|CloseDesktop成功，desktop_handle_closed=True；未切换用户桌面|
|公共空工程入口|baaa340e创建/只读检查/同ID重放通过；原生quiet读回True、用户CST前台事件0、退出0且临时桌面句柄关闭。该批父观察器仍有非激活最小化保护；之后最终策略调整为隔离桌面仅观察，COM最终批验证了该策略|
|纯Windows适配器|独立Python子进程读回实际桌面名与要求一致、退出0，进程/桌面句柄释放；不启动CST|

“0前台事件”是本机该受控样本的实际WinEvent观察，不是所有Windows/CST版本永远不闪现的数学保证；这里没有用事后拉回用户焦点来制造通过。CST仍创建了GUI窗口，只是位于非活动桌面。

## 对照及修复过程

- 5ac13ce0：普通COM路径在握手前抢前台1次；quiet、14项与退出成功，但后台目标失败。保留此正向焦点检测对照。
- 8ac99988：最初观察器把空桌面枚举返回0/last-error0当致命错误而停止；不计无焦点通过。后续继续记录枚举不可用采样，不把它当没有窗口；真实非零错误仍报告失败。
- 6cdbe03d、6259a650：分别记录3次、2次前台事件。原因定位到Python的Popen没有传递赋在STARTUPINFO上的lpDesktop字段，不能仅看Python对象有该属性就称已隔离。显式启动服务器也不能弥补该字段未传入。
- 纯Python桌面读回校准后改用CreateProcessW。970d0a35首轮通过，随后去掉隔离桌面内不必要的最小化动作、补充错误诊断和摘要，最终ce858a55再次通过。
- 首轮验收还修正了驱动nonce与归属nonce混用问题；该判定缺陷没有被写成真实不抢焦点的失败根因，首次普通COM本来就存在1次真实前台事件。

全部CST对照串行、无求解、正常退出；未强杀或修改用户原工程。旧失败保留旧结果，不以最终通过覆盖它们。

## 适用范围和剩余工作

本批生产默认覆盖公共空工程创建和类型化定义构造（复用同一服务/Runner），并覆盖W0校准工具。**G03的独立CLI验证、预处理和Managed/HOM Worker的既有CLI启动尚未迁移为此隔离桌面策略**，仍按原有最小化机制运行，不能将本页结论套到整个HOM链。迁移这些长生命周期入口时须同时处理桌面租约、恢复元数据和退出，不能只换启动函数。

需要用户输入的对话框不保证被quiet抑制；本轮未触发许可失败、保存询问、外层驱动编译错误或任意求解故障。隔离桌面也不会替用户回答：未知交互/通信停滞保留诊断并按既有有界等待失败，正常求解仍无固定总超时，不强杀替代正常关闭。服务/会话环境若无权创建桌面，直接失败，不静默回退到用户桌面。

Call形式仅已通过语法检查，仍不据此替换0+或取消G03/W3。独立NoUI的评估过期状态未改变。副本伴随目录及pytest临时目录完成后清理，保留轻量证据、脚本、宏、hash和窗口诊断；需要模型时重新生成。

## 最终检查

相关离线回归63 passed（12.59秒，artifacts/background-verified-20261103.xml）；独立原生Windows桌面基础测试1 passed（0.20秒，artifacts/desktop-native-20261103.xml），与14项真实CST样本分别记录。文档索引曾因多源码符号混在一行失败，拆分F136/F137后重跑通过；不隐去该轮失败。
