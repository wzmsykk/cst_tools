# Runner审计修复与故障验收

日期：2026-10-15。范围：A1–A4、M1；不启动真实CST、不提交/推送、不重新打包。
前置记录：[审计回应](runner-audit-response-20261015.md)，当前API：[本机Runner](local-runner.md)。

## 实现与防护

|编号|修复|源码/测试入口|
|---|---|---|
|A1|状态含租约有效性/剩余秒数/控制修订；只读仍可申请；有效租约拒绝竞争者，过期心跳与旧claim回执不能抢回控制权|Runner.snapshot/heartbeat/command、RunnerController.request_control、MainWindow.claimControlButton；runner_audit_regression_test|
|A2|启动UUID及请求内容派发前固定；按启动ID取消，墓碑防迟到启动；只停其绑定run；GUI停止意图落盘并在确认后清除|Runner.command/command_record/_stop_run、RunnerClient.save_stop_request、RunnerController.request_stop；真实回环HTTP故障测试|
|A3|连接代次隔离成功/异常/命令上下文；新项目首次允许启动，旧已连接Runner失联不自动重启；捕获旧client释放控制权|RunnerController._sync_context/_observe/poll；项目切换及ABA测试|
|A4|版本2文件游标、有界256KiB扫描、64KiB记录上限、跨批次丢弃、损坏/超长记录原文件位置提示；普通尾行等待|event_replay.read_events、Runner.events、RunnerClient.events；字节阈值/UTF-8/多MB/轮转测试|
|M1|配置草稿、执行控制端口、状态DTO分离；去掉伪执行/假恢复；纯默认设置及共享mesh校验；真实Backend延迟导入|ConfigurationDraft/ConfigurationService、ExecutionControl/RunnerSnapshot、scan_settings；草稿/服务回归|

停止确认是Runner接收持久停止意图，不等于立即关闭CST；GUI继续等待运行终态与安全门禁。目标未闭合时保留意图并要求会话恢复，不能误停当前另一运行。
取消记录及命令记录保留以防旧请求重放，目前没有自动压缩/清理协议；不要手删活跃control目录。

## 验收方法与证据范围

- HTTP响应体丢失：真实假Runner子进程已返回HTTP头后，客户端关闭连接且不读取响应体；GUI同时请求停止，重连后只停止同一run，持久start记录仅一条。
- HTTP响应超时：本机真实HTTP服务在持久接收start后延迟返回，触发urllib两秒socket超时；并发停止按原start对账，不重新提交启动。
- 组合故障：start未发送即失败后登记取消，迟到原请求返回已取消且没有求解调用；cancel_start响应体再丢失时重连继续对账，停止意图不提前清除。
- 额外覆盖：启动尚未到达/迟到、取消墓碑重启、已完成旧启动与新活动运行隔离、控制器重建读取停止意图、租约竞争/旧心跳、跨项目和ABA旧回调、长记录后正常事件可达。
- 恢复边界：目标启动未闭合时保留停止意图，但暂停自动cancel_start，允许用户先执行必要的recover；恢复完成后再确认原目标，不循环取消阻塞恢复入口。
- 新增故障测试全部合成执行，不是CST求解故障验收。测试资源清理后只保留轻量XML；不再引用临时目录中的原始结果为可访问产物。
- 本机socket测试需要脱离限制回环访问的执行沙箱；沙箱内首次尝试通信失败不计为产品验收失败，也不算通过。

## 本轮结果与剩余TODO

最终完整离线回归595 passed、21 integration deselected（60.60s），报告artifacts/runner-audit-fix-20261015.xml；故障与文档/日志索引专项27 passed，报告artifacts/runner-audit-focused-20261015.xml。artifacts不保证随Git迁移。
另以独立解释器禁止导入真实Backend、HomScanAlgorithm和Manager后，草稿构造、ConfigurationService及run_payload JSON往返通过；这是依赖隔离验收，不是求解验收。

- [x] A1–A4及M1实现和新增故障测试。
- [x] API、设计/TODO、知识库和功能索引同批同步。
- [x] 完整离线回归与文档/日志索引最终复跑。
- [ ] 实际桌面控制权/切换/安全退出交互人工验收。
- [ ] 真实CST Completion/received/Ack/采用各窗口的控制器崩溃注入，另行授权串行副本验收。
- [ ] 修复版重新打包/发布（本轮未授权）。

E6–E9远程/分布式仍未实施。本轮不把网络故障恢复推导为远程部署或真实CST异常恢复已全部通过。
