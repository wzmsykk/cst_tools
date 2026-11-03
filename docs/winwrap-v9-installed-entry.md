# CST 已安装 WinWrap v9 的检查入口

> 适用性复审（2026-11-03）：按原日期/样本/固定来源保留的研究，不是通用格式规范、现行运行合同或新实测。现行实现见[当前状态](current-status.md)、[功能索引](feature-index.md)及对应API；不重算或追认旧证据。

2026-11-03。**静态类型库核查找到了入口，尚未创建对象或执行SyntaxCheck。** 没有启动CST、注册OCX、读取许可密钥或修改系统组件。读取方式为Windows `LoadTypeLibEx(..., REGKIND_NONE)`，只读取类型库资源，工具见[inspect_winwrap_typelib.py](../test/support/inspect_winwrap_typelib.py)。

## 找到的接口

|路径/对象|本机类型库实际成员|能说明什么|
|---|---|---|
|AMD64/WB9ENT64.OCX / BasicNoUIObj|`Code`、`SyntaxCheck`、`ErrorFile`、`ErrorLine`、`ErrorOffset`、`ErrorNumber`、`ErrorSource`、`ErrorText`、`Initialize(SerialNumber)`、`IsInitialized`、`Shutdown`|存在无界面原生检查对象，是优先轻量校准候选；不是只能启动完整CST才有WinWrap引擎|
|同OCX / BasicIdeObj、BasicIdeCtl、BasicNoUICtl|同样存在Code/SyntaxCheck与诊断接口|IDE/控件对象并非轻量测试首选；不为此引入完整编辑器|
|AMD64/wwb9_64.dll / _BasicObject、WWB|`MacroCheck`、`MacroCheckThis`|与本地语言帮助一致；接口出现在类型库不证明外部可直接构造该运行时对象|
|同DLL / CodeUnit（_CodeUnit接口）|`SyntaxCheck(MacroName)`、`ErrorLine`、`ErrorLineNum`、`ErrorOffset`、`ErrorDesc`、`AddExtensionEx`等|有更底层编译/宿主扩展接口；当前未核实其直接使用契约，不将其当成可绕过NoUI初始化的受支持路线|
|同DLL / ErrObject|Description、Number、Source、HelpContext、HelpFile、LastDLLError、Clear、Raise；未列Line/Column|支持此前不向MacroCheckThis返回对象猜测ErrorLine属性的设计；控件行列与ErrObject诊断分开|

两个WinWrap文件的本机版本均9.21.027。BasicNoUIObj的CLSID为`{B20ABC7B-2021-11D6-8F7F-0000861EF01D}`；BasicIdeCtl为`{B20ABC73-2021-11D6-8F7F-0000861EF01D}`；CodeUnit为`{B20ABCE9-2021-11D6-8F7F-0000861EF01D}`。CLSID只用于定位类型信息，不等于对象当前已注册或能成功初始化。文件hash和筛选结果见[轻量证据](../knowledge-base/winwrap-v9-installed-entry-20261103.json)。完整类型库报告在artifacts/winwrap-v9-entry-20261103/typelib.json，不保证随Git迁移。

## “调用CST内部引擎”的两种不同含义

**在CST会话内部检查**：通过已有、归属明确的3D对象执行固定驱动，调用MacroCheckThis。此路线仍需启动CST，但有机会获得它注入的全局参数/方法上下文；实际继承行为待W0校准。

**调用CST目录内的引擎文件**：自己创建轻量BasicNoUIObj，不创建CST工程或主窗口，给Code赋值后请求SyntaxCheck并读取诊断。这是独立引擎实例，不是接管CST正在使用的编译器；CST扩展对象和参数不会因DLL路径相同自动存在。语法通过不能证明CST方法或历史持久性。

本机CST DE可执行文件的类型库IApplication列22项，包括NewMWS、Active3D、OpenFile、CloseProject、Quit等，未列公开的WinWrap/SyntaxCheck句柄。modeler_AMD64.exe的类型库读取失败，不能据此断言其所有动态3D接口都不存在相应入口；目前只是没有核实到由CST公开返回内部编译器对象的受支持方法。不通过全局Active3D选择用户工程来探测。

## 下一步：先试文档化NoUI对象

1. 对照随安装的v9嵌入帮助核实BasicNoUIObj初始化、宿主扩展和部署前提；类型库已显示Initialize需要SerialNumber参数，不能从文件存在推定已获得独立宿主使用权。无需读取/复制CST许可文件来做静态核查。
2. 若本机条件满足，在独立短生命周期测试进程中创建文档化NoUI对象；不修改全局COM注册。初始化失败如实记录，不猜密钥、不切换到底层CodeUnit绕开初始化。
3. 测试完整模块：正常程序、明显语法错误、原始Zrange形态、0+版本、Call形式、数组/ByRef、长行和中文。优先无CST扩展的样本证明基础方言；含CST方法的样本单独标注缺少扩展上下文，不能用宽松stub授予语义通过。
4. 检查代码包含写标记正文；SyntaxCheck后标记不得出现，同时记录可能的初始化事件，结束调用Shutdown并确认本轮进程退出。控件SyntaxCheck可能触发Begin/Object_Initialize的边界仍适用，见[W0契约](winwrap-w0-contract.md)。
5. 与少量真实CST检查对照后，决定它可承担哪些高频语法门禁；不因为引擎版本一致就宣称宿主扩展一致。原则上本机发现并使用用户安装，不默认把OCX/DLL加入源码包；独立使用/分发授权分别核实。

现阶段结论是“找到可进一步校准的原生轻量入口”，不是“已实现无CST原生编译器”。ANTLR实验[已证明](antlr-vb6-poc-20261103.md)不能独立拒绝原始Zrange反例，因此NoUI路线优先于继续扩张通用grammar；W0宿主与W3历史重放验收仍未完成。

本轮工具实际读取后核对NoUI目标成员集合存在；10项相关离线/文档测试通过（6.89秒）。类型库读取不证明对象可激活、授权可用或检查功能可执行。

## 2026-11-03独立对象实测

[NoUI校准](winwrap-noui-acceptance-20261103.md)已实际创建对象、访问属性并正常Shutdown/Disconnect；初始化仍False，用户观察到eval expired。SyntaxCheck与正反例未执行，因此“入口已找到”不能提升为“轻量编译可用”。本轮无CST启动；暂停重复初始化，等待独立宿主有效使用条件或后续真实CST校准。

后续[加载与宿主路径核查](cst-winwrap-host-loading.md)未从主程序导入表/manifest确认完整初始化链。v9 Initialize接收序列号而非路径；独立NoUI失败不能代表CST内部路径失败。复用CST初始化应通过已授权宿主的既有接口，实际MacroCheckThis仍待校准。
