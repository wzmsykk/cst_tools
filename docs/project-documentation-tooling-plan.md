# 文档、功能定位与开发工具体系设计

现行范围：D1–D4已实现，2026-11-03组合60项离线/源码包检查通过；本次语义复审不追认新运行证据。详细逐批设计/故障/数字保存在[复审前方案](archive/20261103-semantic-review/project-documentation-tooling-plan.md)及[D4轻量记录](../knowledge-base/project-tooling-d4-20261103.json)。

## 单一责任来源

|责任|归属|约束|
|---|---|---|
|功能/源码符号/测试工具/文档角色及人工关系|docs/project-map.json与schema|原136项无损迁移；feature-index.md只生成，禁止双份维护|
|业务语义/当前能力|API/专题正文、current-status.md|机器字段不是行为证明；专题不能靠名称猜CST语义|
|下一步|现行TODO|不继续追加多组“真正下一步”；旧未决项可查归档|
|全范围文件清单/静态候选/变更及删除预检|scripts/project_inspect.py|默认只读，不导入被分析模块或执行登记工具；删除预检不授权删除|
|维护门禁|定位/迁移/登记/故障/包边界和索引测试|结构有效不授予文档语义、动态投递或真实CST通过|

生产MCP/HTTP/CLI、Task/Completion/ACK/RunStore及配置合同不因开发导航重构改变；utils不清理，第三方/资源/历史证据有独立类别。没有新增常驻文档服务、运行时ABI或另一队列。

## 已实现范围与长期边界

D1迁移全部旧功能与派生索引；D2实现查询、全图/文件清单、变更/删除预检及显式render；D3登记工具/手工动态关系/文档角色并维护导航；D4扩展故障和真实源码包边界。原基线1567文件、136功能等仅为当时分母，当前数量从机器契约/命令取得，不作为常量写入多份文档。

人工关系记录source/targets/consumers、触发、线程/阶段、清理、证据与未知；包含GUI/MCP/Runner/工厂、ACK/采用、COM/WinEvent/logging及打包。AST import或注册是候选，不是实际接收者、回调投递和退出证明。源码hash变化提示人工复审，不自动更新关系或hash掩盖漂移。

工具清单覆盖明确的第一方入口范围；传递副作用未核的保留unknown。文档角色分清现行、提案、验收、研究与历史；本次[语义复审](documentation-semantic-review.md)继续核对正文，不能由D3的清单齐全替代。

源码包有显式package校验，只对manifest所列字节与包内契约负责，报告省略项，repository_complete=False；默认repository校验不豁免省略。测试包已清理，原ZIP需要重建；哈希不认证作者或运行正确性。

## 维护

按AGENTS：读状态/索引→query/changes/delete→修改实现与契约/专题→人工复审证据/hash→render→validate及相应测试。使用和错误详见[指南](project-map-guide.md)；本页保存稳定设计，不继续堆叠D1/D2/D3/D4完成日志。
