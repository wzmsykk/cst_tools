# Controller / GUI退出与CST真实行为

后续采用标记补写已完成，见[采用对账](../docs/checkpoint-adoption-l5.md)；本条保留首次发现及其当时边界。

2026-10-24，CST2022.5，Pillbox cell=8两任务副本串行。
实际GUI Python结束不影响独立Runner完成任务；新MainWindow连接同一Runner，不自动重复提交。使用offscreen而非现场视觉验收。
实际Runner Python结束后，已启动CST可继续完成当前Solver，并等待ACK；重启Runner通过真实Completion/received核验与显式恢复接收，不强杀CST。
Runner原进程死亡导致Popen退出观测丢失，不能依据日志里的exit0补造可信退出码；已死且证据核验后显式放弃与采用有效结果是独立事实。
新发现：IDLE标签可能先于执行线程释放，服务器仍以409阻止start；新增execution_active运行时快照并延迟GUI就绪状态。
新发现：归档目录已移动但receipt旧路径尚未更新，原CST结果未丢失却不能进入续跑。现用既有同Task/Session归档索引＋原快照哈希重绑定，坏证据不猜路径、不重算。
真实检查点已确认但adopt标记前退出时，恢复以pending_index=2跳过两项，Solver总数仍2；receipt仍为acknowledged，历史采用事件补写未实现，不将标记滞后解释成计算未完成。
部分日志在模型正常批退出之后出现The handle is invalid字样；本轮该会话仍有有效回执及Python观测退出0。不以孤立日志文字推断崩溃或解释历史退出1，其具体Windows句柄来源未定位。
证据与范围见[真实退出验收](../docs/controller-exit-l5-acceptance.md)；artifacts不保证随Git迁移，清理后原模型/场需再生成。
