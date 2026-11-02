# B1 保存工程只读来源

## 原生采集/RunStore及B4子集（2026-11-02）

[共享采集链](native-execution-capture.md)已冻结意图/nonce/来源和安装，三阶段固定原生帧，六字段pre必须不存在才能Start，退出后归档DB并绑定对账。真实小网格Pillbox正常1模式、实际Start=0/0模式且配置匹配、旧库拒绝均取得副本证据，回执不将失败退出1写成正常成功；索引缺失可补且不重算。按用户要求2022大版本共用行为规则，精确版本/hash仍留档。默认Managed/HOM及公共single-simulation服务未自动接入，完整B4/G03/MCP闭环仍待完成。此前“采集/RunStore未实现”是较早阶段记录。


## B3执行快照内核实施（2026-11-02）

[公共只读验证器](execution-snapshot-verification.md)已实现六维绑定、固定2022.5/root/Tet profile、时间/阶段核对、6位g精度、严格快照JSON及实际数据库双hash。11项E oracle实际执行，另重放6组历史原生字符串；B2新增exact_values避免预期先转float丢精度。B3采集/RunStore权威接入及B4新副本未验，publish_ready始终false；不证明live、求解/结果/退出成功。下文B3未实现及56项全部not-run是历史阶段记录。


## B2首阶段历史与身份完成（2026-11-02）

[51项命令profile](a1-history-command-profile.md)已实现完整人工Pillbox XYZ历史投影：从同一scope有效历史核验mm/MHz、显式ChangeSolverType；不再接收调用者frequency_unit，元数据/注释不能补缺。修正Reset对象归属并拒绝无依据Mesh/MeshSettings.Reset，保留表达式、逐字段来源与失败语句定位。首阶段静态子集完成，不代表任意旧模板、实际保存重建、live身份或MCP服务器通过；B3/B4/G03仍待验。下文“完整历史允许表和单位身份pending”是本批之前状态。


## B2子集实施更新（2026-11-02）

已新增[受限历史投影](settings-history-projection.md)：H/S/M共35项语义oracle实际执行通过，保留表达式、逐字段来源与缺失配置，未知调用清空字段并拒绝。B1与新投影组合只读入口已实现；完整历史允许表、单位/solver身份锚点及B3仍pending，G03未通过，MCP服务器未实现。下文56项not-run是B0历史记录，不代表本轮35项仍未执行；未实施执行快照、启动CST或迁移GUI/CLI。


2026-11-02。入口 `csttool.saved_project_source.read_saved_source(path, scope=...)`。

## 共用底层与发布

当前 cst_version 没有独立可安装的只读包。本项目固定摘取其 CstFile 只读方法，放在 `csttool/_vendor/cstv_readonly.py`，不是另写容器解析器。来源整文件哈希及摘取范围见同目录 provenance.json；摘取后方法未修改。兄弟仓库不改动，因此这是固定上游快照复用，不是两个仓库已共同依赖一个新发布包。未来上游更新必须重新摘取、核对差异与测试，不能自动跟随。没有引入写容器、表达式执行或 CLI 能力。

源码发布器和 setuptools 均携带源码与来源清单；运行不导入开发机绝对路径。当前GUI/Runner已有读取入口不在B1迁移范围，新验证器后续使用本入口；没有宣称全部旧读取已统一。

## 输入、产物和边界

scope 必须是 project_scopes 的精确身份，例如 root 或 SP/FME。拒绝 None、空串、方便别名及未知作用域，不补前缀。所有结果来自同一 bytes 快照。返回冻结 SavedSource，members/member_hashes 是只读映射；保存路径、工程 SHA256、精确scope、scope清单及四种保存成员的原字节和 SHA256。成员名是scope相对路径。缺少成员返回 None，不推断默认设置。

四种成员为 Model/3D/Model.mod、Model/Parameters.json、Model/simulationproperties.json、Model/Model.prj。没有历史解释、参数求值或当前会话设置判断；publish_ready不在此层产生。json()严格拒绝重复键、非对象、非有限常量及坏JSON；不做完整业务Schema验证。text()默认严格UTF-8，失败为 unsupported/encoding-profile-missing；明确 encoding=utf-8 时违反声明为 malformed。未支持其他编码profile，不猜测系统ANSI、不replace。

共享组件负责中央目录、成员定位、大小及CRC；适配器额外检查目录尾、条目数一致、局部flags/method与目录一致、payload不重叠及有界deflate输出/结束边界。仅选中四类成员验证payload CRC，不声称所有工程成员均已解压核验。其他成员目录结构仍检查。没有解包写磁盘。

默认容器256MiB、选中单成员32MiB、选中总展开64MiB、目录10000条；这是初始保守资源策略，不是所有CST文件的格式极限。超限rejected，不截断。源读前后stat身份与第二次有界字节读取不同为stale。持有快照在返回后不会跟随磁盘变化，不保证读取后文件永不改变，也不提供文件锁。文件访问/权限/消失等OS错误原样抛出；协议公共错误映射待统一服务层。

错误包含 status/reason/member，完整性失败不回退扫描。修复损坏源、选择明确scope、提供经审查编码profile或明确提高预算后可重读；stale需重新获取源。原工程只读且表达式保持字节原样。

## 验收与后续

B1离线测试含真实 Pillbox/Enlarged 作用域、JSON严格拒绝、CRC/重复目录/目录尾/压缩故障、预算及读取期间变化。测试不启动CST，不证明live设置或求解行为。B0的56项语义oracle仍not-run；B2历史解释、B3执行快照、B4新实现真实副本及G03仍未完成。

B1最终离线验收：42 passed（2.64s），含17项来源适配测试、4项B0结构检查及既有校准/索引回归；不是56项语义通过。报告 artifacts/b1-offline-20261102.xml。源码打包完整性/哈希、编译/无Qt Runner导入、GUI smoke及隔离进程读取Pillbox通过；不启动CST。artifacts不保证随Git迁移，本轮pytest临时目录已清理。
