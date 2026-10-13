# 固定窗口 CST 受控对照（2026-10-13）

源码基点32c2bd3；只新增对照工具，未改生产扫描/恢复/求解实现。

## 控制条件

三组均只复制 .cst，不复制配套目录。CST 2022，同一Managed Worker实现和七项后处理设置；nmodes=1，fmin=513.492631838138 MHz，fmax=563.492631838138 MHz。保留Default方法、1e-06目标精度、自适应网格及损耗设置。不提高迭代上限、不改变窗口、不改原始工程。

快照为上次验收第3模式（513.492630838 MHz）的已确认快照，启动前核对SHA-256与接收记录一致。

## 对照结果

| 对照组 | 变化因素 | 目标窗口结果 | 整组耗时 | Stop Ack / 退出码 |
| --- | --- | --- | --- | --- |
| original_cold | 原始工程直接冷启动 | 最大迭代次数停止，Missing eigenmode #1 | 99.94秒 | 有 / 0 |
| snapshot_cold | 第3模式快照直接冷启动 | 同上 | 62.08秒 | 有 / 0 |
| snapshot_warm | 同一快照先重算上一窗口，再算目标窗口 | 上一窗口成功，目标窗口同上 | 165.17秒 | 有 / 0 |

第三组预热窗口为504.406889342598–554.406889342598 MHz，预热任务成功（约81秒）。整组耗时包含启动、预热及退出，不可直接作为Warm/Cold加速比。各组均未自动强杀，结束时记录process_alive=false，源文件哈希前后一致。

三组原生output.txt均含：

```text
Method: Default
Desired accuracy: 1e-06
Number of modes: 1
Adaptive Computation
The eigenmode solver stops due to maximal number of iterations.
Eigenmode solver stops.
```

工具退出码0仅表示三组观察完成，不代表三个求解通过。

## 结论和边界

- 该失败可在原始工程上复现，也可在快照冷/热会话复现；不是仅由快照恢复或冷启动触发。
- 无证据支持更改“只复制.cst”的恢复方式，本次保持不变。
- 缺mode 1是Solver达到迭代上限后的后果，不能作为合法空窗口直接跳过。
- 目标窗口问题与Ack/标准退出问题应分开；此次三组均完成Stop Ack和进程退出确认。
- 每组只做一次，不声称统计复现概率或排除所有恢复问题。尚未确定为何该窗口不收敛。
- 下一步先读取实际迭代设置和Model.log，再单变量比较迭代上限、固定网格/自适应设置或边界位置；维持单模式窄窗口原则，不一次同时调整多个设置。当前边界是上一模式频率+1e-6 MHz，是否涉及数值敏感性只是待验证假设。

## 产物

- 可复用工具：test/support/compare_cst_snapshot_execution.py。
- 完整报告：controlled-cst-comparison-20261013.json。
- 实际原始输出、资源采样、接收回执及生命周期记录：.pytest_cache/controlled/980b5813/各组目录。
- 未重跑余下16项集成测试，也未改动失败的HOM测试要求。
