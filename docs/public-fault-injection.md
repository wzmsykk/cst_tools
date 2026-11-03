# 公共链串行故障注入

入口：[驱动](../test/support/validate_public_faults.py)。默认仅输出计划，不创建目录、不启动CST；`--run-cst`才执行。复用生产Managed、ApplicationService、G03和原有停止/ACK探针，没有生产故障开关。

## 运行范围

驱动包含12个停止/ACK时点，以及公共服务的发布前控制器退出、采用回执写入前控制器退出、真实求解器拒绝三项。`--case`可重复选择，默认全部串行。新增驱动使用500–2000MHz与nmodes=1，适配R=100mm的已验证Pillbox；旧探针独立入口仍保持500–800MHz默认，不把任意模型都当适用。源工程应为已经预处理、受限A1、固定小网格、中心Z线Frequency/RQ定义，不替用户修改源工程。

```powershell
python test/support/validate_public_faults.py
python test/support/validate_public_faults.py --run-cst --source <已验证Pillbox.cst> --cst-exe <CST程序> --case before-parameters --case controller-before-publication
```

父监督进程独立持有独占探针锁，在启动每例前核验不存在CST并检查至少1GiB空闲；这是本机验收隔离策略，不是服务器生产要求。它创建唯一目录、保存父意图和源hash，再启动专用子进程；内部`--child/--root`要求父PID、源hash、安装和artifacts范围匹配。正常求解没有总超时，通信、启动及退出仍由原实现有界。任一子进程失败、退出不明、残留CST或源hash变化，停止后续；报告标记blocked，保存日志，不强杀CST、不自动启动另一个副本。

控制器用例在实际Worker已经标准关闭、采集已持久化后，以`os._exit(91)`让测试子进程突然退出，跳过Python清理；不是结束CST，也不是伪造异常后仍运行finally。父进程确认注入标记、退出码和标准关闭证据，再新建ApplicationService进行两次对账；要求相同公共结果revision、采用日志不增长、Solver调用恰好一次。它证明业务控制进程此边界退出，不冒充完整生产Runner在求解中被杀。

求解器拒绝用例仅向候选宏加入有历史持久记录的`Boundary.Xmax="open"`并原生读回；该条件在2022 Default/Tet的既有文档核查及实测中不受支持。必须实际调用Start，结果发布拒绝后，从原冻结定义新建Worker成功计算；不复用失败快照。该用例直接调用共享服务的新run，不证明生产Runner失败意图已经自动收口或允许立即再次start；Runner显式恢复与求解中崩溃另验。Start返回0、Start异常、返回1但无结果分别记录，不能用人为Err.Raise替代求解器故障。新的实际结果见同批验收记录，既有观察不自动追认本次。

## 报告与清理

父目录`progress.json`表示当前用例；`report.json`保留完整已完成用例与阻断原因。每例保留controller.log、父意图、注入标记、宏、生命周期、回执和原生采集档案。首次试运行可留原始文件；默认完成并确认关闭后清理该例CST伴随场/网格目录，保留轻量.cst、选定工程成员和原始文件hash清单；`--keep-raw`保留原始目录。清理失败也阻断后续，不删除活跃副本、源工程或Git跟踪证据。原始场/网格清理后需重算，artifacts不保证随Git迁移。

## 独立协议验证

[raw stdio测试](../test/mcp_wire_fault_test.py)在可选官方MCP环境运行，不启动Runner/CST：直接验证discover、逐请求版本拒绝、tools-only未知方法、无活跃请求的取消通知无回复及错误后继续调用。与SDK测试、业务故障矩阵分层报告；并未覆盖全部非法JSON、通知、取消竞态、分页、授权或HTTP扩展，N01–N25仍不能整体勾选。

完整当前覆盖见[矩阵](public-fault-matrix.md)。监督器不能在CST阻塞方法内强制注入一个真实内部异常，许可弹窗、安装差异和求解中Runner进程退出仍须逐场景校准；不是承诺所有故障无需人工处理。

## 2026-11-03真实验收

