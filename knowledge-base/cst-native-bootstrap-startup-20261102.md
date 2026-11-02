# 2026-11-02 原生 bootstrap 启动失败与退出边界

## 实测

当前 Codex MCP 服务（九工具）创建一个空 MWS 并正常关闭通过：Runner PID60284 已退出，run389bd860a83645f796717f1c7327b971，记录见[mcp-codex-g02-public-20261102.json](mcp-codex-g02-public-20261102.json)。源和文档 hash 已核对，同 request_id 返回同 run，0次 Solver。

后续以官方现代 SDK/stdio 调用新14工具的独立串行验收目录：`artifacts/typed-public-74b38a64`。在 create_project 内 DesignEnvironment.new() 失败：`TimeoutError: Could not connect to DE with PID: 40732`。没有 de-pid.json/identity-bound.json，没有执行 new_mws，没有工程保存、建模或求解。框架保持 RECOVERY_REQUIRED/session_safety=running，没有发布空文档或 ready。

归属来自启动器的后代记录：启动器12268、DE40732、DBStorageServer47704，并保存创建时间。受限命令环境下 psutil 对DE返回NoSuchProcess；常规权限下相同 PID+创建时间/安装路径确认仍运行。不能将受限查询当作全系统退出证明。

只尝试对核实的 DE40732 调用官方 DesignEnvironment.connect(pid).close()，没有全局 Active3D，也没有强杀。connect实际抛出：`Could not start command 'wmic process where "processid = ..." get commandline /format:list'. ... The system cannot find the file specified.`。此调用尚未取得 DE 引用，也没有执行 close。已检查没有可见的 CST 窗口可供正常关闭。

## 定义、推测和未完成

官方接口 docstring 明确 connect(pid) 连接指定 DE；本次实测它还依赖外部 wmic 查询相关进程。**缺少 wmic 已证明阻挡这次接管/关闭；尚未证明它是 DesignEnvironment.new 超时的唯一根因。** 两次启动来自不同宿主/命令环境，不把差异直接归因到模型、许可证或代码。

未安装系统可选组件、未补造 wmic、未尝试未文档化 process_info 参数。尚需正常处理遗留验收实例后，核实所选运行环境中的原生连接前提，再做单次对照。没有启动第二个并行 CST。

实现新增 bootstrap-context.json（运行时hash、库目录、wmic可见路径，不导出环境变量/许可证），传播原生 failure.json 内容。failure.json 被识别为结束信号后进入既有退出预算，避免先再等一个阶段空闲预算；不因失败文件存在声称应用已退出。

## 产物

本轮失败目录中的 failure.json、session-status.json、cst.log、桥接代码和 public-calls.json 保留；该目录目前是恢复证据，不做清理。artifacts不保证随Git迁移。本轻量记录可随源码保存，原始模型/场不存在，也不借用此前结果作本轮通过证明。

## 后续核验（2026-11-03）

用户反馈PID已不见后，以常规权限复核DE40732、存储47704及Runner53312原身份均已退出；仅按退出事实写abandoned-dead，未补造0退出码/标准关闭。未发布创建意图通过显式恢复记为OPERATION_ABANDONED，0次原生重放；物理pending=0、session_safety=exited-unverified，原诊断保留。

常规权限的新SDK场景typed-public-255868ca成功创建/关闭空工程和提交草稿/配置，进入空.cst批宏建模时没有完成/失败标记，原生日志“Unable to start solver because of missing structure data”，退出0。仅显式ChangeSolverType的空MWS校准empty-batch-ddbca33c仍没有执行Model.run。两轮均确认标准退出且0次求解；求解器身份不足以解释这个前提。

初版新对象构造把身份探针与建模分成两次RunScript；typed-public-676d2b63的身份帧/绑定存在，但第二脚本未执行。最小new-dispatch-0ef58a23第二脚本仅SaveAs/写标记，同样未执行。改成同一次RunScript内身份等待的new-dispatch-31810771校准通过：完成标记、保存和标准退出，0求解。这里记录本机2022.5条件，不把观察扩大成所有RunScript永久只执行一次的官方保证。

新构造通道共用Runner/定义事务；它不依赖接管任意活动窗口。真实整链正在从同一公开草稿继续，旧失败没有计算结果，不能被替代为已通过的求解。

## 收口证据（2026-11-03）

后续单次脚本身份门禁加构造已成功。首个阻塞弹窗由用户提供：`.Zrange ((-RestoreDoubleParameter("L"))/2), ...` 被报Unexpected text。错误来自Sub多参首参数括号语法；数值表达式前加0+消除歧义，保留参数引用。用户点OK，旧候选只按退出事实退役。新候选成功保存、G03及一次实际求解，见[最新报告](../docs/typed-public-acceptance-20261103.md)。

原生Solid.DoesExist的CStr输出-1；材质Vacuum、体积3141593.79277443mm³、两种盒与六电边界在保存/重开相同。参数JSON使用descr保存说明；R=100、L=R及说明实际保留。后处理结果已核对采用回执缺口并恢复，0次重复Solver。旧缺wmic/启动失败记录不删，也不把后来成功改写为最初操作已成功。
