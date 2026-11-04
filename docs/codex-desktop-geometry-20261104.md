# Codex桌面GEO对话验收

日期：2026-11-04；实现基线b11ecab。此批使用当前聊天实际发现的14个cst-tools-acceptance工具；不以独立SDK脚本替代桌面调用。状态：受限GEO正常链验收通过；轻量证据见[桌面GEO记录](../knowledge-base/mcp-codex-geometry-20261104.json)。本批没有修改运行代码或重新发布校准许可。

## 范围与执行方式

受管目录artifacts/mcp-host-acceptance中创建新文档geo-desktop-20261104，不修改此前文档或用户原工程。保留参数R=100、L=R表达式；创建Z向Vacuum圆柱，另创建并删除一个辅助Brick，实体集合只保留pillbox。这样既保留解析Pillbox对照，也实际走GEO顺序历史与消费路径，而非隐式降回A1。

公开顺序为connect/claim→create→apply(geometry_profile)→save(geometry)→configure→save(simulation)→inspect→submit→results→JSON/CSV导出及重试→close(save)→shutdown。几何保存必须geometry_saved=true、ready=false、definition_revision=null；完整仿真保存才可ready。

求解范围500–2000MHz、Default/Tet、固定密度4、关闭自适应、nmodes=1、PEC背景、电边界、中心Z线beta=1的Frequency/RQ。正常求解不设固定总超时；启动、通信和退出按生产有界策略。

## 首次连接观察

首次status/installations超时，显式connect(launch=true)也在就绪等待内超时。随后只读核对同一验收目录的OS锁、端口和Runner身份，确认Runner确实存在并可达，再以launch=false连接成功；没有再启动第二个Runner或重复派发CST任务。普通沙箱的进程枚举曾遗漏该外部进程，不能据此判断进程不存在或锁可强占。超时的内部根因未确定，不把随后可达写成“启动从未失败”。

## 证据边界

|核验项|本批实际结果|
|---|---|
|几何目标|geometry_saved=true、ready=false、definition_revision=null；原生保存/重开证明verified|
|仿真目标|ready=true；实际Model.mod分别提取6块几何历史、13块几何与设置历史，独立核对顺序/body和参数表达式|
|参数|R=100、L=R；参数表读回与声明相符；不是把L固定为100|
|物理结果|1147.42692991921 MHz；模式1中心Z全长R/Q=223.541439593232 Ω|
|解析对照|理想TM010为1147.4252783521006 MHz，相对误差约0.000144%，通过5%门限|
|幂等|保存、提交求解及导出均重试同request_id，操作/结果身份一致；实际Start日志计数为1|
|导出|JSON/CSV文件大小及SHA256与工具返回逐项核对|
|原生收尾|7个定义会话exit_confirmed=true、exit_code=0；61条已记录PID/创建时间身份均无本轮进程存活；Worker另有confirmed-closed收尾证明|
|后台退出|close(save)返回closed；公开shutdown受理后Runner PID29172不存在，OS项目锁可取得并释放|
|原有内容|另8份旧文档JSON哈希保持不变；不改写旧定义/结果|

CSTDCMainController、CSTDCSolverServer和cstd服务仍可被枚举；未将名称匹配当作本轮归属，不终止这些服务，也不声称系统中所有CST名称进程均消失。物理退出核验基于本轮记录的精确身份。

工具返回、实际保存的Model.mod/参数表、保存重开观察、生命周期Start计数、采用/导出文件hash、正常退出及文档内容分别核对。辅助Brick被删除后的存活表不证明任意拓扑等价；本次不是网格收敛、复杂CAD、多材料、全故障矩阵或远程计算验收。

原始副本/场位于artifacts，不保证随Git迁移；完成后清理本轮可再生成的二进制，保留宏、日志、参数/哈希及轻量记录。历史11月3日A1桌面验收保持原范围；A1旧许可本批不更新。

## 文档及清理复核

本批文档/登记/迁移、MCP适配及GEO门禁适配共32项通过；未修改运行源码，不重算旧603项数字。清理本轮129个可再生成网格/场/图片二进制；保留轻量CST、原生DB、完整运行归档、宏、日志、参数、导出及哈希，原始场/网格需重新生成。初始冷启动就绪超时作为未定位观察保留，不擅自加长超时或重复派发。
