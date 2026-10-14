# Managed可选真空域登记与GUI入口

日期：2026-10-14。默认关闭；不改变HOM默认nmodes=1、标量后处理、VBA协议或求解成功判定。

## GUI使用

扫描与算法设置→“可选：工程前提预检与真空域掩码登记”→选择域设置JSON。单Worker；多Worker启用时明确拒绝，不静默降低并发。取消对话框恢复原设置，未启用时不新增场导出或原生探针。设置页改为可滚动内容、按钮固定底部，避免新增选项挤出确认/取消按钮。

域设置JSON：

```json
{
  "geometry_id": "verified-fixed-cavity-v1",
  "sampling": {
    "bounds_m": [-0.229, 0.229, -0.229, 0.229, -0.1295, 0.1295],
    "counts": [64, 64, 64],
    "scope": "specified-domain"
  },
  "modes": [1]
}
```

边界/范围仅为理想Pillbox示例，不应复制到不同几何。坐标单位m；明确geometry_id不是随意证明几何一致性的字符串，跨几何扫描仍不支持。modes选择场导出编号，不改变求解的nmodes；不存在的场仍按可选工件失败处理。采样精度需要独立收敛证据，不自动认证。

## 实际执行链与API

GUI AlgorithmSettings→HomScanAlgorithm设置→CstApplicationBackend._create_manager→CSTManager(vacuum_domain=...)

1. Manager在创建任何Worker前，独立副本原生工程预检；不符合PEC/封闭真空域规则时拒绝启动Worker。域选项进入执行fingerprint。
2. WorkerConfig.vacuum_domain传到Managed；Manager附加选定mode的ExportModeField/E，不修改参数任务的nmodes。旧标量结果集合不混入场工件。
3. 已成功任务先完成Backup、Completion、Ack和归档；返回DomainRegistration状态pending-after-stop及预期登记/描述符路径，不冒称已登记。
4. 在已核对StopAck和标准退出后，Managed串行处理该Worker的成功快照：生成掩码/登记、vacuum-fields.json和vacuum-tracking-input.json；登记入口加入RunStore映射。回收Worker时也执行此步骤，之后才能启动替代Worker。
5. 不在Warm实例旁启动探针，不在重建历史中调用包围盒查询，不强杀。第一版限制一个Worker以避免其他池实例与原生探针竞争。

独立Worker字典入口vacuumDomain；typed WorkerConfig与CSTManager入口vacuum_domain。Manager负责自动附加场步骤；直接构造Worker时需自行配置ExportModeField，否则只有登记，不得到可用场。

## 状态、失败与恢复

结果中的DomainRegistration是提交时的待办指针，不会原地改变已返回字典。最终状态查path指向的domain-registration.json；错误查归档根的vacuum-domain-error.json和日志事件WORKER_VACUUM_DOMAIN。GUI日志给出任务ID、状态和报告位置。

可选登记失败不改写已确认任务的TaskStatus、不请求Solver重算；保留快照/错误回执。记录写入失败额外提示检查磁盘，不伪造持久化成功。Worker重复stop不再次登记相同待办。标准退出未确认时不会登记，需要先恢复会话；进程强制消失不等于允许开启探针。

当前GUI开关通过域设置JSON中的matching选项可增加固定参考模式匹配；不自动合并HOM、跳频或改变积分线R/Q。GUI报告浏览器及扫描候选请求控制仍待完成。

## 增加模式匹配输出

在域设置JSON中显式增加下列matching对象；没有matching时仍只登记，不执行匹配。策略数值仅示例，非通用物理阈值：

```json
{
  "reference_strategy": "first-valid",
  "policy": {
    "minimum_mac": 0.9,
    "minimum_margin": 0.05,
    "minimum_subspace_overlap": 0.99,
    "maximum_frequency_change": 0.01
  },
  "sampling_evidence": "对应全域采样收敛报告路径和说明"
}
```

reference_strategy=first-valid时，本次运行第一次完整且满秩的结果建立固定锚点；输出reference-established而非matched。之后各任务及回收后的替代Worker共享RunStore/vacuum-reference.json，不因低MAC、漏模或歧义更新锚点。新运行不自动继承旧锚点。

外部参考使用reference_strategy=external，并提供绝对reference_file路径，文件内容应为vacuum-tracking-input.json快照描述符。配置时冻结描述符SHA，匹配时再次核对；源场、掩码等继续由Tracker验证。外部参考丢失/变化返回未确认，不自动换成当前结果。固定参考的原始场不能按临时缓存清理。

每个成功登记任务输出vacuum-mode-matching.json：MAC矩阵、选中模式编号selected_modes、单模匹配或模组子空间重叠/奇异值、参考与候选身份、策略、状态和原因。字段随分支不同：缺场等输入失败不产生虚假的MAC；first-valid建锚点也不产生假匹配。物理身份与阈值校准标志仍False；多模组匹配不指定极化成员身份。

