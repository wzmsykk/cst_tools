# 本机配置与生成文件

`.gitignore` 排除本机 `config/current.ini`、该文件的临时/备份副本、`config/*.local.ini` / `*.local.json`、`.env` 本地变量，以及 Python 缓存、虚拟环境、构建目录、运行产物与已约定的根目录自动报告。

`config/default.ini`、`config/project.example.ini` 和 `.env.example` / `.env.template` 继续允许入库。缺少 current.ini 时，GlobalConfigManager 从 default.ini 初始化并保存本机配置。机器安装路径、最近项目等不再随提交传播。

current.ini 已从索引移除，磁盘原文件保留；不再依赖单机 skip-worktree 标记。此索引删除需随之后的提交一并提交，才能在其他检出中生效。

Git 忽略规则只约束未跟踪文件。历史已经提交的验收 XML/JSON、模型和数据不会因新增规则自动退出版本跟踪；本次不批量删除历史验收资料。未使用全局 *.cst、*.json、*.ini、*.xml 规则，以免掩盖新模型夹具、配置模板和文档数据。

验证：git check-ignore 核对本机配置/运行产物命中及模板/测试夹具不命中；文档索引专项校验链接和符号，不代表实际 CST 验收。
