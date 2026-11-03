# BasicNoUIObj独立进程校准：初始化未通过

> 适用性复审（2026-11-03）：原批次实施/故障/验收记录；旧当前、未提交、待做及现场进程状态不代表本次实时事实。现行实现见[当前状态](current-status.md)、[功能索引](feature-index.md)及对应API；不重算或追认旧证据。

日期：2026-11-03。**成功创建NoUI对象并正常收尾，但初始化未通过，SyntaxCheck及Zrange正反例未执行。** 用户在本轮独立初始化期间观察到提示：`This eval copy is expired`。该提示属于用户现场证据，不是程序成功读回的ErrorText字段；不能据此断言CST自身授权过期。

工具：[validate_winwrap_noui.py](../test/support/validate_winwrap_noui.py)，[回归测试](../test/winwrap_noui_probe_test.py)，[轻量证据](../knowledge-base/winwrap-noui-acceptance-20261103.json)。没有启动CST、修改系统注册表、读取/复制许可文件或修改原工程。原始阶段日志及当时执行的工具快照在artifacts/winwrap-noui-local-20261103，不保证随Git迁移。

## 文档依据及初始化方式

本轮读取随安装保留的wb9ent.chm中Initialize、IsInitialized、NoUI Object、SyntaxCheck、IgnoreDialogs、Shutdown及Disconnect条目。Initialize文档要求安装序列号，同时提供仅在已安装开发软件环境适用的示例token；本轮只尝试该文档化开发环境token，没有读取CST随附的wb9ent.lic，没有猜测或尝试其他密钥。

NoUI是无需容器窗体的ActiveX对象。Shutdown的文档成功值是0，-1表示嵌套执行；Disconnect的文档成功值是True，表示语言扩展已断开、对象不再可用。不能将Shutdown的0按普通bool判断为失败，也不能将测试进程退出0当作初始化或语法通过。

## 实际过程与证据

|阶段|事实|边界|
|---|---|---|
|免注册manifest首轮|创建对象前0x8007007E；绝对路径LoadLibrary单独成功|不能归为初始化授权失败；尚未进入Initialize|
|标准类工厂诊断|对象可以创建，但类型信息调用返回0x8002801D“库没有注册”|动态绑定仍需要类型库映射；没有注册系统类型库。该诊断分支已从最终工具移除，不形成备用绕行接口|
|本机路径映射|尝试硬链接被文件系统拒绝；随后在本轮artifact中临时复制两份公开二进制，hash与安装文件一致|仅本机测试，不复制许可内容、不进入发布包；测试完成后删除临时二进制|
|进程内SxS映射|为NoUI/内部依赖及其类型库建立仅本进程有效的activation context；对象和属性访问成功|不是把组件全局注册，也不是独立启动CST或直接调用底层CodeUnit规避初始化|
|Initialize|初始化前False；只调用一次文档化开发token；返回后仍False|用户看到eval expired；本轮不能建立合法可用的独立编译会话，不继续尝试其他初始化方式|
|SyntaxCheck与诊断|执行次数0，样本列表为空|错误行列、原始/正例差异、正文不执行均未验证，不能拿ANTLR结果或静态类型库代替|
|收尾|Shutdown=0、Disconnect=True、activation context撤销True，Python子进程21312正常退出0|是未初始化NoUI对象的正常收尾证据，不是成功编译后收尾的证明|
|CST进程|前后均无CST进程；稍后复查原helper PID不存在|无CST启动或遗留；没有强制结束进程|

NoUI文件版本9.21.027，OCX/DLL hash见JSON。临时manifest同时映射OCX库1.0和运行库1.1，避免把类型库缺失误判为引擎缺失。原manifest放在与二进制不同目录时，单纯设置assembly probing目录不足以完成本轮根文件解析；本记录只描述该受控样本，不推导所有SxS部署情况。

## 新确认的行为边界

- 本机安装二进制可创建BasicNoUIObj，不代表当前独立宿主具备可用初始化条件。文档化开发token不是可随程序分发的授权凭据。
- IgnoreDialogs=True在本轮初始化前已设置成功，但用户仍观察到eval expiry提示。不能承诺此属性屏蔽授权/初始化阶段的所有UI；它的文档描述不能代替实测。
- 主程序只有在初始化、全部检查、正文标记及收尾事实齐全时才报告校准完成。最终工具对未完成返回非零；保留当时执行快照，不能把后改的诊断代码当作当时已执行。
- 最终工具补充了初始化失败时读取已知ErrorNumber/ErrorText/ErrorSource的诊断，但为避免重复触发过期评估提示，本轮未再次原生运行；用户提示仍独立存档，不补造COM错误码。

## 结论及后续

轻量原生路线已证明可定位、可激活、可清理；**未证明可用来编译**。不继续对过期评估副本重复初始化，不读取/复用CST许可材料，也不直接改用CodeUnit绕过初始化。若后续具备适用于独立宿主的有效初始化条件，再运行原有正反例与诊断矩阵；没有此条件时保留该路线为不可用，W0原生校准回到经授权的少量真实CST MacroCheckThis。后者仍需用户另行要求，因为本轮约束是不启动CST。

本批补充8项离线事实判定回归：退出0但初始化失败不能通过；Shutdown/Disconnect/退出未确认、正文标记出现、缺样本、判定错误及新增CST事实均阻止完成。它们不是WinWrap编译测试。与文档索引的最终合并结果另见本页验收补充。

最终离线/文档验收10 passed（1.08秒），报告artifacts/winwrap-noui-final-20261103.xml；不包含原生SyntaxCheck通过。临时OCX/DLL副本、CHM解包树及本轮pytest目录已按限定路径清理，保留宏驱动、manifest、原始阶段日志、工具快照、hash与JSON；这些产物不含许可内容。

## 初始化结论的范围修正

[宿主路径核查](cst-winwrap-host-loading.md)明确：本轮只验证开发示例token的独立NoUI路线，未复现CST自身的初始化链。不能将其失败扩大为已有CST授权不可用，也不添加未核实的许可目录参数。
