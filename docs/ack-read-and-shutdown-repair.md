# Ack 读取和退出收尾修正

本页记录第一阶段修补。当前状态协议以 [managed-ack-state-contract.md](managed-ack-state-contract.md) 为准：Ack失败进入阻塞待确认，不再采用等待1秒后主动退出；接收记录和接受回执先于清理，Manager暂停而不自动重算。

## 现场证据

2026-10-13 的用户诊断显示：Completion 为 success，Ack 文件存在且任务/会话匹配；VBA 报 Could not open file，停止请求随后才发布，最终进程退出码 0 但缺 Stop Ack。退出日志含 EvaluateInternal CDbl(TrrrA1) 求值错误。不能证明这是未计算导致：本轮有 887.7311 MHz 求解结果。未请求的外部 Q 模板失败是预期现象，不作为必需指标失败依据。

## 有限重试是否必要

有限重试不是正确性的必要条件，也不是已证实的根因修复；但对长任务文件握手具有实际容错价值。文件原子发布确保不会读到半成品，并不保证发布后立刻能打开（例如瞬时共享锁或存储访问故障）。现场未提供 Err.Number，因此不预设具体 Windows 错误码。

仅文件 Open 失败最多尝试 3 次，间隔 0.1 秒，总等待约 0.2 秒（不含系统调用耗时）。每次打印路径、operation=open、尝试次数、Err.Number 和描述。打开成功后读取一次；格式、缺字段、身份错误不重试、不放宽协议。永久错误最多额外等待 0.2 秒，并保留最终错误。WinWrap 中的实际错误码和重试效果仍需现场验收。

## 退出路径

- ack-read 和 ack-cleanup 分别记录阶段；删除 task/completion/ack 前分别记录具体操作与路径。
- Ack 读取失败不覆盖已经发布的 Completion；保留协议文件供恢复。
- 失败后最多等 1 秒让 Python 观察 failure 并提交 stop.request，然后转入独立收尾函数。错过这段窗口仍可能无 Stop Ack，不能将其等同于已验证正常闭合。
- 收尾校验 Stop Request，Save 成功返回后才写 Stop Ack，再 Quit；日志分别记录 save/quit 的 begin/returned。Stop Ack 不单独证明 Quit 成功，Python仍等待进程结束。
- 独立 CloseFailed 捕获保存/退出错误，不跳回任务求解或 Ack 循环，不重写任务 Completion。Save 失败不继续 Quit，避免未保存工程引发交互保存提示；不自动强杀。
- 会话新增 worker.state.lifecycle.log，Python失败诊断JSON收集其尾部。实际日志位于 marker 同目录，不依赖 stdout及时刷新。
- Python退出错误区分“仍在运行，需会话恢复”和“已经退出，需核对协议/快照”，不再统一要求紧急终止。

## 测试边界

普通测试覆盖生成 VBA 的打开重试范围、协议校验保留、Save→Stop Ack→Quit 顺序、收尾独立处理，以及假进程退出但缺确认的错误分类。源码契约检查不是 WinWrap 执行验证；实际文件锁注入、Save表达式错误、Stop/Ack交叉及CST标准退出还需真实集成验收。
