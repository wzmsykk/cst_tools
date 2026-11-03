# ANTLR VB6 离线 PoC 验收

> 适用性复审（2026-11-03）：原批次实施/故障/验收记录；旧当前、未提交、待做及现场进程状态不代表本次实时事实。现行实现见[当前状态](current-status.md)、[功能索引](feature-index.md)及对应API；不重算或追认旧证据。

2026-11-03。只进行词法/语法解析，不执行宏、不启动CST。**能发现一般语法错误，但接受了原始Zrange故障形态，不能独立作为WinWrap语法门禁。**

工具：[antlr_vb6_poc.py](../test/support/antlr_vb6_poc.py)，测试：[antlr_vb6_poc_test.py](../test/antlr_vb6_poc_test.py)，轻量证据：[JSON](../knowledge-base/antlr-vb6-poc-20261103.json)。完整下载/生成文件和报告位于artifacts/antlr-vb6-poc-20261103，不保证随Git迁移；固定成功历史片段保存在test/fixtures/antlr-vb6-poc/retained-history.vb，来源/hash见JSON。

## 实验与判定

固定grammars-v4 commit b96e04db9d54bb313e542cc3e6ee913900a21520，ANTLR生成器及Python runtime均4.13.2，Python3.12.7，生成使用本机已有JDK25.0.3。依赖仅pip --target安装到本轮artifacts/runtime，没有修改requirements或全局Python环境。下载URL、输入hash与生成命令保留在证据中。

检查器同时收集lexer/parser错误、检查EOF，不能因为ANTLR返回树就报告通过。所有样本分别运行默认自适应LL和SLL快速路径；SLL发生ParseCancellationException后用LL重试解析，不执行被检查代码。五次预热重复检查本批判定一致；两份完整历史均触发回退。首次解析与默认模式会逐步预热共享DFA缓存，结果具有运行顺序依赖；这里是本机观察，不是稳定性能承诺。

共15样本，4个明显语法错误均拒绝；原始Zrange、0+版本与Call候选均接受。原始反例是按现场语句重建的最小完整模块，不是原失败宏的逐字节副本；0+历史另有保留候选的完整片段包装对照。Call候选未在CST验证。重复声明和不存在的CST方法均接受，说明类型/作用域检查不在本PoC能力内。中文、续行和ByRef数组样本只证明解析，未证明其运行效果。

## 性能结果

每格为最后一轮5次预热中位数（毫秒），包含分词与完整解析、不含import；重复次数少且本机负载波动明显。

|样本|解析判定|默认LL ms|SLL/LL ms|回退LL|
|---|---|---:|---:|---|
|body-not-executed|接受|34.967|0.583|否|
|zrange-original|接受|116.629|0.746|否|
|zrange-fixed|接受|111.621|0.827|否|
|zrange-call|接受|338.950|1.928|否|
|missing-quote|拒绝|0.976|1.273|是|
|missing-end-with|拒绝|0.569|2.510|是|
|missing-end-sub|拒绝|16.836|15.957|是|
|trailing-garbage|拒绝|84.300|85.464|是|
|unicode-continuation|接受|90.392|1.849|否|
|byref-array|接受|96.093|1.947|否|
|duplicate-declaration|接受|56.982|0.650|否|
|unknown-cst-member|接受|60.490|1.474|否|
|wwb-header|接受|106.360|0.884|否|
|retained-history-wrapped|接受|2459.118|2176.745|是|
|a1-fixture-wrapped|接受|924.097|888.880|是|

新Python进程启动、import并解析空模块的5次中位数为391.7ms；本进程首次import为66.9ms。两份完整历史分别1266/1588字节（含Sub包装），不能把短语句的毫秒表现推到整套Worker宏。较早轮完整历史默认中位数也曾约0.8–1.8秒，最后一轮存在约2.46秒样本；保留早期default-report.json，不选择最快数字作为结论。

## 诊断与未执行

缺引号返回lexer错误：包装后第4行、0基列4；缺End With在遇到End Sub时报parser错误；缺End Sub在EOF处报告；尾随@@@拒绝。位置可能是发现错误的位置而非根因位置。报告明确line_1based/column_0based；Sub包装增加两行，后续映射必须扣除包装。当前fixture记录完整包装源码，不把行号冒充原History顶层行号。

缺End Sub的错误文字在首次与缓存预热后有差异，判定未改变，诊断变体保留；测试不锁定整段消息。独立带Open/Print文件操作的合法源只被解析，标记文件不存在；测试也用临时绝对路径核对该事实。没有调用eval、exec或CST接口。

## 依赖与采用结论

Python runtime目录实测约1010KiB，生成文件目录约1919KiB，均含pycache/元数据；其中Python源码分别461/705KiB。生成输入共约2118KiB（含ANTLR jar与grammar）。Java只用于生成，后续本次Python解析及冷进程测量未调用Java；不等于未来发布包已决定包含这些文件。

runtime元数据包含typing条件依赖（Python<3.5），本机3.12无额外活跃依赖。parser grammar头部标MIT，lexer没有同样的文件头，runtime标BSD；完整分发许可仍需确认，未把源码/生成器/运行库加入生产发布。输入与生成文件目前仅供隔离实验。

建议暂不纳入生产必需依赖：它没有覆盖最重要的原生反例，完整历史仍可能回退并耗时秒级。W2可以在此结果上评估受限调用规则与声明检查，但不扩大成完整WinWrap编译器。更值得优先验证已安装的原生v9 NoUI入口，见[入口核查](winwrap-v9-installed-entry.md)；无论哪条轻量路径通过，CST参数注入、扩展方法和历史重放仍需少量宿主验收。

## 复现

首次准备（替换为本机已有Java路径，不安装系统组件）：

```powershell
python test/support/antlr_vb6_poc.py --directory artifacts/antlr-vb6-poc-20261103 --prepare --java "C:\Program Files\Java\jdk-25.0.3\bin\java.exe" --repeats 5
```

已有本轮生成文件时去掉--prepare和--java，仅本地Python解析。运行显式相关测试：

```powershell
$env:ANTLR_VB6_POC_DIRECTORY="D:\work\cst_tools\artifacts\antlr-vb6-poc-20261103"
python -m pytest -q test/antlr_vb6_poc_test.py test/documentation_index_test.py
```

未设置该环境变量时8项可选parser测试明确跳过，不把缺依赖当通过。相应生成产物需按固定版本重建。测试临时目录本轮结束后清理，保留轻量报告、夹具和约5MiB可复现实验依赖；没有原始场文件或模型副本。

最终相关验收：8项显式parser测试与2项文档索引共10 passed（6.89秒），报告artifacts/antlr-vb6-final-20261103.xml。该数字不包含CST/WinWrap原生执行。