最终目录`artifacts/public-native-faults-4b92d5c9`：15个用例全部通过，14次实际Start，16个Managed会话及6个G03会话全部标准关闭。源工程hash未变；两个控制器退出用例清理后再次对账，结果revision不变且采用事件各一次。求解中/后停止的E/H场在活动工程、中断快照、关闭快照之间hash一致。最终批次自动清理51个伴随目录，保留轻量工程与证据；前置4例校准批清理17个伴随目录。

求解器拒绝实际为Start返回1，而读取模式数时报没有Eigenmode结果；错误文字带有“2013以前工程”的通用说明，本轮为新模型，不能据此断言工程太旧。没有post帧是次生现象。已将成功采集移至返回值/模式可用门禁之后，保留原始SOLVER_FAILED；其它协议错误码及未知TASK_FAILED映射另有离线分类测试，不把重建/输入/结果输出失败混为求解失败。Start=0和Start自身抛异常未被本次证明。

[轻量JSON](../knowledge-base/public-native-faults-20261103.json)保留最终报告、哈希、关闭事实及先导试验暴露的诊断遮蔽。原始驱动hash与验收批次绑定；错误分类的后续扩展另由离线用例验证，不将所有错误类别都算作实测。全部N01–N25、生产Runner在求解中退出和复杂几何仍未完成，不因这15例通过整体勾选。

最终服务/Worker/驱动/文档/登记组合118项通过（103.18s），官方SDK与原始stdio组合13项通过（12.90s）；映射validate和A1校准门禁有效。测试集合不相加作全仓结论。

## 官方中止自动时序探针（2026-11-04）

`test/support/validate_solver_abort.py`只用于受控验收，不增加生产MCP/GUI停止接口。显式运行：

```powershell
python test/support/validate_solver_abort.py --run-cst --cst-exe "D:/Program Files (x86)/CST Studio Suite 2022/CST DESIGN ENVIRONMENT.exe" --source "已验证的Pillbox源副本.cst"
```

先使用测试专用几何约束生成小网格processed副本，再建立Managed Worker。桥接使用该安装的bundled Python及python_cst_libraries；按启动器持久身份找到唯一子DE，核实PID、创建时间、程序路径并保留WinAPI进程句柄，再通过`connect(pid)`和`get_open_project(path)`检查精确工程。禁止connect_to_any/active_project或新建额外CST。`--bridge`是内部子进程参数，校验父PID、artifacts位置及会话工程，不是任意工程控制入口。

在桥接ready后才提交任务；观察本会话生命周期的Start调用并通过官方`is_solver_running`确认运行后，独占创建并fsync中止意图，再只调用一次`Modeler.abort_solver`。已有意图（含截断/未知回执）或并发预约均不重发；响应缺失保留unknown。连接及触发等待分别60/90秒，桥接退出10秒有界；这些不是正常求解总时限。桥接通信卡住时只可结束本轮Python桥接，不结束CST或其进程树；原生仍经标准stop/严格失败退役核验。

要求被中止任务无成功指标/快照，实际分类限Start返回0、Start自身异常或Start返回1但无可读结果；三者分别留档。正常关闭后才能从未改动的processed新建Worker，要求Frequency/RQ及成功快照、两任务总计两次Start、两个子项目会话均标准关闭、源及processed hash不变。最终报告保留驱动hash；原始场/网格在任务结束并核实路径后清理。正常中止不能保证自然触发Start=0或Start抛异常。

首轮`solver-abort-805b67b3`中止和新Worker求解成功，但驱动总目录会话查询漏掉两个子项目，整轮报告保持失败；已修正并增加离线回归，不改写首轮为通过。复验`solver-abort-b632e158`通过：单次abort返回True，实际Start=1无结果，随后新Worker恢复Frequency=1147.45580535672MHz、Z轴R/Q=224.694610020595Ω；两次Start、两会话标准关闭、源/processed hash不变。轻量事实见[中止记录](../knowledge-base/solver-abort-20261104.json)。

替代任务保留received-unadopted，不将Worker层成功当上层算法已采用。只覆盖solver-running触发，不代表所有内部阶段。真实运行后仅补了CLI外部路径失败处理的写入边界，离线反例已验；native报告保留当时driver hash，不改写成最新字节实测。正常副本5个伴随目录已清理，首轮失败证据也保留。