DomainRegistration增加matching_report路径；GUI日志事件WORKER_VACUUM_MATCH报告状态、编号与路径，RunStore提供映射。当前GUI通过原有JSON入口启用与日志查看，不新增矩阵表格页面。

nmodes=1的逐频HOM扫描通常返回不同模式，因此与固定参考不相似/频率不符的结果会unconfirmed，不能据此丢弃该HOM。此功能用于寻找目标模/模组，不代替完整谱枚举。参考组由导出modes明确选择，first-valid最多4个；不按频率相近自动建组。

## 验收

离线测试入口：test/managed_vacuum_domain_test.py、test/gui_config_models_test.py；真实小网格入口test/support/validate_managed_vacuum_domain.py；离屏布局入口test/support/preview_vacuum_domain_dialog.py。Qt离屏参数仅限预览/测试进程，禁止传给CST（已有cst_process_environment过滤）。离屏测试不证明真实桌面的输入、焦点或高DPI行为。

真实证据：`artifacts/managed-vacuum-domain-076454a2/report.json`。Manager创建前原生预检通过，真实cell8显式nmodes2任务成功并导出两mode E场；返回pending-after-stop，标准StopAck/退出后自动registered；生成描述符可载入、两场SHA/坐标可读，Tracker同快照双模检查matched。原工程SHA不变，可靠进程检查无CST主实例/Modeler/Solver残留。该测试证明新Managed链，不替代此前跨mesh身份或整个GUI桌面交互验收。

离屏截图`artifacts/gui-vacuum-domain/settings.png`检查680×720布局：标签、路径、提示与保存/取消可见；预览初次缺字形，辅助程序仅在其自身进程加载系统中文字体后重验，不修改CST或生产GUI字体配置。

最终完整离线484 passed、19 deselected（17.13秒）。新增硬门禁拒绝活跃进程或缺失StopAck的登记，登记只选择配置点集的E工件，已有完全相同ExportModeField步骤不重复附加。域选项在本应用会话持有，旧scan_manifest不自动恢复该开关/文件路径，续算时需明确确认。

本轮大型模型、原生场/HDF5及pytest临时目录已清理；验收报告、登记/掩码、宏、日志和GUI截图保留。报告中的原始场路径仅为历史位置，重新分析需再生成。GUI离屏布局与逻辑已验收，真实桌面焦点/缩放/鼠标交互仍不由该证据证明。

### 自动匹配补充验收

`artifacts/managed-vacuum-domain-5fc7a299/report.json`：`validate_managed_vacuum_domain.py --matching`运行两个cell8重复双模任务。标准退出后第一任务reference-established、第二任务matched，选中Mode1/2；MAC对角约1、非对角约1.25e-10，模组最小平方子空间重叠1。源工程SHA不变，可靠进程检查无CST主实例/Modeler/Solver残留。重复计算可复用CST结果，不把该例称为独立参数扫描或跨mesh验收。

最终离线488 passed、19 deselected（17.65秒）；包含固定锚点、低重叠后恢复、跨Worker复用、缺描述符和外部描述符变更拒绝。匹配报告写入失败不撤销工程登记或求解成功，也不发布假匹配。first-valid建锚点记录是状态记录，不需要假造MAC。

本次重复任务验收原始模型/场与pytest临时工件已清理，参考和匹配报告仅留作历史证据，原始场需重新生成才能复算。生产使用的固定参考必须保留，不能仿照一次性验收清理它。

## GUI假Worker流程验收

入口test/gui_vacuum_matching_fake_flow_test.py。实际使用MainWindow、CstApplicationService、Qt运行控制器、CSTManager及Managed的退出后登记/匹配方法；应用Backend是测试替身，Worker进程状态/StopAck/原生库存是模拟，HDF5为独立合成向量场。禁止任何subprocess.Popen，不能将此测试称为真实CST或生产应用Backend全链实测。

六项新增场景：正常建参考/匹配、低重叠未确认且不重算、Worker回收复用锚点、预检拒绝且零Worker创建、默认关闭且零探针/匹配、运行中关闭窗口等待当前任务结束后再登记。另运行原GUI假Worker成功/并发/失败/关闭四项与固定参考算法四项，共14项通过（1.67秒）。GUI日志检查包含匹配结果。

假Worker用生命周期锁模拟Managed的任务/停止串行化，避免测试替身在任务归档前消费待办。所有未确认结果仍保留成功求解，不增加solver调用；关闭时未执行第二排队任务。此处验证的是逻辑与消息链，不证明Qt真实桌面输入、CST退出或场物理精度。

完整离线494 passed、19 deselected（11.20秒），轻量JUnit记录artifacts/gui-fake-vacuum-matching/regression.xml。测试合成场及pytest临时目录验收后清理，可由pytest重新生成；本轮未运行真实CST。
