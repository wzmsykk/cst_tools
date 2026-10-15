# 假Worker HOM专项验收

## 2026-10-15：独立Runner审计修复后复验

源码基线：053e4ca。仅假执行器，不启动真实CST或修改用户工程。

```powershell
python -m pytest -q test/hom_probabilistic_fake_worker_test.py test/hom_scan_test.py test/hom_mode_count_contract_test.py test/gui_fake_worker_flow_test.py test/gui_vacuum_matching_fake_flow_test.py test/runner_test.py test/gui_runner_test.py test/runner_audit_regression_test.py test/documentation_index_test.py --basetemp D:/work/cst_tools/.pytest-hom-fake-20261015 --junitxml artifacts/fake-hom-acceptance-20261015/report.xml
```

结果：103 passed（40.10秒）。报告artifacts/fake-hom-acceptance-20261015/report.xml；artifacts不保证随Git迁移。
包括HOM扫描/模式数约束、GUI假Worker与可选场匹配流程、独立Runner停止续跑/崩溃恢复、HTTP启动及取消响应丢失/超时故障。场匹配流程通过不表示完整HOM谱的物理场身份追踪已验收。

另逐组核对CSV驱动随机模型：扫描911.715464937295–1860.70021088335 MHz，窗口20 MHz、nmodes=1。

|模型种子|预期/找到模式数|每mode后处理项|求解调用数|空区间数|失败区间数|
|---|---|---|---|---|---|
|0|8/8|7|52|44|0|
|1|8/8|7|53|45|0|
|17|8/8|7|54|46|0|
|20260919|8/8|7|55|47|0|
|4294967295|8/8|7|56|48|0|

找到频率与每组生成谱逐项相等；七项为frequency、R_divide_Q、R_divide_Q_5mm、R_divide_Q_10mm、Shunt_Impedance、Total_Loss、Q-factor。
空区间属于有效覆盖，不要求每次调用都产出模式；完整找齐结论限正常返回路线。持续异常必须保留缺口，不能把故障测试通过解释为任何异常下都找齐。
本轮不修改实现，测试结束后清理临时模型/检查点，保留轻量JUnit和本文；原始临时数据需重新生成。

## 2026-10-14：历史验收

日期：2026-10-14。本轮不运行真实CST，不修改用户工程。

命令：

```powershell
python -m pytest -q test/hom_probabilistic_fake_worker_test.py test/hom_scan_test.py test/hom_mode_count_contract_test.py test/gui_fake_worker_flow_test.py --basetemp .pytest_cache/fake-hom-acceptance --junitxml artifacts/fake-hom-acceptance/report.xml
```

结果57 passed（1.12秒）；轻量JUnit记录artifacts/fake-hom-acceptance/report.xml。

## 覆盖与结论

- 默认窄窗口、nmodes=1逐模扫描；空区间继续推进，近频率模式不简单合并。
- 基于现有CSV样本的随机谱，模型种子0、1、17、20260919、4294967295。正常模式返回路线下，五份模型全部生成频率找齐，每mode具有frequency、R_divide_Q、R_divide_Q_5mm、R_divide_Q_10mm、Shunt_Impedance、Total_Loss、Q-factor。标量来自假模型，不代表CST物理精度。
- 随机异常发生器可复现并覆盖配置的异常类别；脚本化求解失败、越界、非有限、多mode、重复频率等不会误报完整扫描。
- 越界后重新计算、有限重试、持续异常留下failed区间、停止时保留pending区间、检查点身份和快照校验、生产HomScanAlgorithm结果/存档映射及恢复均通过。
- 原GUI假Worker成功/并发/失败/关闭流程通过；不证明真实桌面输入或CST生命周期。

“正常返回路线找齐”与“异常混合路线总能找齐”不是同一结论。持续失败、真正重复/简并频率等仍可能产生未确认区间；门禁要求保留原因，不强行宣称全部找齐。本轮未新增HOM请求控制，也未把固定参考场匹配用于跳过或合并HOM。

这套测试主要验证频率枚举和标量后处理。新登记/匹配的GUI假Worker链另见[Managed/GUI假Worker验收](managed-vacuum-domain-gui.md)；不能用本轮57项自动推断完整HOM谱的场模族身份追踪已验收。

pytest临时模型、CSV、检查点等产物在验收结束后清理，可重新运行测试生成；保留JUnit和本文，不保留临时数据路径的可复算保证。
