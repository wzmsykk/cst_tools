# NMODES=2 多模式后处理验收

2026-10-13，CST 2022。仅复制源 .cst，不复制伴随目录。正式 HOM 扫描仍为单模式。

## 实现确认

`EigenResult_Simple_All_output` 和 `EigenResult_Complex_All_output` 遍历 `EigenmodeSolver.GetNumberOfModesCalculated`，不是请求的 nmodes。Python `read_all_modes` 返回按 `ModeIndex` 分开的字典。默认 PPS 只读取 Mode 1，本次对七项指标使用 `_All`。现有 HomScanAlgorithm 会拒绝 `_All` 配置，不能直接接入正式扫描。

## 实际结果

范围 513.492631838138–713.492631838138 MHz，nmodes=2。

| 指标 | Mode 1 | Mode 2 |
|---|---:|---:|
| frequency / MHz | 568.241333802364 | 568.745898810088 |
| R/Q | 1.83015706258064e-6 | 9.18683904252178e-7 |
| R/Q 5mm | 1.75144865382745e-6 | 1.01085003742643e-6 |
| R/Q 10mm | 1.67228645896462e-6 | 1.11079054376255e-6 |
| Shunt Impedance | 9.44701888071902e-7 | 4.75087440274737e-7 |
| Total Loss | 5135407940.3396 | 5134371605.61809 |
| Q-factor | 0.516186237447737 | 0.517139179293084 |

七项均包含两个 ModeIndex。任务 Success，Stop Ack 成功，进程 exit=0，源工程哈希未变，未强制结束。全过程108.16秒，任务51.98秒。后处理生成器及读取回归测试12 passed。

第一轮自适应日志频率约564.5062、564.8037 MHz，但最终后处理频率为上表，不能把中间轮次当最终结果。此前同范围 nmodes=1 返回564.639290502774 MHz；本次两个最终频率均不等于它。不能仅凭相邻频率断言同一物理模式或确定新增模式，需比较网格收敛及场型。更不能据此证明旧范围为空。

原始证据：`.pytest_cache/controlled/97bf7751/width_200/comparison.json`，任务 b84750fe-a72d-4e18-8fb8-1c6e40936c16。测试入口 `test/support/compare_cst_snapshot_execution.py` 增加 `--nmodes 2 --all-modes`，仅用于受控对照。
