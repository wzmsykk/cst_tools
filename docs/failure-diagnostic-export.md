# 一键导出失败诊断

2026-10-25。GUI默认扫频工作台顶部点击“导出失败日志”，无需先恢复任务或连接在线Runner。项目必须已经选择且本机可读。按钮直接在项目diagnostics目录生成“项目名-failure-时间.zip”，完成后在状态区和日志中显示完整路径，按钮提示也保留该路径；把该ZIP复制到需要排查问题的电脑即可。不会发送网络消息或自动上传，不改变项目/Runner/Worker运行状态。

导出使用独立Qt线程；运行中按钮可请求协作取消，不销毁活跃QThread，完成/失败后复位。关闭编排等待导出安全结束；磁盘满等错误不伪造成功，不因此停止CST。按钮保留在默认扫频结果页顶部；原始.log/JSONL入口放在详细运行信息页。失败消息提示该入口；成功或运行中也可手动导出。

## 包含范围和来源

1. control/status.json和project.json；显式排除含认证数据的endpoint/其他控制文件。项目project.ini、params.json、pps.json等轻量设置（若存在），以及save/csv下HOM检查点/清单/CSV与save下标准检查点。
2. 优先按持久状态log_directory选择当前run；附带log_history最后一条上下文。无法定位时退到logs目录名排序的最新目录，并在manifest声明选择方式，不把它声称为精确失败运行。
3. run下应用.log/JSONL、运行摘要、Worker诊断/失败JSON、生命周期日志、process-identity、recovery-l1/recovery记录、资源采样和接收记录。没有status run_id时尝试读取选中run.json的run_id并记录来源。
4. 与run关联的会话temp/worker_*目录：任务上下文、v1任务/Completion/ACK、StopAck/close.receipt、close-verification、任务撤销表达式、宏、CST日志及worker-input/Result/output.txt和progress.log。无run会话映射时仅按时间选最新三个会话，明确标出降级选择。
5. 最新三个预处理探针的轻量输出，含stage.txt、completion.txt、parameters.txt等；覆盖Worker创建前失败。schema3项目paths.temp_dir可在项目内自定义；项目外temp不读取，标出限制。

不收集.cst模型、三维场、大型求解数据库或全部result树；不会沿诊断文件中的任意artifacts路径去读项目外文件。文件缺失/权限错误、配置损坏及输出已清理均尽量形成部分诊断包，manifest列出不可用项目。包本身含真实本地路径、参数表达式和日志内容；没有通用自动脱敏。当前实现是本地文件导出，不是远程Runner文件下载接口。

## 清单和限额

manifest.json保存project/run/state/phase/error、run身份来源、源路径→ZIP内files/路径映射、实际捕获SHA256/大小、读取偏移、缺失/预算略过/截断和读取期间变化标记。README解释数据范围。记录身份和原路径，不用ZIP文件名推测任务；具体task/session仍由task-context、received及日志提供。

默认单文件最多4MiB、源文件内容合计64MiB、最多1000条候选文件记录，目录发现也有上限。先为control及当前/最近run主日志和元数据保留候选/写入预算，再处理Worker原生/协议证据；资源采样优先级较低；候选发现到上限也可能略过后续文件，警告明确列出。超大文件仅收尾部原始字节，offset/truncated明确标记，JSON/JSONL尾片不保证是合法完整文档，不声称完整日志都已导出。ZIP压缩大小和manifest额外开销不包含在64MiB源内容上限内。

活跃文件采用尽力快照，不锁住求解器；stat变化会标记，不提供跨文件事务一致性，也不能仅据包内历史状态认定CST已关闭。临时压缩/发布失败清理本轮临时和部分输出；同名既有包不覆盖。用户关闭整个进程/系统掉电仍可能留下.export-*.tmp，不能当成有效ZIP。导出本身不是恢复检查点，不能用它自动续算。

## API、取消与证据

`export_failure_bundle(project, *, file_limit=4*1024**2, total_limit=64*1024**2, max_files=1000, cancel_check=None, progress=None)`返回path/bytes/run_id/files/warnings；files是清单记录数，包含缺失/略过，不全是成功复制数。cancel_check为真抛ExportCancelled，progress报告discover/capture阶段。GUI DiagnosticExportThread及MainWindow.exportFailureLogs/_diagnosticsFinished负责线程、取消和反馈。

发现时优先预留control及当前/最近运行主日志/元数据名额；写ZIP再次按核心→原生→其余/资源优先级处理。先写入候选的检查点不代表其字节一定早于原生日志；额度耗尽可略过，必须看manifest，不能承诺所有文件全包含。

[原批次完整记录](archive/20261103-semantic-review/failure-diagnostic-export.md)保留10月25日实际旧文件导出及11月2日优先级/取消修正过程、原始测试数字。现行测试见test/diagnostic_bundle_test.py和GUI导出/退出用例。没有远端文件下载、通用脱敏或磁盘调用硬超时；部分诊断包不是可恢复工程。
