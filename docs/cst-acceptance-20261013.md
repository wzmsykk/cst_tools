# CST 真实验收：2026-10-13

源码：32c2bd3fad7334b45e49a58dfdfd3e13ee0f433f。环境：Windows，CST Studio Suite 2022，Python 3.12.7。

执行19项集成测试，采用首个失败即停止。报告 `integration-cst-acceptance-20261013.xml`；现场保存在 `.pytest_cache/cst-acceptance-20261013-01/`。

## 结果

- 2 passed / 1 failed / 352 deselected，845.84秒；剩余16项尚未执行。
- 工程预处理、源文件保护测试通过。
- 同一Managed Worker两次任务和标准退出通过：产生两份任务Ack接受回执；生命周期日志记录Save returned、Quit returned；Stop Ack存在，退出码0，不需要强制清理。该专项测试继承Pillbox源工程10模式设置，不是生产HOM单模式策略。
- 十模式三种故障恢复测试失败：前三个模式已确认（502.882119041、504.406888343、513.492630838 MHz），完成用户安全暂停。由第三模式快照新建会话后，第4次请求失败，未进入控制器失联及进程中断恢复路径。

## 失败定位

窗口：513.492631838 MHz附近起点、宽度50 MHz，单次nmodes=1。任务2cada292-5449-47d0-a0f6-09ed5252be5f；会话f30a289a-c957-4c6e-938c-4ea9af74bf36。

Result/output.txt显示：

```text
Number of modes: 1
Adaptive Computation
Pass 1:
The eigenmode solver stops due to maximal number of iterations.
Eigenmode solver stops.
Do you also wish to abort the following template based post-processing steps?
Auto answered with "Yes"
3D Eigenmode result template execution: Cannot find result for mode #1.
```

Worker报告RESULT_FLUSH_FAILED / postprocess failed / Missing eigenmode #1。本轮没有模式结果是求解达到迭代上限造成，不是已证实的合法空区间，也不是Ack文件打开错误。VBA仍未在后处理前直接区分Solver返回失败，故最终错误分类落在后处理层。

故障会话生命周期记录已发布失败Completion并消费Ack，删除了current通信文件；未找到该会话Stop Ack，不能据此认定标准退出通过。测试finally允许在标准停止失败时紧急终止其自身会话；本次输出未提供足以证明故障会话完整正常闭合的证据。验收后只读进程清单未见CST DESIGN ENVIRONMENT或modeler进程，仍有CST后台服务进程，不对这些服务采取清理。

## 边界与下一步

- 不将2项通过推广为19项全部通过；集中日志、生产待确认结果接纳、资源准入等仍缺真实完整链路验收。
- 下一步对同一快照和窗口进行受控对照，核对恢复后的求解器/网格设置及最大迭代限制；不得仅把Missing eigenmode当作空窗口跳过。
- 应核对EigenmodeSolver.Start的实际返回与求解状态，区分Solver失败和后处理缺数据；不靠放宽整个扫频范围掩盖收敛故障。
- 此测试直接使用源工程及快照，原生输出显示Adaptive Computation；它并不等价于生产GUI固定网格预处理后的全部设置。
- 本次仅验收与诊断，未修改求解或扫描实现，未重新打包。
