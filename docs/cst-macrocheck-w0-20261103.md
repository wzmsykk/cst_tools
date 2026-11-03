# W0：CST宿主内批量MacroCheckThis验收

> 适用性复审（2026-11-03）：原批次实施/故障/验收记录；旧当前、未提交、待做及现场进程状态不代表本次实时事实。现行实现见[当前状态](current-status.md)、[功能索引](feature-index.md)及对应API；不重算或追认旧证据。

日期：2026-11-03。本机CST 2022.5（文件版本2022,5,0,0），**核心宿主校准通过**：一个新3D副本、一次RunScript、14次MacroCheckThis，0次求解。无需人工确认完成检查及标准关闭。该结论不覆盖任意宏、完整WinWrap语言或Call形式的实际几何执行。

工具：[calibrate_cst_macrocheck.py](../test/support/calibrate_cst_macrocheck.py)，[离线回归](../test/cst_macrocheck_probe_test.py)，[轻量证据](../knowledge-base/cst-macrocheck-w0-20261103.json)。本轮通过目录artifacts/cst-macrocheck-84eeb1af；原始目录不保证随Git迁移，必要源码/hash/结果保存在轻量证据。未修改用户原工程，没有复制宿主授权材料。

## 执行与归属

复用既有run_new_definition：创建专用新MWS，固定宏首先报告modeler进程，父进程核对创建时间、安装路径及DE祖先，再解除身份等待，随后在同一次RunScript中批量检查。未使用全局Active3D或打开原工程；没有重建或执行待检查历史，没有调用Solver.Start。

主驱动设置本轮参数W0Base=2、L表达式`2 * W0Base`、R=2，再检查各完整模块。被检查程序与控制驱动分别保存，前者正文包含文件写入、改参数及真实历史命令，后者只调用MacroCheckThis、采集错误并保存空白参数工程。

## 原生结果

|样本|结果|证据/限制|
|---|---|---|
|写正文标记文件|接受|检查结束标记不存在；该Sub Main未执行|
|将L改成999|接受|主驱动检查后L表达式仍`2 * W0Base`；写参数正文未执行|
|明显未闭合表达式|拒绝|10586，Expecting ')'; Source定位包装第5行|
|原始Zrange故障形态|拒绝|10576，Unexpected text.; Source定位包装第5行的原始Zrange语句|
|0+前缀Zrange|接受|与此前实际执行正例的调用形态一致|
|Call .Zrange(...)|接受|仅证明本样本可编译，未实际执行或写历史；暂不替换0+|
|重复声明|拒绝|10519，Identifier is already in use.; 指向第二次声明|
|未闭合With|拒绝|10587，Unterminated block statement. 'With'; 在End Sub发现错误|
|中文字符串|接受|源代码通过统一ChrW字符串辅助传入|
|CST RestoreDoubleParameter调用|接受|本轮3D宿主上下文能解析该调用；不是表达式值/引用关系的完整验证|
|含非法历史文本的AddToHistory外层|接受|证明检查外层字符串表达式不检查字符串内部程序；该历史没有执行|
|Xrange/Yrange的0+调用|接受|是语法覆盖，非X/Y物理求解或几何构造验收|
|保留的完整历史片段包装|接受|源来自前批受控候选，未运行其中Create/设置；不取代G03或Rebuild验收|

原始Zrange是按现场错误语句重建的最小完整模块，不是原失败宏逐字节副本。相同形态在ANTLR通用grammar中被接受，在本轮真实WinWrap中被拒绝，明确了离线通用解析不能代替原生门禁。

## 错误诊断与源映射

MacroCheckThis返回ErrObject，实际获得Number、Description、Source。原始反例的Source为：

```text
[*xMacroRunThis4*#5]  .Zrange ((-RestoreDoubleParameter("L"))/2), (RestoreDoubleParameter("L")/2)
```

本轮Source可提取临时模块、1基行号与原始语句；没有从ErrObject取得列号，不发明ErrorLine/Column属性。工具的parse_error只解码已观察格式，遇到其他格式保留原文并返回未知位置，不保证后续版本格式相同。

包装为语言注释、Option Explicit、Sub Main三行，历史片段的行映射需减3；通用完整模块则直接对应保存的样本.bas行号。Source定位的是解析发现位置，缺End With时定位End Sub不能误称根因就在End Sub。

## 正常收尾与未执行范围

主驱动SaveAs完成后写nonce完成标记，调用方对已绑定对象正常Quit、释放project及application COM引用。wrapper日志记录两次关闭返回；进程退出码0，session-status的exit_confirmed=True、active_pids=[]，结束后CST进程列表为空。整个被观察会话约32.98秒，包含启动/保存/关闭，**不是14次检查本身的耗时**。

正文文件标记缺失与L表达式保持是本轮Sub Main不执行的独立观察；不能扩大为任意对象初始化事件均无副作用。只检查Sub模块，未覆盖Object_Initialize、类模块、插件回调和所有宿主扩展。独立NoUI的评估到期结论保留，本轮复用的是CST自己正常工作的宿主，不证明NoUI独立授权问题已解决。

## 首轮问题及修复

1. 受限环境COM激活返回E_ACCESSDENIED，未执行宏，辅助进程退出1且无残留；随后按用户授权在正常用户环境运行。
2. 第一实际宿主批次490aa5b7可调用检查器，但样本语言头漏了前导注释符，全部10586拒绝于第1行。它不计正反例通过；会话正常退出。补充包装回归后复验，84eeb1af通过。
3. 同样的未执行NoUI样本包装也已修正；NoUI尚未重跑，不把该源码修复算作初始化成功。

因此不是整个工作批次只有一次CST启动：两次真实批次均独立、串行、正常关闭；最终通过批次只用一个副本和一次RunScript。各自证据保留，不用后续成功改写首轮。

## W0收口与W1边界

本次要求的MacroCheckThis可调用、原始反例/正例区分、错误诊断、正文不执行与正常退出已验，可进入W1最小发射器实施。检查需要在CST宿主内运行，不能称为启动CST前离线编译；后续优先在生成器/模板变化时批量检查，不为每个HOM窗口启动CST。

尚未完成：Call形式的实际执行与重建持久性、通用数组/ByRef扩展、物理行/续行硬边界、所有初始化副作用和W3发布门禁。W1继续保留已验裸调用加0+及24字符保守字符串分段，不能仅凭Call编译通过就全面替换。

## 最终离线回归与清理

包装/诊断/完成判定及NoUI既有回归与文档索引共13 passed（0.98秒），报告artifacts/cst-macrocheck-w0-final-20261103.xml；该数字与14项真实宿主样本分开计数。首轮及通过批次的空白.cst和伴随目录在确认任务退出后清理，保留宏、逐项源码、原始诊断、参数表达式、身份与hash；模型需要时重新生成。pytest临时目录清理，轻量JSON随Git保存。
