# 失败诊断导出边界

2026-10-25。实现和实际证据见[导出说明](../docs/failure-diagnostic-export.md)。现场排查需要同时取得Python运行状态/任务归属、CST生命周期与Result/output.txt/progress.log、ACK和close.receipt，单份application.log不能证明求解根因或物理关闭。当前GUI可一键生成本地ZIP，manifest将源路径/运行身份/捕获SHA与缺失/截断对应。

已有真实验收日志导出103232字节，60份收录、10份不可用；原始模型已清理不掩盖缺失，不重新求解。大日志只保留尾部时JSON/JSONL不一定完整，接收端应按manifest offset/truncated处理，不把它当完整结构化流。导出不锁定活跃文件或CST，不代表跨文件一致快照/安全关闭证明。端点token文件排除，但日志和表达式可能包含用户实际路径，未做通用自动脱敏。远程物理主机不能仅凭同名桌面路径读取，需要从该主机复制导出的ZIP；当前没有远程文件下载API。
