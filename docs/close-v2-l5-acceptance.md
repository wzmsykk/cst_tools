# L5 WinWrap / CST 串行副本验收

后续[十二个停止/ACK时点](stop-ack-l5-acceptance.md)已真实补验，并修复Completion清理后待采用received记录的发现缺口。下文“完整停止时序pending”保留首轮范围，OS级Controller崩溃/任意指令级停止仍未覆盖。

日期2026-10-24，CST2022.5（2022-06-03，change981760）。本轮原工程为test/data/Pillbox/Pillbox.cst，SHA256 `7b63939b2dbed3de567aa55a5ff19cb69e7447245882a691be15d28580f1ddfa`。
全部使用独立副本，最多一个CST实例；正常批返回，不强杀，不修改许可配置。
L5为部分真实验收，不能把未触发的Start=0、Start异常、退出1和所有停止时点补成通过。

## 发现并修复

受限环境首启FlexNet -63,403，退出3，宏未进入。正常用户权限同命令可运行；这是环境对照，不是Solver故障。未改变许可证设置。

首次正常权限生产启动实际Save成功、StopAck写出、批退出0，但回执引用的活动工程大小从242770变成242773字节，严格核验拒绝。
已证实Save返回到批退出之间活动文件大小变化；具体CST内部写入阶段未定位，不推断所有版本都如此。
修复为Save后Backup到固定`worker-input.cst.closed.cst`，正常saved回执绑定独立快照长度。
恢复路径继续引用`.recovered.cst`。Python/WinWrap同步固定允许列表与保存关联，未放松文件大小/路径/身份校验，退出1规则不变。
这是尚未发布的v2草案修订；旧v2程序不能读取新token，必须两端同批更新，不热替换既有会话。
旧`worker-input.cst` token继续可读，但历史失配证据不会因此被改写或放行。

## 真实门禁与产物

|情形|本轮结果|证据目录（artifacts下）|
|---|---|---|
|首次受限启动|许可证退出3，非宏验收|close-l5-startup-6462119f|
|首次正常权限启动|编译/执行到Save，活动文件变化，收尾门禁正确拒绝|close-l5-startup-cfb09b95|
|修复后启动即关闭|prepared/not-started，独立快照、回执、StopAck、退出0核对通过|close-l5-startup-9bc5956f|
|预处理|cell=8，参数设置进入历史，源哈希不变|close-l5-prepare-ce602cb3|
|正常单模|500–800MHz，nmodes=1，频率503.605585325746MHz；实际频率后处理/任务快照/回执/退出0通过|close-l5-success-9689cbab|
|nmodes=0|真实Rebuild失败；ACK后退役，恢复表达式/Rebuild/Backup/Save，restored-saved回执＋退出4通过|close-l5-rebuild-failure-d322c6e6|
|Default/Tet＋open边界|真实求解器拒绝；Start=1但无可读Eigenmode库，判solver-result失败；退役、无成功任务快照，保存模型与退出0独立成立|close-l5-solver-failure-f6200931|
|求解后后处理入口异常|真实单模Start=1后显式Err.Raise；任务失败、无成功任务快照、不执行recovery-rebuild；e1/eenergy1/h1/henergy1四个.m3t前后SHA256相同，保存模型、收尾回执及退出0通过|close-l5-postprocess-failure-ae7bcbe3|
|WinWrap codec四组golden|startup/saved/restored/failed读写、相同内容幂等、冲突拒绝/原内容保持，四组退出0且无残留|close-l5-codec-6f7969e5|

准备副本SHA256 `b2cd95e9337426de5f3e18fa353c0cbd88fee4203d93444d5921ad1432f7347e`。
边界测试使用已有文档支持的探针，在副本中AddToHistory并回读open，不能将其称为Start返回0或Start异常。
这里只验收Frequency后处理，不代表所有复杂R/Q/三维场匹配验收。
后处理失败为运行时入口异常注入，不冒充某个物理算子本身故障；原始场哈希保持不等于已验证所有场导出/积分可用。
codec使用独立有效Pillbox项目执行宏；receipt中的小字节快照只用于编解码契约，不是可求解模型，未把它交给CST打开。
新增正常收尾需要额外一次Backup，较大工程的时延及副本空间开销尚未量化。

## 七阶段收尾故障

`close-l5-fault-matrix-dd74437e/verification.json`逐项核验实际生命周期日志中的失败阶段、v2错误码、进程死亡和显式恢复结果。
不是仅以测试脚本退出0判断通过。

|点位|触发方式|退出/恢复|
|---|---|---|
|restore|真实WinWrap收尾路径入口Err.Raise；**不是CST恢复API自身故障**|CLOSE_RESTORE_FAILED；拒绝标准关闭，死副本显式abandoned-dead|
|rebuild|恢复后写nmodes=0，真实Rebuild拒绝|CLOSE_REBUILD_FAILED；同上|
|backup|`.recovered.cst`位置建目录，真实Backup写入失败|CLOSE_BACKUP_FAILED；同上|
|save|真实WinWrap收尾路径入口Err.Raise；**不是Save自身故障**|CLOSE_SAVE_FAILED；同上|
|recovery-receipt|`.recovery-saved`位置建目录，真实文件写入失败|CLOSE_RECEIPT_FAILED；同上|
|close-receipt|阻挡`.tmp`发布，正/负回执均不可写|缺v2回执，拒绝降级；死副本仍阻断、保留证据|
|stop-ack|stop.ack位置建目录|正收尾回执存在但Ack无效；拒绝标准关闭，显式恢复继续阻断|

这些故障均实际退出4，但缺少完整收尾组合时仍属异常退出，未因退出4而自动放行。
前五项显式放弃仅证明该副本已死且可以清除归属，不表示恢复了可用计算结果；后两项保留阻断为预期。
`report.json.closure`是Worker自身停止判定；显式恢复后的独立发现判定在verification.json，两者不能混用。

## 工具、验收与剩余

运行工具：[validate_close_v2_l5.py](../test/support/validate_close_v2_l5.py)：run_case、run_codec、verify_fault_matrix。
新固定快照回归：[close_v2_l5_test.py](../test/close_v2_l5_test.py)。源码/假对端通过不能替代上面的真实证据。
离线测试数字、codec golden实际结果及清理结果以current-status最终记录为准。

离线回归729 passed、21 integration deselected（157.40s）；主窗口独立34 passed（1.42s）；最终协议/Worker/文档及日志索引132 passed（12.03s，含重叠）。XML为artifacts/close-l5-{offline,window,focused}-20261024.xml。最后诊断manifest增加close_snapshot由专项覆盖，不冒充此前整仓代码快照的全量复验。

剩余：真正Start=0、Start抛异常、退出1根因，各停止/ACK时序的完整真实矩阵，Save/恢复API自身失败与超大文件FileLen边界，其他CST版本及现场GUI。
不为满足矩阵强制伪造Start返回值或杀进程。上述未触发项继续pending；当前不宣称L5全量完成。
大模型/场文件清理后需重新生成，artifacts不保证随Git迁移；保留轻量日志、宏、回执、哈希及报告。

本轮已在所有进程退出后删除上述十个目录的可再生成.cst/对应模型与原始场数据，共84236805字节；保留report/verification、原生日志副本retained-native、宏、参数与cleanup.json哈希清单。准备模型也已删除，续测先运行工具的prepare，不再把原报告中的模型/场路径当现存数据。清理后的原目录不能直接重跑严格snapshot核验，必须重新生成完整副本；保留的验收结论仅对应清理前实际证据。
