# CST后台运行、headless与无弹窗边界

2026-11-03，针对本机CST 2022.5及W0校准入口的静态核查。本轮没有启动CST或修改启动代码。**后台/批处理可用；没有核实到本机Windows2022通用的真正headless入口；不能把最小化或quiet称为全部异常都不会弹窗。**

## 官方能力与作用范围

|能力|CST2022本地文档定义|对本项目的意义|
|---|---|---|
|CLI `-i`|iconified state|最小化启动，不是无窗口，也不承诺没有启动闪现|
|CLI `-m -b project.cst`|加载工程并执行Model/3D/Model.run|是批处理执行入口，包含前端；空工程批宏不执行的既有边界仍适用，不能直接替换W0新3D RunScript通道|
|COM `SetQuietMode(True)`|抑制message boxes；不能抑制需要输入的dialog boxes|必须调用本轮归属已核实的Application对象，不能全局获取活动实例；不是保存、授权和恢复提示的通用自动回答器|
|Python `set_quiet_mode` / `in_quiet_mode`|对应消息框抑制及状态查询，同样有输入对话框例外|查询可用于后续验收；Python示例称new默认quiet/script，但不等于隐藏主窗口|
|Python `DesignEnvironment.new(options, gui_linux, ...)`|options可传CLI选项；gui_linux控制Linux是否GUI|不能把gui_linux=False当Windows隐藏参数，也不猜测存在NewHidden/Visible=False|
|Linux批处理|本地Python接口支持Linux GUI选择；集群部署另有平台前提|不能把Linux配置照搬到本机WindowsCOM路线|

本地原文：安装目录Online Help/advanced/commandlineoptions.htm、advanced/vbaapplicationobject.htm、Python/source/cst.interface.html。帮助/API的quiet定义明确保留输入对话框例外，即使示例更笼统描述阻止对话框，也按具体接口限制设计。

官方较新[Cluster Integration Guide 2025](https://updates.cst.com/downloads/Cluster_Integration_Guide_2025.pdf)第4及8节记录Windows执行环境可能需要GUI/console session，Linux batch默认使用Xvfb。第10.2节又提到可抑制GUI，但未给出可直接证明本机2022具备同等入口的调用方法。这是跨版本部署参考，不据此宣布Windows2022绝无无GUI方案，也不把批处理等同于不创建前端。

## 当前代码的实际缺口

- `managed_cstworker._background_startup_options`使用SW_SHOWMINNOACTIVE；`_keep_window_minimized`每0.5秒枚举顶层窗口，但仅匹配启动进程PID。它不覆盖所有modeler/其他已归属子进程窗口，且最小化是窗口出现后的补救，不能证明从未闪现。
- `native_definition_builder.WRAPPER`只对PowerShell设置CREATE_NO_WINDOW；COM启动的CST不受此控制台标志的无窗口保证。本入口尚未显式设置Application.SetQuietMode，也没有窗口事实采集。W0已有“无需人工确认完成”证据，不能改写为“没有显示窗口”。
- 原生Python创建入口调用DesignEnvironment.new，文档描述默认quiet/script；当前没有显式读取quiet状态或验证窗口/输入对话框矩阵。
- `cst_process_environment`主动清除QT_QPA_PLATFORM等Python Qt设置。不能向CST传offscreen作为headless捷径；保留环境隔离，不将GUI测试环境带入外部CST。

## 建议的实施目标

优先将产品承诺写为**后台、不抢焦点；正常任务无需人工交互；无法静默处理的异常明确暂停并给诊断**。如果要求所有窗口始终不出现在当前桌面，需要另外验证受支持的隔离桌面/远程执行部署，而不是偷偷隐藏未知模态框后继续等超时；本轮不配置系统服务、桌面或注册表。

1. 统一后台选项的意义和各入口应用范围。CLI可评估-i；官方原生Python new可评估options=['-i']并查询quiet；COM无已核实的等价最小化启动参数，不虚构。
2. 在能证明归属后，通过该实例的官方Application/DE设置并核对quiet。当前COM单次RunScript的绑定发生在宏开始后，不能为了更早quiet就无条件更改可能复用的任意COM实例；需先设计新实例身份门禁与设置时点。不能换成全局GetObject/Active3D。
3. 按已绑定的PID+创建时间及安装身份观察DE/modeler窗口，区分主窗口、弹出窗口、可见性、最小化和前台焦点；只操作归属明确的本轮窗口。窗口隐藏不能作为任务成功、停止或退出证据。
4. 保持MacroCheckThis返回错误对象的检查路线，预处理输入与保存/退出前提，避免主动MsgBox/ReportError。ReportInformation/Warning也需按文档区分ToWindow接口。不能盲点OK、否定所有保存提示或隐藏需要用户输入的错误框冒充解决。
5. 所有异常继续有界通信/启动/退出并独立记录恢复事实；正常求解仍不设固定总超时。不把弹窗导致停滞当正常慢求解，不强杀代替标准退出。

## 后续验收

用无求解副本对比普通COM、显式quiet与后台窗口策略；每批检查实际quiet、窗口可见/最小化/焦点变化、MacroCheckThis错误返回、完成标记与标准退出。覆盖正常及可捕获语法错误；保存/输入、授权初始化等需要另外受控设计，不能直接触发未核实的全局对话框。窗口轮询能证明观察到的状态，不能证明间隔内绝无闪现，需明确证据分辨率。

本轮仅核实文档和现有代码，不宣称quiet/headless改造已经完成。独立NoUI评估过期属于真实未解决初始化边界，不能用IgnoreDialogs代替授权处理。W0已验原生检查能力保持有效，后台显示验收是新增且独立的要求。

## 实施后状态（2026-11-03）

[真实后台验收](cst-background-acceptance-20261103.md)已补：公共空工程与类型化构造默认临时非活动桌面，归属后quiet，WinEvent与窗口观察，正常/语法错误14项及标准退出通过。使用CreateProcessW真正传桌面参数，不再依赖Popen未支持的lpDesktop属性。仍是GUI隔离，不宣称Windows真正headless；其他CLI入口未迁移，具体范围见验收表。
