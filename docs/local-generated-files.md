# 本机配置与生成文件

`.gitignore` 排除本机 `config/current.ini`、该文件的临时/备份副本、`config/*.local.ini` / `*.local.json`、`.env` 本地变量，以及 Python 缓存、虚拟环境、构建目录、运行产物与已约定的根目录自动报告。

`config/default.ini`、`config/project.example.ini` 和 `.env.example` / `.env.template` 继续允许入库。缺少 current.ini 时，GlobalConfigManager 从 default.ini 初始化并保存本机配置。机器安装路径、最近项目等不再随提交传播。

current.ini 已从索引移除，磁盘原文件保留；不再依赖单机 skip-worktree 标记。此索引删除需随之后的提交一并提交，才能在其他检出中生效。

Git 忽略规则只约束未跟踪文件。历史已经提交的验收 XML/JSON、模型和数据不会因新增规则自动退出版本跟踪；本次不批量删除历史验收资料。未使用全局 *.cst、*.json、*.ini、*.xml 规则，以免掩盖新模型夹具、配置模板和文档数据。

验证：git check-ignore 核对本机配置/运行产物命中及模板/测试夹具不命中；文档索引专项校验链接和符号，不代表实际 CST 验收。

## 历史验收清理（2026-10-28）

按用户要求清理artifacts中未跟踪、可再生成的CST模型副本及原生求解数据库，共2925份、75.04 MiB。删除前进程快照未见CST/Python/pytest进程，逐文件核实绝对路径位于artifacts内并排除Git跟踪文件和符号链接。保留报告、日志、宏、参数及真空域掩码/场TSV；原始求解产物现已不完整，需要重新生成，旧报告不能被当作仍可访问的完整原始数据。清单见artifacts/history-cleanup-20261028.json（不保证随Git迁移）。

清理未改变程序功能和测试夹具；工作区原有11份历史证据删除状态不属于本轮新删除。用户原工程及temp/testman未处理，不因没有进程就推定其为可删验收副本。
