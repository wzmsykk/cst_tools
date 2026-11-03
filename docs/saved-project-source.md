# B1保存工程只读来源

2026-11-03语义核对：本页只描述read_saved_source的只读合同。B2历史投影、B3/B4采集和生产G03/公共单次已接入，源码API不是“仍待实现”；范围见[当前状态](current-status.md)。

2026-11-02。入口 `csttool.saved_project_source.read_saved_source(path, scope=...)`。

## 共用底层与发布

当前 cst_version 没有独立可安装的只读包。本项目固定摘取其 CstFile 只读方法，放在 `csttool/_vendor/cstv_readonly.py`，不是另写容器解析器。来源整文件哈希及摘取范围见同目录 provenance.json；摘取后方法未修改。兄弟仓库不改动，因此这是固定上游快照复用，不是两个仓库已共同依赖一个新发布包。未来上游更新必须重新摘取、核对差异与测试，不能自动跟随。没有引入写容器、表达式执行或 CLI 能力。

源码发布器和 setuptools 均携带源码与来源清单；运行不导入开发机绝对路径。当前GUI/Runner已有读取入口不在B1迁移范围，公共验证器已使用本入口；没有宣称全部旧读取已统一。

## 输入、产物和边界

scope 必须是 project_scopes 的精确身份，例如 root 或 SP/FME。拒绝 None、空串、方便别名及未知作用域，不补前缀。所有结果来自同一 bytes 快照。返回冻结 SavedSource，members/member_hashes 是只读映射；保存路径、工程 SHA256、精确scope、scope清单及四种保存成员的原字节和 SHA256。成员名是scope相对路径。缺少成员返回 None，不推断默认设置。

四种成员为 Model/3D/Model.mod、Model/Parameters.json、Model/simulationproperties.json、Model/Model.prj。没有历史解释、参数求值或当前会话设置判断；publish_ready不在此层产生。json()严格拒绝重复键、非对象、非有限常量及坏JSON；不做完整业务Schema验证。text()默认严格UTF-8，失败为 unsupported/encoding-profile-missing；明确 encoding=utf-8 时违反声明为 malformed。未支持其他编码profile，不猜测系统ANSI、不replace。

共享组件负责中央目录、成员定位、大小及CRC；适配器额外检查目录尾、条目数一致、局部flags/method与目录一致、payload不重叠及有界deflate输出/结束边界。仅选中四类成员验证payload CRC，不声称所有工程成员均已解压核验。其他成员目录结构仍检查。没有解包写磁盘。

默认容器256MiB、选中单成员32MiB、选中总展开64MiB、目录10000条；这是初始保守资源策略，不是所有CST文件的格式极限。超限rejected，不截断。源读前后stat身份与第二次有界字节读取不同为stale。持有快照在返回后不会跟随磁盘变化，不保证读取后文件永不改变，也不提供文件锁。文件访问/权限/消失等OS错误原样抛出；库不生成MCP错误；当前Runner按既有异常通道传播，不能据SourceError.status推断每种失败已有专用公共错误码。

错误包含 status/reason/member，完整性失败不回退扫描。修复损坏源、选择明确scope、提供经审查编码profile或明确提高预算后可重读；stale需重新获取源。原工程只读且表达式保持字节原样。

## 验收与后续

B1离线测试含真实 Pillbox/Enlarged 作用域、JSON严格拒绝、CRC/重复目录/目录尾/压缩故障、预算及读取期间变化。测试不启动CST，不证明live设置或求解行为。B0的原始结构用例不能当全部原生语义通过；B2/B3和公共G03/G04后续证据分别见对应专题，不累加为本页验收。

B1最终离线验收：42 passed（2.64s），含17项来源适配测试、4项B0结构检查及既有校准/索引回归；不是56项语义通过。报告 artifacts/b1-offline-20261102.xml。源码打包完整性/哈希、编译/无Qt Runner导入、GUI smoke及隔离进程读取Pillbox通过；不启动CST。artifacts不保证随Git迁移，本轮pytest临时目录已清理。

B1–B4前批追加进度完整保存在[复审前快照](archive/20261103-semantic-review/saved-project-source.md)，不在本页维持多组相互覆盖的当前状态。
