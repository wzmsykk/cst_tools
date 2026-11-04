# W2/W3：A1独立检查、源映射与原生发布门禁

2026-11-03原生记录；2026-11-04更新当前实现边界。作用域为类型化A1定义的save_project构造链；不迁移其它稳定Worker/预处理宏，不增加MCP工具或编译服务。W0/W1原始证据见[前阶段](winwrap-w01-implementation.md)。下方11月3日无求解验收仅代表原记录版本；当前许可由11月4日[A1重校准](a1-recalibration-20261104.md)独立重新认证，不用旧记录放行新代码。

2026-11-04现行扩展：A1/GEO共用history_program原子分块、控制模板与物理块源图。GEO实际保存提取/两会话核验及独立版本门禁已接，见[GEO-2–4生产实现与验收](geometry-production-implementation.md)。A1本页旧23样本/12会话不自动认证变化后的源码；此前GEO批次A1更新被拒绝，后来用户明确授权后已完成[A1重校准](a1-recalibration-20261104.md)并更新独立许可。

## 生产链

保存预检 → 受限历史/外层模块独立检查 → 当前代码的原生校准记录核验 → 持久原生意图 → 同一受控3D候选 → MacroCheckThis检查历史包装模块 → AddToHistory/Rebuild/Save → 关闭证明/表达式与说明核对 → 原有两会话G03 → 发布。

winwrap_checks.check_history和check_module读取已经发射的文本，不复用发射节点来证明自身。检查字符串闭合、括号、命令/参数数、首实参形态、With/过程/If块、声明/参数冲突、固定控制模板中的已知语句/标识符。未知内容拒绝，生成profile禁用续行及Class/Object初始化钩子；800字符是项目保守预算，不是WinWrap硬上限。这不是完整Basic解析器，数值/单位/历史顺序仍复用原A1投影，原生语法仍单独验证。

进入CST前的错误为GENERATED_CODE_INVALID并给出history/outer-macro层及生成行；错误不触发加密/扩窗/求解重试。保存预检拒绝尚未建立候选目录时，以层/行和已保存草稿定位；进入候选后保留完整代码与映射。

## 版本门禁

require_calibration核对data/winwrap-a1-calibration.json、其中固定命名的知识库原生证据摘要及当前SOURCES中16项共享生成/投影/验证/服务源码与Schema的规范化换行SHA256（原批次为七项）。缺失、过期、证据改变、检查器加载后磁盘变化均拒绝保存，不自动刷新hash。应正常退出旧Runner后升级；不支持热更新。

数据文件是本地发布/开发门禁，不是数字签名，不能防御可同时篡改代码和证据的本地操作者。它只证明记录版本和样本；运行输入仍检查，构造后仍核对G03。2022大版本规则沿用用户既定假设，真实校准只覆盖本机2022.5。

重新校准必须显式运行：

```powershell
python test/support/calibrate_winwrap_gate.py --run-cst --publish-gate --cst-exe "D:/Program Files (x86)/CST Studio Suite 2022/CST DESIGN ENVIRONMENT.exe"
```

工具只在独占串行副本全部通过、各会话标准退出、校准前后源码hash不变后写门禁；参数不开放任意VBA。--publish-gate是写本地校准记录，不是Git提交、推送或发布源码压缩包。普通业务不为每个HOM窗口新开CST编译；此门禁只用于A1保存。

## 原生检查与诊断

生产render_edit_macro在参数/说明设置后、AddToHistory之前调用MacroCheckThis；包装固定为语言头、Option Explicit、Sub Main三行。失败写history-syntax-error.txt，既有错误处理/持有对象正常保存诊断并退出，Python拒绝候选。检查历史不等于检查字符串所在的外层模块；外层由独立检查和本版本原生样本门禁共同覆盖。

候选保留history.vb、edit.bas、最终probe.bas、source-map.json。映射包括参数名称/表达式/说明、历史行→输入字段组→外层字符串片段→Python生成函数；范围/多个实参只映射到字段组，不发明原生列号。身份声明插入两行、绑定调用插入一行，最终宏映射与最终hash另存。

