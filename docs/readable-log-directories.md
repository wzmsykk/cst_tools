# 可读日志目录、运行摘要和总览

2026-10-14。唯一ID用于关联，不代表可读名称；用户不必解析元数据才能看出新目录用途。

## 新运行

默认应用日志目录示例：

```text
项目/logs/
  index.md
  20261014-102140_HOM-500-1000MHz_续跑_c0aba273/
    summary.md
    run.json
    application.log
    application.jsonl
    events.jsonl
    tasks/<task_id>/attempt.json
    tasks/<task_id>/artifacts.json
```

目录包含北京时间（UTC+08:00）、用途/频率范围、新运行或续跑与短ID。Windows非法字符替换，短ID仅防重名；同秒同短ID冲突会创建带序号的新目录，不合并数据。run.json始终存完整run_id，不能用目录名当身份。

应用Backend将同一run_directory传给Manager，应用日志、任务索引和后续工件共用此路径。独立Manager创建“批量任务”目录，日志ContextLogger的run_id与run.json一致；标准stop更新其摘要状态。注入外部application_logger时不强制迁移调用者文件handler；默认应用logger才自动创建应用日志、首错误观察器及完整运行生命周期摘要。

续跑命名读取原scan_manifest的起止频率，不使用GUI默认范围；原清单不可读时命名为“续跑-原配置待确认”，不猜频率。配置实际恢复后刷新摘要settings。名称中的范围是运行请求，不是已确认计算覆盖。

## 直接阅读

- summary.md：工程、时间、用途、状态、续跑、配置、连续确认计算边界、计算窗口最高上限、模式/待处理计数、首个错误/原因/源码/诊断目录/恢复建议及文件入口。
- logs/index.md：按目录时间命名排序列出时间、用途、状态、首错误与摘要链接；无需逐个打开随机ID目录。
- 首错误只记录一次，完整异常与后续故障仍在log/JSONL。摘要消息与原因最多2000字符，原文件不截断。STOPPED仅显示“已结束”，不冒称CST求解成功；未记录错误也不代表验收通过。
- 状态变化读取当前HOM检查点coverage，旧检查点未提供该字段则显示未知，不能从最高模式频率猜覆盖。

摘要为轻量观测，不是恢复账本或计算成功契约。运行状态变化及HOM检查点保存后更新；Backend、Manager和扫描器共享同一摘要对象/锁，不周期性刷日志。JSON元数据/Markdown使用同目录临时文件+原子替换，不写半截索引；索引是可重建派生视图，不保证跨进程同时更新时的强一致。更新失败保留完整日志及控制状态，不通过摘要状态触发Solver操作。

## 旧目录

rebuild_log_index(project)只补总览及有旧run.json的目录中缺失的summary.md，不改名、不移动、不删旧目录，不覆盖旧summary，不改旧run.json或日志。没有元数据的目录仍列入总览，但只链接原目录；新运行自写摘要，索引不抢写。已有旧元数据仅包含project/run_id/创建时间时，缺失的用途、范围、状态及错误明确为未知；不读取巨大历史log猜测成功，也不把文件mtime当仿真时间。

旧目录中的Task/协议路径与工件引用保持原样。Task子目录仍使用唯一ID，job/参数与产物路径见attempt.json/artifacts.json；本批不改任务协议路径。总览/摘要的链接只提供入口，不保证旧日志/原始大文件仍存在。

## API、验收与TODO

RunOverview(project, run_id, purpose, resume=False, settings=None)创建/复用身份对应目录；update更新状态/摘要；RunOverviewHandler观察首个ERROR；rebuild_log_index仅索引已有目录。RunStore新增可选run_id，已有metadata不被覆盖。

离线测试覆盖可读命名/非法字符、身份复用与短ID冲突、旧目录原路径和字节不变、损坏元数据索引、首错误/源码/计算覆盖、默认Backend日志绑定及关闭清理。真实服务器日志权限、网络盘原子替换和多窗口最终索引一致性仍待验收。后续可增加GUI“打开运行摘要/总览”入口，不新增日志服务。

本批最终全套离线543 passed、19 integration deselected，报告artifacts/readable-log-directories-20261014.xml（不保证随Git迁移）。另测HOM检查点实时刷新摘要，确认日志目录与Manager任务目录共用完整身份/路径。测试临时目录已清理，未启动真实CST。

过程中两次既有文件操作出现Windows WinError 5：project.ini原子替换、结果目录归档重命名。后者代码保留原目录；单例及最终全套复跑通过。根因未确定，不能据此断定沙箱、同步软件或文件占用；本批没有增加盲目重试或强制删除来掩盖异常，服务器文件权限/占用压力验收仍需补充。
