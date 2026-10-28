# V06新增来源边界（2026-10-28，只读）

本轮只读固定cst_version源码和仓库Pillbox/Enlarged，原文件hash前后未变；没有启动CST、求解、保存工程或修改共享读取器。设计和用例入口：[V06合同](../docs/cst-settings-v06-acceptance-plan.md)。

## 源码定义

固定`cstv.py` SHA256为`612eb6da9132ecf6aea8e2e0416877063c0bf70dfde1db3a4e01e7e9f52e23fc`。

- `_scope_prefix(None/空串/root)`返回根前缀；非SP开头的scope自动补SP/。它不代替“请求scope必须来自project_scopes”的业务校验。验证路径先判确切身份，不能按便利转换后再猜用户意图。
- `history_list`按UTF-8/replace解码，`history_steps`在该文本上识别块；`_is_disabled`只判断整块是否所有非空行都为注释，不是完整条件/对象/语句解释。
- `simulation()`将缺失和JSON错误都返回{}。本轮未改这些API；后续共用严格模式/适配，不复制容器读取器。

## 本轮只读观察

从`model/Pillbox.cst`与`model/Enlarged.cst`提取5个保存历史块，原字节保存在[固定证据](../test/fixtures/cst_settings_verifier_v06/evidence.json)，含源/成员/片段SHA256及原始行区间。它们进入Git工作区而非仅放artifact，未来可核对出处；当前尚未提交。

|来源/scope|块/原始行|事实|
|---|---|---|
|Pillbox/root|60，795–842；61，843–890|全注释块含模式数12，后续活动块含1；完整成员可严格UTF-8解码|
|Enlarged/root|56，4063–4110|模式数表达式nmodes、target表达式fmin；参数fmin=499；完整历史首个UTF-8错误偏移9609|
|Enlarged/SP/FMF|23，7619–7666|仍有Eigenmode设置历史，保存Last Solver Type却为HF Frequency Domain；完整历史首错11611|
|Enlarged/SP/FME|23，7635–7685|target表达式fmin，参数fmin=498.5；完整历史首错11618|

偏移均为成员解压后原始字节的零基偏移。行号沿用共享块导航，并核对字节行数；摘录保留原字节，不把导航replace解码当作语义正确。选中的块基本ASCII，不消除完整成员未知编码的问题。Last Solver Type是保存元数据，不是本轮live求解器查询。

## 结论与未证事项

不能把所有合法CST历史都假定为UTF-8；也不能依据这几段字节宣称它们必为GBK、ANSI或某个固定编码。这里未查明原编码。缺乏编码声明/profile时应unsupported-encoding，保留字节和定位，不能替换后放行，也不能直接判工程损坏。若未来已明确声明UTF-8却出现非法字节，则是另一类malformed输入。

明确scope、未知控制流、Reset、参数依赖、CRC/JSON和执行快照的56项预期是人工设计合同，不是CST实测输出；其中有些采用既有实测边界，来源见各设计文档。生产语义解释器未实现，V06/G03仍未通过。

本轮结构/来源检查及既有安全回归40 passed（2.24s），artifacts/v06-design-verified-20261028.xml；其中4项新检查不执行语义解释器。pytest重算源文件和片段hash，成员hash来自本轮只读提取而非pytest重新解包。未产生模型/场副本；pytest临时目录已清理，轻量报告保留。人工预期、历史摘录及本记录尚未提交。