原生错误保留Number/Description/Source原文，native-diagnostic.json在已观察Source格式可解析时减去三行包装偏移，定位到如cylinder.axial_range；未知格式保持未知。映射用于诊断，不授予执行/发布权限，也不将源映射的宽松定位器当语法验证器。

## 故障与恢复边界

- 部分属性步骤失败、返回不完整保存内容、保存后响应丢失、未确认退出：不写定义提交/结果，不移动旧文档指针。同操作重入要求对账，不再次调用原生编辑器。
- 单次仿真项目/定义身份错误：FakeWorker验收零次run_task；求解异常/完成响应丢失最多一次派发；stop超时保留unknown与恢复要求。它们是离线故障证据，不冒充真实求解失败。
- 真实无求解负例分别验证历史语法拒绝且未执行历史，以及成功执行前置历史后受控Err.Raise失败。后者是明确注入，不是未经文档证实的自然CST setter失败；都要求正常退出。
- 独立NoUI初始化仍不支持，不复制/猜测许可材料；不覆盖任意对象初始化、所有弹窗或所有求解器故障。G01–G08真实求解/控制器退出矩阵继续独立维护。

## 本轮发现的边界

[早期证据](../knowledge-base/winwrap-w23-early-20261103.json)记录：MacroCheckThis对特定缺末尾引号样本返回接受，而独立生成规则继续拒绝；没有执行被检查正文，不能据此声明该语句运行正确或所有未闭合字符串均被接受。

CST参数说明中的emoji样本保存成两个问号，且观察到末尾空白被去掉；表达式保持。当前profile明确拒绝非BMP/孤立代理字符和首尾空白，不静默替换或裁剪。首尾空白统一排除是项目保守策略，并非已测试所有前导空白；其它BMP文本也必须经过保存后逐项核对。这是说明持久化边界，不外推所有CST API的Unicode行为。

## 验收记录

最终根目录artifacts/winwrap-w23-c121c36e：23个原生编译样本（含观察项）、2个失败拒绝样本、XYZ各一次构造及两次G03会话，共12个串行会话，均确认退出0；所有求解调用为0。结束时本轮进程清单为空，仅属于当时观察。

[冻结原生证据](../knowledge-base/winwrap-w23-20261103.json)与[data门禁](../data/winwrap-a1-calibration.json)绑定实际源码版本，源码相关文件变更会拒绝保存，需重新校准；首版按整个文件保守钉住，不自动推断语义等价。原始artifacts不保证随Git迁移。正常求解无总超时约定不变；本轮不调用Solver.Start。离线检查、原生编译、实际历史执行、G03、进程退出分别统计，不以单个退出0充当总成功。

首轮缺引号反例的预期与原生观察不同，第二轮说明持久化不一致，各自均阻止校准发布；早期共5个会话全部正常关闭，不把整个工作批次说成只启动12个会话。当前规则加严后才完成最终验收。此前39项离线专项通过，完整组合回归结果见知识库外层字段；这些集合不相加。

完整组合回归271 passed、1 skipped（148.79秒），包含独立检查/源图、定义事务/故障、原生构造/G03、适配器、文档/登记和源码包；跳过模块为缺少可选mcp依赖的SDK测试。解压源码包直接require_calibration核验通过，不依赖开发目录。原生XYZ的外层映射片段与实际注入后的probe.bas逐段核对一致。

本轮17个会话（最终12、前期5）均结束后，已保留各模型的参数/历史/必要宏/源图/hash并删除17份.cst及同名计算目录，测试临时树已清理；原模型需重生成，不能按旧路径直接重验。未提交、推送或交付新发布包。

2026-11-04边界补充：现行SOURCES已扩展包含geometry_contract/geometry_codegen，旧11月3日stamp随后被独立11月4日重校准记录替代，不改写旧原生证据。显式GEO离线profile与[源映射产物](geometry-selection-interface-design.md#13-geo-2离线历史发射投影检查与源映射)不由本页A1原生证据校准，GEO已由独立geometry-calibration校准，不借本页旧A1证据放行。
