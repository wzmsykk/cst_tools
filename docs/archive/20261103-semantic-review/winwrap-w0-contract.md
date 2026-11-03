> 2026-11-03语义复审归档：基线2705935的完整原文，只重定位相对链接；旧当前/下一步/验收只属于原时点。现行入口：[对应专题](../../winwrap-w0-contract.md)。

# W0：WinWrap 调用、CST 持久化与诊断核查

日期：2026-11-03。**静态核查完成，原生能力校准未完成**；本轮没有启动CST、求解或修改原工程。依据是随本机CST 2022保留的WinWrap v9三份CHM、CST宏概述和3D Application Object帮助，以及现行生成器源码。来源和topic hash见[来源清单](../../../knowledge-base/winwrap-w0-sources-20261103.json)。后续实施遵循[W0–W3方案](../../winwrap-codegen-safety-plan.md)。

## 1. 语言与调用规范

语言profile固定为`#Language "WWB-COM"`，不能采用WWB.NET/Compiled、VB.NET或Excel VBA代替。WinWrap网站同时列出不同语言/宿主开发接口；网站当前版本不能覆盖本地v9定义。[官方语言入口](https://winwrap.com/web2/doc-basic/)、[版本10及编译选项](https://www.winwrap.com/web2/solution/WinWrap-Basic)。

下表的topic均位于`wwb9_000.chm::/wwb9_000htm/`，不是根据通用VBA经验推定。

|构造|文档约束|本项目生成规范|
|---|---|---|
|Sub/丢弃返回值的调用|`Call name[(arglist)]`或`name [arglist]`；省略Call的Sub实参表不能整体括号包围；doc_call_instr.htm|区分语句调用与返回值表达式。当前裸调用保持既有已验形态；`Call obj.Method(...)`作为待宿主校准候选，不能立即全量替换|
|函数返回值|需要返回值时用于表达式；Call形式会丢弃返回值|`If Not AddToHistory(caption, history) Then ...`与无返回值setter分开建模|
|With|`With objexpr … End With`内`.method/.property`属于该对象；doc_with_stmt.htm|对象身份在进入块前确定；不把文档Project Object分类当作可用的全局Project变量|
|参数/数组|非ByVal且实参仅为变量时按引用；表达式不是同一引用语义；数组必须引用，不能按值；pop_paramz_popup.htm|字符串、数值表达式、数组变量分别发射；不能为统一格式给所有实参加括号，防止影响ByRef/输出参数|
|命名实参|命名实参后只能继续命名实参；pop_arglistz_popup.htm|首批发射器使用已验位置实参，不扩张到任意命名调用|
|声明|Option Explicit要求事先声明变量；doc_option_def.htm|固定声明表并检查大小写不敏感冲突。CST参数可自动成为Double变量，必须同时检查工程参数名与辅助变量名冲突|
|错误处理|每个过程独立On Error；默认错误终止宏；处理器执行期间再出错可能终止宏，除非Err已清；doc_onerror_instr.htm|先保存原始错误字段再独立清理；不能因外层有On Error就保证捕获所有编译错误|

CST[宏概述](../../../knowledge-base/vendor/cst-2022-vba-help/vba/vba_macro_language_overview.htm)明确提醒：工程参数自动作为Double变量暴露，局部同名会冲突，建议Option Explicit。此前文件句柄/参数重名不是单纯随机命名问题；W1应预留内部命名空间并在生成前核对参数表，不能只在生成器内部查重。

### 本次故障的精确边界

现行`definition_editing.render_history`把受限Python AST转换为WinWrap算术，并加`0+`避免裸多参调用首实参以左括号起始。已保留的真实记录说明原`.Zrange ((-RestoreDoubleParameter("L"))/2), ...`失败、加前缀版本成功，见[原验收](../../typed-public-acceptance-20261103.md)。Call文档支持其调用形态解释，但没有证明所有以括号开头的表达式都非法，也没有证明所有COM方法支持同一种替代形式。W1不得把局部观察提升成通用语法定理。

本轮未找到并核实统一的物理行/续行硬上限；当前24字符分段是实现的保守策略，不是WinWrap文档规定的长度。继续保留，W2用边界样本校准。自动引入临时变量也需先验证历史顶层声明作用域、重名和重放行为，不能直接作为已可靠修复。

## 2. CST 接口与持久化边界

依据[3D Application Object](../../../knowledge-base/vendor/cst-2022-vba-help/VBA_3D/common_vbaapp/common_vbaappapplication_object.htm)、宏概述及[A1逐命令允许表](../../a1-history-command-profile.md)。这里的“3D Application Object”是帮助中的对象类别，不是DE主窗口的全局活动工程选择保证。

|接口/类别|文档定义|设计与验证要求|
|---|---|---|
|AddToHistory(caption, contents) → bool|创建历史条目并立即通过VBA解释器执行内容；两者成功才True；前一块标题相同会被移除以压缩历史|不是纯检查或事务。False/异常不证明没有任何部分修改；候选不得发布。标题不能代替operation/revision身份；同标题合并须纳入重放检查|
|结构宏/结构设置|宏概述要求结构宏进入历史以便参数变化后再生成；DS不支持结构宏|几何、单位、背景/边界和首阶段求解/网格配置沿用现有历史profile；不得因setter直接返回就宣称重建持久。现代MeshSettings部分依赖V05校准，仍保留其证据等级|
|StoreParameters(names, values)|批量增加/修改参数，允许互相依赖及引用已有参数|参数表和历史分开。原样保存表达式字符串；前向依赖可以批量设置，不逐个求值后写常数；无文档依据将批量调用称为原子事务|
|RestoreDoubleParameter / RestoreParameterExpression|前者取数值，后者取表达式|数值计算与表达式持久化分开取证；不得用数值读回代替表达式读回|
|SetParameterDescription / DeleteParameter|修改说明/删除指定参数|单独核对保存后参数表；只删除本任务新增参数，不依赖历史回放自动复原参数集合|
|Rebuild → bool|处理History List重建结构，删除所有结果；返回是否重建成功|不能作为已有结果工程上的只读检查；G03只在候选副本验证|
|RebuildOnParametricChange(full, showError) → bool|处理历史更新结构；保留应在参数变化后保留的结果，删除其他结果|不等于保留全部结果；具体full/showError行为不能从名字额外推导，不拿它替换恢复协议|
|Save / SaveAs(path, include_results)|保存当前工程；SaveAs可选择结果|保存状态不证明历史完整、重放成功或场数据已随.cst复制；保留结果伴随目录边界|
|RunScript(scriptname)|读取脚本文件输入|不提供文档化纯编译返回或诊断字段。当前新3D对象仅用一次RunScript完成身份门禁和构造；二次调用未执行是本机旧实测边界，不是官方保证|
|控制宏/后处理|宏概述将通常用于后处理的控制宏与结构宏区分，不要求控制宏存历史|运行时积分与结果读取不进入结构历史；结果产物保存和来源绑定另核验，不能据此宣称所有模板设置均不受Rebuild影响|
|Quit|结构改变时存在保存例外|不是无条件不保存退出；继续正常保存/收尾/进程身份核验，不新增猜测的Quit(False)|

首批方法继续复用A1的51项命令及官方B编号，不复制另一套可漂移允许表。调用卡片字段为scope、调用类型、参数/返回、表达式/单位、历史要求、副作用、官方topic及校准证据；W1按需补入共享元数据。方法、target、自适应和Tet密度没有因此得到新live getter，继续遵守[验证器来源矩阵](../../cst-settings-verifier-design.md)。

## 3. 原生检查与诊断：区分脚本作者和宿主开发者

### 优先校准：脚本级 MacroCheckThis

WinWrap v9 WWB-COM语言帮助明确列出：

- `MacroCheckThis(MacroCode$)`检查代码、不执行该宏/模块；语法错误返回Err对象，无错返回Nothing。示例声明`Dim E As ErrObject`并读取`E.Description`。
- `MacroCheck(MacroName$)`检查指定名称的宏/模块，同样返回错误对象或Nothing；它不是任意路径解析的保证。

来源topic：`doc_macrocheckthis_func.htm`、`doc_macrocheck_func.htm`。这是**文档化的原生检查候选**，无需自行开发完整WinWrap编译器；但本轮未证明CST2022实际允许调用、是否继承CST全局方法/参数上下文、是否有弹窗，也未证明返回对象具有行列字段。`E.Description`有示例依据；不能把控件ErrorLine移接到这个对象上。

外层完整模块与内层历史须分别检查。内层不是完整Main模块时，候选检查器需要固定包装；包装插入行数应进入source map。包装通过不证明AddToHistory顶层语义相同，更不证明建模执行成功；W3仍保留实际历史执行/保存重开。原生检查需要一个已启动的宿主，因此不能叫作“启动CST前离线编译”。离线受限检查与宿主内、模型修改前的检查是两道门禁。

### 有能力但未证明CST暴露：嵌入控件接口

`wb9ent.chm::/wbenthtm/doc_syntaxcheck_property.htm`记录IDE/NoUI控件/对象的SyntaxCheck，检查其Code属性；`ErrorLine`、`ErrorOffset`、`ErrorFile`、`ErrorText`以及ErrorAlert/ErrorLog用于诊断。ErrorLine=0表示无可用行号；ErrorOffset在VB接口和C++接口的基数/运行错误哨兵不同。不能统一假设所有原生错误都有行列。

更重要的是TN0021指出SyntaxCheck可触发Begin事件；TN0220指出可能运行默认对象的Object_Initialize/Object_Terminate。故“正文不执行”不等于“完全无宿主副作用”。这些是WinWrap嵌入开发API，不是CST VBA Application Object的方法；目前没有核实CST向外暴露BasicIdeCtl/NoUI句柄，**不把新建一个独立控件实例当成CST上下文编译器**。

ErrorAlert包含语法及运行时错误，但不包含evaluation errors；ErrorLog是语法错误事件，也排除evaluation errors。Err对象用于脚本错误，不能因此推导CST建模表达式求值错误必定进入同一个回调。外层编译失败可能连错误处理器都无法安装；内层编译失败也可能在宿主弹框，均须校准。

CST Application Object另有ReportError：显示消息框、停止当前VBA求值，可被On Error Goto捕获。它是主动报告错误接口，不是静默采集编译错误的接口。ReportInformation/ReportWarning也可能在非求解期弹框；阶段日志应沿用文件记录或明确ToWindow接口，不用这些方法充当无交互诊断。

原生Python的`cst.interface.studio.py`只是对二进制`_cst_interface`的薄包装，静态阅读没有证明存在纯编译接口；同样不能因Python文件没有方法定义而声称二进制API绝无此能力。本轮没有导入运行或调用这些二进制对象。

## 4. W0收口与下一步校准

|项|状态|下一步|
|---|---|---|
|语言profile、调用/With/ByRef/参数重名规则|本地文档已核实|W1按小范围规则实现，裸调用与Call候选分别留样|
|首阶段持久化、参数、结果和会话边界|文档与现行profile已对照|保留G03；未知命令仍拒绝，不扩大支持范围|
|原生检查候选|MacroCheckThis已找到；SyntaxCheck控件权限边界已明确|进行独立串行无求解副本校准后才能接入生产|
|CST环境下可用性/行列/无弹框/初始化副作用|未实测|不能勾选原生语法门禁通过|
|统一Call形式、物理行/续行限制|未完成宿主校准|不替换0+或现有分段策略|

下一轮最小校准只创建本轮空3D副本，0次Solver.Start：固定已验外层驱动分别调用MacroCheckThis检查正常完整模块、明显语法错误、原始Zrange反例、0+版本、Call候选、CST方法/参数引用、中文/多行以及数组/ByRef样本；被检查代码包含写标记的正文以核实检查本身未执行。记录错误对象实际可读字段、是否弹框和source-map包装偏移；不调用错误字段的猜测属性来掩盖原始错误。

检查失败或能力不可用时停止该路径并保留诊断，不把未知降级为通过，不以真正运行错误代码替代语法检查。若MacroCheckThis缺失或不能解析同宿主上下文，W0能力结论更新为unsupported，再采用W3隔离的实际构造/重放门禁；不新增控件依赖。若出现模态框，记录无交互能力尚未满足，不继续叠加启动。

只有正常/反例区分、无正文执行、CST上下文适用性、诊断范围和正常关闭均有证据，才允许将该候选标为可用；当前只是设计与文档核实完成。校准程序/夹具与W1发射器需后续实施，用户原工程不参与。

## 本轮验证与产物

文档索引与既有定义事务回归共14 passed（8.91秒），报告artifacts/w0-static-review-20261103.xml；只证明链接/符号及既有离线契约未回归，不证明WinWrap已编译或CST已执行。git diff --check通过。本轮CHM解包树及pytest临时副本在解析后清理；原始CHM保留，可按来源清单重建topic，不依赖artifacts随Git迁移。

## 轻量检查器后续方向

[开源选型](../../winwrap-open-source-checker-options.md)已核查ANTLR VB6/VBA、Rubberduck和ViperMonkey。当前优先考虑ANTLR VB6离线PoC，保持MacroCheckThis真实宿主校准待验；通用语法通过不能改变此处原生证据状态。

## 已安装v9入口补充

[静态类型库核查](../../winwrap-v9-installed-entry.md)进一步确认BasicNoUIObj.SyntaxCheck与独立诊断成员，以及ErrObject无Line/Column成员。原生轻量对象创建/初始化尚未验证；这比“完全没有已核实接口”的旧边界前进，但不改变真实检查待验状态。[ANTLR实际PoC](../../antlr-vb6-poc-20261103.md)已接受原始Zrange故障形态，不可充当原生通过证明。

## NoUI原生尝试结果

[本轮NoUI实测](../../winwrap-noui-acceptance-20261103.md)在不启动CST情况下完成对象激活与正常清理，但初始化未通过（用户看到评估到期），语法检查0次。IgnoreDialogs=True没有阻止该初始化提示。W0调用规范仍以文档和既有CST证据为准，本轮没有新增原生语法通过结论。

## 2026-11-03核心宿主校准结果

[验收](../../cst-macrocheck-w0-20261103.md)现已证明本机2022.5的MacroCheckThis正反例、CST调用上下文子集、诊断Source行/语句、正文不执行与标准关闭。独立NoUI状态未改变；行列中的列号仍未知，Source格式仅按观察解码。原先“本轮未实测”保留为静态核查时点，当前结果以此验收为准。
