# V06设计用例

说明入口：[验收用例与合同](../../../docs/cst-settings-v06-acceptance-plan.md)。

- `cases.json`是56项人工规范性输入/预期，尚未由语义解释器执行；不是公共Schema。
- E组`expected_execution_config`与数据库观察分开；用例中的profile只是显式前提，不是生产能力登记。
- `evidence.json`登记真实源文件、成员和5个`.mod`字节片段的hash与原始行号。片段用于溯源，不代表整工程或整个历史已支持。
- `.mod`只作为数据读取，不可当作可执行宏或重新写入CST。
- 根`.gitattributes`将这些原字节片段标为binary，禁止Git换行归一化；保留原始行尾空白。
- `test/v06_casebook_test.py`仅查结构、来源hash及预期保留，不检查解释器是否实现，更不证明CST行为或G03通过。

用例修改必须注明依据；不要通过改expected来消除实现失败。源文件hash漂移应先核查来源、重新审查摘录和预期，不能自动追随新hash。真实证据与人工规则分开，保留未知和不支持。
