# 任务参数恢复与收尾等待

2026-11-03按生产模板及ManagedCSTWorker核对。[复审前批量全表版本](archive/20261103-semantic-review/parameter-restore-close-budget.md)保留原测试；旧“恢复所有203/208项参数”不是现行热路径。

当前只读取本任务参数的存在性和原表达式，跳过表达式完全相同项；setter前记录可能已修改的前缀。恢复仅对已尝试、原先存在的名字批量StoreParameters，再逆序删除尝试新增名字，核对这些名字，不遍历全工程。Solver已返回成功时保留结果，不用回滚/Rebuild清掉场。详见[任务级撤销与真实副本边界](task-parameter-undo.md)。

恢复副本用于旧会话安全收尾；失败新Worker从已预处理基准建立，通常processed.cst，以项目实际路径为准。确认覆盖、已采用结果及成功快照保留；正常成功任务上限轮换仍可显式接力同槽确认快照，不跨槽继承独立参数点。

ManagedCSTWorker.STOP_TIMEOUT=600秒。第一次进入stop的实际收尾建立单调期限，后续Manager清理共享剩余预算；request_stop只写意图，不限制阻塞Solver时间。预算外迟到但有效的关闭可再次核对，缺证据则立即保留恢复状态。独立显式恢复的会话预算是另一操作，不是自动重复stop预算。

lifecycle.log只截取有界尾部，完整末行变化时发布阶段；日志不延长预算，不替代close回执/StopAck/快照/进程证据。关闭按[协议](minimal-python-vba-protocol.md)返回批执行器，不重复Save/Quit或求解补元数据；普通退出拒绝1，严格HOM失败退役不改判标准成功。

本页无新实测。旧208项全表真实验收与后续任务级撤销真实验收分别保留，不能据操作数量变少宣称墙钟提速；复杂CAD、零参数真实故障及数值不收敛等按原门禁继续。
