# 缺失模式后处理与同Worker恢复验收

日期：2026-10-13，CST2022.5。入口：`test/support/validate_missing_mode_recovery.py`。

## 设计

只操作cell30 prepared.cst副本，频段513.492631838138–713.492631838138MHz。后处理固定读取Mode 2频率；第一次请求nmodes=1，第二次在同一Worker请求nmodes=2。这是显式故障对照，不改变生产HOM默认nmodes=1。

第一任务必须Failure、无成功后处理值并明确Missing eigenmode #2；失败completion仍需正常Ack并回到ready。第二任务必须Success且Mode 2频率为正。最后检查StopAck、退出0、源SHA不变、无已知重建/批关闭错误；不强制清理进程。

## 首次探针问题

`artifacts/missing-mode-recovery-e6d7e273`第一任务真实返回`RESULT_FLUSH_FAILED: postprocess failed ... Missing eigenmode #2`，用时236.609秒。验收脚本随后直接序列化SimulationResult对象失败，未执行第二轮，不能据此宣称恢复通过。已改用dict转换，与既有验收脚本一致。

该探针finally仍调用标准stop；后续提升权限进程检查未发现CST主实例/Modeler/Solver残留。常驻CSTDC服务未停止。失败日志及协议文件保留；report.json因序列化异常未成功发布。

## 离线复核

相关门禁34通过。受限环境全量回归415通过、1失败、19排除，失败为测试目录rename WinError5；同项提升权限复查通过。完整提升权限回归416通过、19排除（11.16秒）。该差异单独记录，不归因于CST参数或后处理逻辑。

## 修正后真实验收

重跑证据：`artifacts/missing-mode-recovery-d84eee5f/report.json`，验收脚本退出0。

|检查项|实测|
|---|---|
|session|a62c83b7-f358-4ca6-ad29-5fa59e1bf19b，两任务共用|
|第一次任务|f554bbc8-4397-476b-9400-fb3d55781ad0：Failure，Missing eigenmode #2，PostProcessResult及ProjectSnapshot均null|
|恢复任务|94de089e-0db3-41da-a979-67ba8a520ed6：Success，Mode 2频率570.135507219754MHz，有成功快照|
|通信恢复|第一任务正常Ack回到ready，第二任务无需新Worker即可提交并完成|
|关闭|stop_returned=True、stop_ack=True、exit_code=0|
|已知错误门禁|shutdown_errors为空：未发现批关闭sheet及concaveL标量错误|
|原工程|source_unchanged=True，SHA与首次探针及基准相同|
|残留检查|提升权限只读检查无CST主实例、Modeler或Solver进程|

该结果证明本例“求解后必需后处理请求缺失模式→失败completion→Ack→同Worker下一任务成功→标准退出”链路可用。不是Start返回0、真实缺网格、损坏工件、退出卡住或全域物理模式身份的验收。错误分类当前为RESULT_FLUSH_FAILED，详细消息包含postprocess阶段及缺失模式；未新增协议枚举。
