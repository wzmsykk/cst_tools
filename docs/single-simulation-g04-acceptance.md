# G04公共单次服务串行副本验收（2026-11-02）

> 适用性复审（2026-11-03）：原批次实施/故障/验收记录；旧当前、未提交、待做及现场进程状态不代表本次实时事实。现行实现见[当前状态](current-status.md)、[功能索引](feature-index.md)及对应API；不重算或追认旧证据。

目的：通过生产G03后运行公共single-simulation服务一次，核对本次definition/run/task/session、原生执行采集、completion/ACK、结果快照、RunStore采用与正常关闭。使用开发者验收工具创建工程不等于G01真实MCP宿主/G02公开建模接口已通过，不能宣称首阶段完整闭环通过。

工具：`python test/support/validate_single_simulation.py --cst-exe <授权安装> --run-cst`。真实调用串行，先检查空闲及磁盘；R=100mm、L=100mm，500–2000MHz、Tet cell=4、nmodes=1，背景PEC内部真空。参数保留表达式，持久设置进历史，G03验证在求解前完成；无求解总超时。

本轮启动发现：受限环境COM创建返回0x800706BE；正常用户环境可创建，不据此泛化RPC故障原因。真实WinWrap拒绝缺少前导单引号的#Language声明，修正生产G03及建模探针为注释形式，并加回归断言。COM RunScript异常时单纯释放对象不保证应用退出；新验收工具用finally对自己创建的对象保存并Quit，不使用全局Active3D。首次遗留空实例由用户正常关闭，后续核验已无该实例。

验收目录：`artifacts/single-g04-24e6dd99`。本页将根据实际运行结果更新；旧B4或离线回归不能代替此组合验收。轻量回归报告：`artifacts/g04-offline-20261102.xml`（39 passed，25.17秒）。

## 实际结果

CST 2022.5；生产G03两会话通过，Managed仅调用Solver.Start一次（20:49:38–20:49:46），返回1、calculated_modes=1、原生数据库hash匹配、completion/ACK及采用通过、standard_closed=true，最终进程检查无本轮CST/modeler。频率1147.42692991921MHz，中心Z轴R/Q=223.541439593232Ω。理想TM010频率1147.425278354MHz，粗网格偏差0.000144%；此频率合理性不单独证明场型。

可迁移轻量证据：[归档JSON](../knowledge-base/single-simulation-g04-evidence-20261102.json)。原始宏、G03读回、生命周期、ACK/采用及数据库归档在artifacts目录，不保证随Git迁移。本轮可再生成临时模型及原始场/网格清理后不再保证可读取；源定义、结果.cst及轻量证据保留，完整三维场需重算。

G04本次组合通过；G01真实宿主、G02公开建模服务、故障矩阵及跨版本不在本次结论范围。

最终相关回归及索引40 passed（25.41秒），报告artifacts/g04-final-20261102.xml。已清理本轮pytest临时目录和成功验收工程同名结果/网格目录，保留.cst、宏副本、日志、原生帧、数据库归档及结果JSON。原始场不可再访问，需重算。
