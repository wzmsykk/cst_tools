# 任务级参数撤销与HOM热路径

2026-10-25。替代启动/每次成功时全量参数检查点和失败时全表恢复；历史全量版本的208项真实验收仍保留在[旧验收记录](batch-restore-real-acceptance-20261025.md)，不能代作新代码验收。收尾期限、回执v2及失败后从processed.cst启动的规则不变。

## 读写范围

CSTPMW_CaptureTaskParameters只遍历当前任务参数，按名称读取是否存在和原始表达式字符串。表达式文本与请求完全相同则不列入修改集合，也不调用StoreParameter；数值相同但表达式不同仍视为修改，不能把表达式求值后判断相等。HOM一般只查询nmodes/fmin/fmax三个名字，不再GetNumberOfParameters/GetParameterName枚举项目全部参数，也不在启动/成功后全量读取。

修改前收集名称、原表达式、存在性和请求值；任务名称按大小写无关检查重复，重复任务拒绝且不写参数。零参数/全部不变时修改集合为空。先完整写完并关闭任务撤销诊断文件，成功后才允许setter；采集/文件写入失败直接拒绝，尚未改变CST参数。

原诊断路径worker-input.cst.last-good-parameters.tsv保留，但内容已变更为CST_PARAMETER_UNDO_V2，首行magic，第二行session与TaskID，后续行name、任务前存在性（本轮WinWrap的CStr(Boolean)实际输出-1/0，分别表示存在/不存在）、原表达式（反斜杠/tab/CR/LF转义）。这不是旧版全参数TSV，不允许按旧格式读取，也不是可自动回放的崩溃恢复日志；活动任务身份/采用仍按既有协议与快照核验。新诊断manifest用task_parameter_undo键。旧会话宏不热替换；旧文件继续作为历史证据保留。

## 部分执行及失败恢复

在每个setter前先推进appliedParameterCount，记录该项可能已写入；setter发生部分副作用后抛错也纳入恢复。停止若发生在下一个setter前，只恢复之前尝试的前缀；尚未写入的项不动。

恢复仅将尝试过且原先存在的参数组成精确长度String数组，批量StoreParameters恢复原表达式；随后倒序删除尝试过且原先不存在的参数。空集合跳过批量接口。核对这些名字的表达式/存在性，不遍历/删除其他工程参数。不把未修改参数或历史重建的其他设置当作参数事务一并回滚；这是任务参数撤销，不是完整工程事务。结构、历史或复杂模板的副作用仍须按CST既有边界独立处理。

成功快照完成后撤销记录在内存失效，下次任务重新按当时模型取原值；不会回到首次预处理值。Solver已成功时的后处理/Backup失败或停止仍保留求解结果，不恢复参数、不Rebuild清掉场；现行solverReturnedSuccess/activeTaskSolveReady门禁保留。恢复失败不发布正向StopAck；不靠求解重放修复元数据。失败Worker正常关闭核验后，新Worker仍从预处理基准启动，HOM确认覆盖/结果不清空。

## 日志和验收边界

parameter-checkpoint记录requested/changed；restore-parameters记录attempted；restore-batch记录实际恢复数，restore-delete记录删除数。阶段起止与600秒单次关闭期限不变。源码/假对端可检查操作顺序，不能替代真实WinWrap/CST语义；新版真实副本结果另在本轮记录。

## 本轮验收

新版真实CST 2022.5/WinWrap串行副本通过：artifacts/batch-restore-real-062f861b/report.json（passed=true）与task-undo-summary.json；原Pillbox源只读、cell8、nmodes1、480–530MHz，预处理副本含208项，其中200项为测试表达式。正常任务仅requested=3；故障任务requested=5、changed=3，fmin/fmax原表达式相同被跳过。实际撤销文件仅nmodes（原1）、probe001（原probe000 + 1）及新增probe_added；恢复批量count=2、removed=1，表达式/存在性验证通过。任务阶段没有全表枚举。首项成功快照前后哈希一致，失败Worker严格恢复退出4，随后Worker源为processed.cst且输入SHA一致，原任务重试成功；两次频率均503.49464359617MHz，Solver调用共2次。

无求解迟到关闭用例沿用2秒测试宏暂停及0.3秒测试预算：首次stop约0.359秒、第二次约0.032秒，随后退出0且同期限再次stop通过。生产600秒期限和退出1拒绝均不改。原工程/预处理基准未改，实际同权限CST清单为空；没有强杀。删除199个可再生成模型/原始场/缓存文件共24066340字节，保留轻量报告/日志/宏/参数/协议/cleanup.json哈希。原始数据已删，不能再用旧路径复核快照，需要重新生成；artifacts不保证随Git迁移。

注意本轮restore-batch约9秒、删除及验证约7秒，恢复入口至batch-return约21秒；此前全表小模型批量版本约19秒。本轮证明操作数量从全表收窄为任务修改项，并未证明总收尾墙钟显著加速。历史316秒为不同现场模型，不计算跨模型提速倍数。

离线专项137 passed（12.69s），报告artifacts/task-undo-final-20261025.xml；文档/日志索引及恢复6 passed（1.06s），task-undo-index-20261025.xml。首轮74 passed/1 failed/1 error为假对端ACK读取访问失败，保留task-undo-20261025.xml；未修改生产协议掩盖此偶发，也不以复验通过保证该问题永不再现。

本轮新发现：WinWrap实际CStr(Boolean)在撤销文件写出-1/0，而不是按名称猜测True/False；诊断说明/探针同步。没有新增运行时自动回放该文件的接口。未覆盖：零参数真实任务、setter部分写入后异常与采集文件失败的真实故障注入、任意复杂CAD副作用、Start=0/exit1。本轮直接故障为nmodes=0导致Rebuild=False；源码契约检查部分执行前缀和已成功Solver不回滚，不扩大为所有指令级中断已实测。

最终文档/日志索引复核3 passed（0.59s，重叠）；本轮pytest临时目录均清理。未提交、推送或打包。
