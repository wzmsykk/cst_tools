# 一键导出失败诊断

2026-10-25。GUI默认扫频工作台顶部点击“导出失败日志”，无需先恢复任务或连接在线Runner。项目必须已经选择且本机可读。按钮直接在项目diagnostics目录生成“项目名-failure-时间.zip”，完成后在状态区和日志中显示完整路径，按钮提示也保留该路径；把该ZIP复制到需要排查问题的电脑即可。不会发送网络消息或自动上传，不改变项目/Runner/Worker运行状态。

导出使用独立Qt线程，按钮期间禁用以避免重复；完成/失败重新启用，磁盘满等错误显示原因而不伪造成功。正在导出时GUI拒绝直接关闭并提示等待，避免销毁仍运行的线程；不会因此请求停止CST。按钮保留在默认扫频结果页顶部；原始.log/JSONL入口放在详细运行信息页。失败消息提示该入口；成功或运行中也可手动导出。

## 包含范围和来源

1. control/status.json和project.json；显式排除含认证数据的endpoint/其他控制文件。项目project.ini、params.json、pps.json等轻量设置（若存在）。
2. 优先按持久状态log_directory选择当前run；附带log_history最后一条上下文。无法定位时退到logs目录名排序的最新目录，并在manifest声明选择方式，不把它声称为精确失败运行。
3. run下应用.log/JSONL、运行摘要、Worker诊断/失败JSON、生命周期日志、资源采样和接收记录。没有status run_id时尝试读取选中run.json的run_id并记录来源。
4. 与run关联的会话temp/worker_*目录：任务上下文、v1任务/Completion/ACK、StopAck/close.receipt、close-verification、任务撤销表达式、宏、CST日志及worker-input/Result/output.txt和progress.log。无run会话映射时仅按时间选最新三个会话，明确标出降级选择。
5. 最新三个预处理探针的轻量输出，含stage.txt、completion.txt、parameters.txt等；覆盖Worker创建前失败。schema3项目paths.temp_dir可在项目内自定义；项目外temp不读取，标出限制。

不收集.cst模型、三维场、大型求解数据库或全部result树；不会沿诊断文件中的任意artifacts路径去读项目外文件。文件缺失/权限错误、配置损坏及输出已清理均尽量形成部分诊断包，manifest列出不可用项目。包本身含真实本地路径、参数表达式和日志内容；没有通用自动脱敏。当前实现是本地文件导出，不是远程Runner文件下载接口。

## 清单和限额

manifest.json保存project/run/state/phase/error、run身份来源、源路径→ZIP内files/路径映射、实际捕获SHA256/大小、读取偏移、缺失/预算略过/截断和读取期间变化标记。README解释数据范围。记录身份和原路径，不用ZIP文件名推测任务；具体task/session仍由task-context、received及日志提供。

默认单文件最多4MiB、源文件内容合计64MiB、最多1000条候选文件记录，目录发现也有上限。优先CST原生/生命周期日志和协议/失败证据，资源采样优先级较低；候选发现到上限也可能略过后续文件，警告明确列出。超大文件仅收尾部原始字节，offset/truncated明确标记，JSON/JSONL尾片不保证是合法完整文档，不声称完整日志都已导出。ZIP压缩大小和manifest额外开销不包含在64MiB源内容上限内。

活跃文件采用尽力快照，不锁住求解器；stat变化会标记，不提供跨文件事务一致性，也不能仅据包内历史状态认定CST已关闭。临时压缩/发布失败清理本轮临时和部分输出；同名既有包不覆盖。用户关闭整个进程/系统掉电仍可能留下.export-*.tmp，不能当成有效ZIP。导出本身不是恢复检查点，不能用它自动续算。

## API与实际验证

csttool.diagnostic_bundle.export_failure_bundle(project, *, file_limit=4*1024**2, total_limit=64*1024**2, max_files=1000)返回path/bytes/run_id/files/warnings；files是清单记录数，包含缺失/略过，非全是成功复制数。GUI DiagnosticExportThread运行该函数，MainWindow.exportFailureLogs/_diagnosticsFinished负责按钮和反馈。

回归80 passed（36.70s），报告artifacts/diagnostic-export-gate-20261025.xml，含导出/Qt/结构化日志/日志恢复/主窗口/Runner；追加长日志及最终专项12 passed（1.21s），diagnostic-export-focused-20261025.xml，包含重叠。初轮9 passed/1 failed为测试数据未耗尽所设预算，修正夹具预算后复验；另一次文件名错误未收集测试，不计通过。

实际读取旧真实验收目录batch-restore-real-062f861b生成103232字节ZIP：run_id=e3bbe85719674f86bdf0461fd1d32e3a，70条记录中60份收录、10份不可用，含原生cst.log/lifecycle/close.receipt且无模型/场；这些原始模型在此前已清理，未将缺失隐藏。摘要artifacts/diagnostic-export-real-files-20261025.json；artifacts不保证随Git迁移，本轮未启动CST或操作原工程。

剩余边界：没有现场远端共享目录/文件锁/掉电验收，也没有桌面视觉验收；Qt测试证明异步交互与退出保护，不证明不同DPI/字体的实际显示效果。导出速度仍取决于磁盘/网络映射盘响应，64MiB限制不是文件系统调用的硬总超时。

最终文档/日志索引3 passed（0.86s），artifacts/diagnostic-export-index-final-20261025.xml；初轮索引跨文件符号放入首源码列不符合检查约定，已修正映射后复验。已完成的本轮pytest临时目录清理，保留轻量XML和实际导出示例；未提交或打包。

2026-10-25：一键导出补充save/csv下hom_scan_checkpoint.json、scan_manifest.json、hom_scan_results.csv及save/standard_batch_checkpoint.json，Worker补充recovery-l1.json和recovery.json。检查点与退役证据优先收集，沿用限额和截断标记；导出不等于可自动恢复或标准安全退出。对应导出/恢复/索引27 passed（3.19s），artifacts/hom-recovery-bundle-20261025.xml，未启动CST。
