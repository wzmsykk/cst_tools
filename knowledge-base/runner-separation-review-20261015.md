# 本机 Runner 分离审查（2026-10-15）

后续实施：用户授权后A1–A4及M1已修复，见[修复及故障验收](../docs/runner-audit-fix-20261015.md)。本文保留审查当时结论，不用历史“未修复”覆盖当前状态。

范围：HEAD b63bb77 之上的待提交工作区，包括新增 Runner/GUI 客户端。审查期间未修改执行实现、未启动真实 CST。评估依据为 local-runner.md 与统一实施计划 E0–E5；远程 E6–E9 不在当前交付范围。

## 结论

实施方已收悉并逐项核查，四项缺陷及维护性建议均认可；工作记录、源码依据、拟修复方案和新增验收见
[逐项审计回应](../docs/runner-audit-response-20261015.md)。回应批次未修改执行实现、未启动真实CST，不表示问题已修复。

进程隔离、显式 JSON 命令、OS 所有权、持久命令意图、状态与计算线程分离方向合理，但 GUI 重连和故障语义尚未满足设计闭环，不建议按完整通过验收发布。

## 确认的问题与待办

1. P1：GUI 无法接管崩溃客户端的过期控制权。Runner.snapshot 返回 owner_client 而不反映租约过期；RunnerController.poll 将其他 owner 判为 read_only，_command 又拒绝所有修改（包括隐含 claim）。服务端允许过期后 claim，但 GUI 没有可达入口。应公开控制权有效性/可申请状态，并允许用户申请过期控制权，服务端继续做原子判定。
2. P1：启动响应丢失时丢弃停止意图。RunnerController.poll 的异常分支在 finished_operation == start 时清除 stop_after_start。若服务端已接受 start，用户又选择安全停止后退出，响应超时后重连只观察运行，不会补发 stop，窗口会继续等待。此项为代码路径确认，尚未做 HTTP 故障注入；应保留待停止意图，持有稳定 request_id 并对账对应 run_id 后停止，不能误停另一运行。
3. P2：同一窗口切换新项目不能启动 Runner。RunnerBackend.select_project_directory 只替换 client；Controller.instance 未重置，_observe 使用 launch=self.instance is None，因此第一次连接过项目后，新项目连接一律 launch=False。应按项目重置观察/命令上下文并释放旧控制权，同时防止旧异步响应污染新项目。
4. P2：长日志阻塞全部后续回放。Runner.events 每次 readline(65537)，遇无换行的块又 seek 回 begin；完整 JSONL 行超过上限后永久返回同一 cursor。应区分未写完与超长完整记录，采用有界读取/可展示摘要或明确跳过记录的协议，保证游标推进并保留原始文件。

## 实测与边界

- 测试前 D 盘约 15.19 GiB 可用。本轮 runner_test、runner_recovery_test、gui_runner_test、documentation_index_test：26 passed in 28.20s。不是完整回归或真实 CST 验收。
- 合成探针：owner_seen 回退 11 秒后 snapshot.owner_client 仍是 dead-gui，新客户端 read_only 判定为 True。
- 合成探针：Controller.instance 为前一个项目实例时，新的 client.connect 收到 launch=False。
- 合成探针：70,000 字符 JSONL 消息后附正常记录，连续两次 events(0) 都返回 cursor=0、events=[]。
- 上述探针无 CST 进程/模型。临时测试目录与合成日志在结束后清理，需重新生成，不作为仍可访问的原始产物。
- 待补验收：旧 GUI 持有控制权时崩溃后新 GUI 接管；启动接受但响应丢失并同时请求停止；同窗口跨项目；超长日志后续事件可达。

## 设计质量观察

RunnerBackend 通过实现一组抛异常/空操作的方法适配执行后端接口，且为默认设置实例化 HomScanAlgorithm。后续宜拆分配置草稿接口、执行控制接口与状态 DTO，避免虚假接口替代性；属于维护性建议，不与上述可复现缺陷混为一谈。

原有 571 项历史回归与真实副本验收记录保留；它们不能替代本次发现的故障窗口测试。文档索引只验证入口有效。
