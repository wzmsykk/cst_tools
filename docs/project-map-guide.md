# 项目定位与变更工具

状态：实施草案，尚不可作为已验收工具使用。计划中的权威映射为 `docs/project-map.json`（尚未建立），结构由[Schema](project-map.schema.json)约束；当前[feature-index.md](feature-index.md)仍为现行手工索引，尚未迁为派生视图。下列命令是目标用法；契约文件缺失时不能完成查询。架构和全量迁移规则见[实施计划](project-documentation-tooling-plan.md)。工具不替代API正文、动态运行或CST验收。

## 日常入口

```powershell
python scripts/project_inspect.py query --feature F135
python scripts/project_inspect.py query --path csttool/native_definition_builder.py
python scripts/project_inspect.py query --symbol run_new_definition
python scripts/project_inspect.py query --question "quiet"
python scripts/project_inspect.py changes --base HEAD
python scripts/project_inspect.py delete csttool/native_definition_builder.py
python scripts/project_inspect.py graph --path csttool/native_definition_builder.py --limit 40
python scripts/project_inspect.py inventory
python scripts/project_inspect.py tools
python scripts/project_inspect.py validate
```

输出为JSON，包含Git提交、工作区、契约hash、命中原因、全部阅读入口、测试候选、登记关系和未知。问题查询只是字面匹配；多个选择器按并集聚合，不是AI语义检索。符号重名列出全部声明和歧义，不凭名字挑选。路径或功能未映射返回退出2；结构或运行错误退出1；正常查询退出0。delete始终是预检，safe_to_delete=False，不删除任何文件、不授权删除。

inventory包含全范围文件分母及每个旧路径→保留路径/责任/处置记录；根目录分类不代表功能关系已审查。vendor、二进制、模型、跟踪的历史artifacts与不改动的utils分别登记；无显式F关系的文件显示unmapped，不能当无影响。

graph输出AST候选和显式登记关系，提供总数/截断标记；import、注册、调用候选和真实分发分开。无法静态决定的接收者、反射或注入目标保持未知；不会导入被分析模块。跨语言VBA/COM/原生库内部不由Python AST解析器解释，须读登记合同及真实验收。

## 修改与同步

1. 检查工作区，查询功能/源码/消费者和必读合同；缺口先补查，工具结果不代替判断。
2. 修改实现、对应API/设计/测试和project-map.json。每个source的symbols属于该文件，不能将多个文件的符号混在第一个源码下。
3. 当前状态、TODO与证据按AGENTS同步；文档角色不明确的条目标为unreviewed，不按文件名自动升级为现行规范。
4. 显式生成派生索引：`python scripts/project_inspect.py render --write`。不带--write只打印预览；查询及validate不自动重写索引或人工关系。
5. 运行validate和`test/documentation_index_test.py`、对应功能测试。source_fingerprints仅记录采集时输入；变化提示复审，不自动刷新关系或宣布语义有效。完成复审后显式更新相应采集hash及证据。

查询、inventory、graph、changes、delete、tools和validate均不运行测试、构建、CST、COM、部署或网络，不创建缓存文件。建议将需要保留的JSON通过调用方显式重定向到本轮artifacts；工具不代替调用方清理这些报告。render --write只更新固定派生Markdown；构建/真实探针仍独立显式执行。

## 覆盖和错误边界

路径/符号/章节有效、派生索引一致，只是结构事实。工具的动态目标列表可以是候选或未知；没有运行记录就不标记runtime_proven。人工登记关系有适用基线，内容hash变化只提示复审。旧记录属于原日期/版本，不因本次生成工具而成为新代码验收。

文档清单保留已核角色与未核角色，不把自动分类当完成人工整理。工具清单中未审查的外部副作用入口明确禁止自动调用；参数提取只是AST事实，不证明参数组合安全。范围外、缺失或历史文件仍显示原因，不静默按测试选择器忽略。
