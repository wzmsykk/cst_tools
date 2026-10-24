# 检查点确认后采用标记滞后

2026-10-24源码确认：原Manager先写receipt.algorithm_adopted再写RunStore事件，重复调用见receipt已采用即返回，会漏补RunStore。
现统一采用写入，按日志→索引→receipt补齐，重复调用核对每个所属运行的同Task事件，不重复追加。检查点为权威，标记不是新结果导入指令。
真实CST标准双任务在三个Runner退出窗口已验证：检查点确认后全缺标记、事件有但索引缺、索引有但receipt缺。两次恢复标记不变，续跑仍只Solver两次，原确认检查点与快照/场保持。
HOM空任务和多模式身份采用仅有离线验证，不冒充真实HOM扫描验收。截断日志尾部保留原字节后修复；中间损坏/重复事件不自动删除。
范围与证据见[采用对账](../docs/checkpoint-adoption-l5.md)。清理后的原始模型/场需重新生成，artifacts不保证随Git迁移。
