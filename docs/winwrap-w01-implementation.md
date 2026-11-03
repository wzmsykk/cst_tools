# W0/W1：受限WinWrap发射与无求解验收

2026-11-03，W01原批次范围与证据；后续现行门禁见[W23](winwrap-w23-implementation.md)。基线2705935加当批工作区。W0在首阶段Sub-only范围内完成扩展校准，W1已迁移类型化定义构造；不是完整WinWrap编译器，也不宣布W2/W3生产门禁完成。

## 实现与接口

- csttool/winwrap_emitter.py提供String/Number/Boolean、Variable/Element/Property、Function/Unary/Binary/Arithmetic、HistoryCall/With、SubCall/resize_arrays、Symbols和assign_string。禁止将原始源字符串当表达式传入历史调用。
- arithmetic先复用既有有界算术检查，再将参数名发射为RestoreDoubleParameter引用，保留原表达式与运算结合关系；不以缓存值代替。
- HistoryCall从settings_projection.history_call_contract取得唯一COMMAND_ARITIES派生的调用卡片：loaded-3D、语句调用、参数数、类型检查归属、弃用返回值、历史立即执行/重放、副作用、版本及B编号。参数具体数值/枚举/单位/顺序仍由同一A1投影核验，不复制第二套允许表。
- definition_editing.render_history使用类型节点生成历史；render_edit_macro复用声明登记和字符串赋值。稳定的错误处理、文件输出和会话流程仍是固定模板，不引入通用控制流AST或第二个调度器。
- 裸调用首实参若仍以左括号起始会在发射时拒绝；算术节点显式输出已验的0+安全形态。生成器保留已验裸调用及0+前缀；此次Call校准没有将所有生产调用改为Call。保留24字符字符串分段，生成行采用800个ASCII字符的项目保守预算；它不是CST/WinWrap语言硬上限。

## 错误、命名和发布

工程参数与模板局部变量、过程、注入归属辅助函数、使用的CST对象/函数名按大小写不敏感方式检查。f/F、history、names、ReportStage、Cylinder等冲突在草稿检查时返回GENERATED_CODE_INVALID；关键词表只覆盖此受限生成范围，不承诺枚举整个宿主名称空间。

保存预检先发射历史和外层宏，冲突/未知节点/参数数不符/保守行预算失败均在写definition-intent.json与原生调用前拒绝。长输入不会截断，不能通过重试、改数值或自动求解消除生成错误。旧草稿如果使用这些冲突名，不再接受该受限生成链的检查/编辑；须新建文档并显式重命名参数及引用，不原地迁移、不增加旧生成器兼容开关。已确认定义/结果保持原样。

发布仍要求原有AddToHistory整体返回、Rebuild/Save、表达式和说明核对、G03及正常退出；本批没有新增每个setter的返回探针，部分属性失败矩阵留在W2。A1静态投影不是原生语法证明。原生执行后响应/回执缺失仍走已有对账，不隐式再执行。当批未覆盖的源图和A1发布门禁现已在W23接入；更广故障/生成器矩阵仍按计划推进。

## W0受控副本实测

工具[test/support/calibrate_winwrap_calls.py](../test/support/calibrate_winwrap_calls.py)显式要求--run-cst，复用exclusive_probe、持有对象的run_new_definition、私有桌面/归属后quiet和已有两会话G03。未更改用户原工程，无Solver.Start。

- W0：23个MacroCheckThis样本，保留原始Zrange反例拒绝与0+正例；语法检查正文文件标记未生成，L表达式仍为2 * W0Base。
- 实际Call .Zrange建模后，将W0Base由2改为3并Rebuild，结构盒Z读回-3/+3，Call保留于保存历史。String数组ByRef修改为after，Double标量1变3。
- 字符串赋值物理行526、814字符接受，1038、2062、4110拒绝；1/10/24/50个续行样本均接受。只证明这些完整样本，不给出精确阈值或无限续行保证。
- W1：实际生产发射器创建小圆柱，L=2 * R及中文/引号说明保存；已有G03保存/重开两会话核对设置、表达式、实体/体积/边界通过。
- 共四个串行会话，均确认退出0；两个构造会话有归属/quiet与零前台事件证据，G03沿用原有批处理关闭门禁，不宣称整个G03显示策略已迁移。结束时探针进程清单为空，只属于该时点。

轻量证据见[知识库JSON](../knowledge-base/winwrap-w01-20261103.json)。原始目录artifacts/winwrap-w01-0627823e不保证随Git迁移；本轮模型副本/同名结果在确认结束后清理，重验需重新生成。首次受限环境PrivateDesktop创建被拒，在启动CST前失败；正常用户环境的串行校准通过，不把首次失败计为原生宏失败。

## 初始化与剩余范围

此profile只有固定Sub/函数和普通数据声明，不生成Class/Object模块、As New、Object_Initialize或Object_Terminate；这些初始化能力明确排除，不能把Sub正文未执行推广为任意对象初始化无副作用。独立NoUI仍初始化失败，不再尝试过期评估初始化，不绕过许可。

Call实际通过仅覆盖此调用及参数/重放样本；多维数组、更多COM签名、所有声明/行长、复杂模型、XYZ真实构造、全部错误弹窗及指定桌面完整MCP流程不在本次验收。W1只迁移定义构造，其它稳定宏未批量改写。

## 测试

首轮84项离线发射/定义/投影通过；扩展核心163项通过（10.58秒），包括新探针离线约束、XYZ/嵌套表达式、字符串/符号冲突、长行拒绝前无执行意图及原定义事务/允许表回归。集合重叠不相加；原生23样本和四会话不是163项离线测试。最终组合回归232 passed、1 skipped（83.05秒），含事务/原生构造/G03、允许表、适配器、文档/登记及源码包边界。跳过test.mcp_sdk_test：当前Python缺少可选mcp依赖，不视为SDK或指定桌面新验收。测试XML为artifacts/w01-final-verified.xml，不保证随Git迁移；摘要随知识库JSON保存。
