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

源码RunOverview.update读取检查点并写run.json/summary.md，RunOverviewHandler截取首ERROR，rebuild_log_index只索引/补旧摘要。公共单次settings.kind=simulation不展示HOM覆盖，任务结果定位到execution-index.json；不能从其它运行的HOM账本推断单次成功。

[原批次完整记录](archive/20261103-semantic-review/readable-log-directories.md)保留10月14日543项及WinError5原现象，根因未定；现行回归见test/run_overview_test.py。真实共享盘权限、并发跨进程索引和现场占用仍需验，不以原子替换称强事务。
