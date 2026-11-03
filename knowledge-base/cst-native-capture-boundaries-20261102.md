# 原生采集B4新观察

> 适用性复审（2026-11-03）：按本条原日期、来源/样本范围引用；原当前/未实现/进程或artifact存在性不作实时保证。本次不复验原数据或外部结论，现行执行见[当前状态](../docs/current-status.md)。

2026-11-02，仅对本机CST2022.5受控副本有效。详见[流程、根目录及证据](../docs/native-execution-capture.md)。

**文档定义**：官方Project Object的GetProjectPath("Project")返回无.cst后缀的计算目录；GetApplicationVersion返回版本字符串，文档没有保证其格式与二进制中完整release/change标签相同。GetOwnProject代表当前工程，不意味着应在空工程编译后OpenFile切换scope。

**本轮实测**：GetApplicationVersion返回Version 2022.5 - Jun 03 2022；与既有2022.5 Release from 2022-06-03 (change 981760)不相等。首次严格比较因此在Start之前正确拒绝错误身份解释。modeler原文件SHA与旧校准一致：a1cb2ec6316592020e81129fa0687343db2c650d82286c79a22ef4e08310db98。此hash只支持该既有版本标签映射；按用户决定，不把未知2022补丁/hash当作单独不兼容证据。

**工程决定**：2022大版本共用规则，精确显示串及launcher/modeler hash仍留档；同一个attempt内安装或捕获身份变化不能默默接受。这是兼容假设，不是所有2022发行版均已实测。

**本轮实测**：启动受限环境时，新旧宏均未出现首阶段标记、进程退出5；非受限相同旧宏正常运行并退出0。此对照支持环境相关，不说明是哪一权限、许可证或启动组件导致；不把退出5一般化为代码错误或固定许可证错误。各次均已确认归属退出，未强杀。

**本轮实测**：fresh source仅复制.cst，pre六个执行字段明确缺失；正常Start后出现，Start=0且最大迭代失败后也出现。带同名结果目录重开时pre六项已有值，采集门禁在Start前拒绝。没有结果重标/自动补算，Start=0不当空区间。

**本轮实测**：正常及实际失败两个RunStore回执可重复对账；删除artifacts索引后补写不改变receipt/event journal，不再调用求解器。结果采用未被模拟，task仍独立走原协议。

**剩余边界**：当前采集只接受ASCII路径/既定missing错误格式、root/Tet与Modes=1；其他2022版本规则按用户假设复用，但其他scope/mesh、完整定义发布、所有Save/Rebuild时间点和MCP宿主闭环未验。raw CST/场清理后只剩轻量帧/日志/归档DB，不得说还能重开原副本；artifact不保证随Git迁移。
