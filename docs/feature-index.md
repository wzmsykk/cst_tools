# 功能—实现—验收映射入口

日期：2026-10-28。这是维护中的核心功能索引，不是全仓符号清单。先按功能ID查实现，再查工具、日志和验收；历史方案不是现行运行保证。

内部迭代决策：现代MCP协议与唯一共用底层优先；不维护旧API/客户端/协议兼容，所有入口同批迁移并删除旧路径。历史结果保护另行设计显式数据迁移，不以兼容名义保留双框架。生产公共接口仍仅设计；测试用校准探针已存在，不是运行时API实现。

设置验证D15：[验证器设计](cst-settings-verifier-design.md)、[静态证据](../knowledge-base/cst-settings-readback-20261028.md)、[基础V01–V06](../knowledge-base/cst-settings-calibration-20261028.md)、[V05实际网格](../knowledge-base/cst-tet-density-mesh-calibration-20261028.md)、[V01/02/04执行快照及陈旧值](../knowledge-base/cst-solver-settings-readback-calibration-20261028.md)。生产语义读取器/门禁未实现，原生执行快照不可冒充当前live设置。

D15工具映射：[基础设置探针](../test/support/calibrate_cst_settings.py)的`cases`/`render`/`run`/`main`，[网格探针](../test/support/calibrate_tet_mesh.py)的`collect_mesh_evidence`及[有界CBOR](../test/support/tet_options_evidence.py)的`decode_options`，[求解配置探针](../test/support/calibrate_solver_readback.py)的`keys`/`render`/`render_staleness`/`main`，复用[归属门禁](../csttool/acceptance_session.py)。安全测试：[设置](../test/cst_settings_calibration_test.py)、[网格证据](../test/tet_options_evidence_test.py)、[求解读回](../test/solver_readback_calibration_test.py)。V03当前请求数已校准；V05现代通道实际生效、旧通道有上下文限制；V01/02/04可靠读取的是绑定某次尝试的执行快照，6位数字、缺失/陈旧性必须处理。

D15/V06设计验收：[合同与B0–B4顺序](cst-settings-v06-acceptance-plan.md)、[人工用例](../test/fixtures/cst_settings_verifier_v06/cases.json)、[字节证据/来源hash](../test/fixtures/cst_settings_verifier_v06/evidence.json)、[编码/scope边界](../knowledge-base/cst-v06-source-boundaries-20261028.md)，检查入口[v06_casebook_test.py](../test/v06_casebook_test.py)。56项语义预期未执行、5个真实摘录仅证明来源；无生产解释器，V06/G03未通过。

首阶段契约D14：[工程/建模/配置/单次求解/输出冻结](mcp-first-stage-interface-contract.md)、[官方文档与持久化核查](../knowledge-base/cst-first-stage-api-semantics-20261028.md)。九操作及typed变更、single-simulation、作用域/发布顺序/设置读回缺口；仅设计，创建通道/设置验证器未实现。现行映射[预处理](../csttool/cst_preprocessor.py)、[Managed](../csttool/managed_cstworker.py)、[后处理](../csttool/postprocess_cst.py)；既有测试[生成器](../test/postprocess_generator_test.py)、[Worker](../test/managed_cstworker_test.py)，不证明新建模Gate通过。

首阶段门禁D13：[对话建模→仿真设定→计算→后处理输出](mcp-first-stage-conversational-gate.md)。A1必须完成空白副本Pillbox G01–G08；仅协议/控制工具通过不足，当前为验收设计而非已通过。

总体目标D12：[COMSOL MCP功能对齐C01–C11与A0–A4](comsol-mcp-functional-alignment.md)。完整建模/配置/求解/结果链是目标，14运行操作只是A1子集；工程编辑扩展公共服务，未新增运行接口。参照源码/哈希和现行差距见该文。

子契约入口D11：[后处理/优化策略冻结](postprocess-optimization-subschemas.md)、[官方SDK与目标宿主支持证据](../knowledge-base/mcp-sdk-host-support-20261028.md)。13项指标+3特殊操作按实际生成/消费链收敛，文档内JSON Schema及O01–O06阻断；mcp==2.3.0候选、Codex同版本tag的现代开关/stdio条件已核实，桌面握手未验。测试入口[生成器](../test/postprocess_generator_test.py)、[场工件](../test/field_artifacts_test.py)、[优化入口](../test/optimizer_entrypoint_test.py)，现有测试不是新接口实现验收。

契约入口D10：[统一接口契约](unified-interface-contract.md)、[旧入口删除与同步迁移](unified-interface-migration.md)。覆盖14候选操作、公共控制/幂等/错误、结果revision及X01–X14删除清单；现状源码链接在迁移表。仅静态设计，尚无新API实现，子Schema冻结及SDK/宿主静态支持证据见D11；运行接入和握手仍pending。

框架入口D09：[MCP静态框架设计与冻结清单](mcp-framework-static-design.md)。MCP优先、GUI/CLI/MCP共用公共应用服务；原mcp_service专属层提案已替代。模块、内部接口、状态权威及并发生命周期均为设计，未创建运行代码；先完成静态契约审查再进入实现。

设计入口D06：[MCP接入设计与M0–M5计划](mcp-design-plan.md)（仅设计，未实现）。既有映射：[Runner状态/控制](../csttool/runner.py)、[无Qt客户端](../csttool/runner_client.py)、[JSON契约](../csttool/execution_contract.py)、[结果检查点](../csttool/hom_scan.py)、[诊断导出](../csttool/diagnostic_bundle.py)；现有测试入口[Runner](../test/runner_test.py)、[恢复](../test/runner_recovery_test.py)、[诊断](../test/diagnostic_bundle_test.py)。新MCP模块/测试/工具名称只在计划内标为拟定，实施后再登记F项，现有测试不证明MCP通过。

作用域入口D08：[CST官方能力与MCP详细设计](mcp-cst-capability-scope-design.md)。映射[Managed实现](../csttool/managed_cstworker.py)、[生产宏](../data/runtime_managed_worker_v1_main.vb)、[预处理宏](../data/preprocess_hom_parameters_v1.vb)、[原生标量读取](../csttool/native_results.py)；验收入口[Managed离线测试](../test/managed_cstworker_test.py)、[原生结果测试](../test/hom_native_results_test.py)。仅设计审查，原生SDK后端未接入；预处理AddToHistory返回检查待补。

标准入口D07：[MCP官方完整阅读记录](../knowledge-base/mcp-protocol-reading-20261028.md)、[固定来源及SHA256](../knowledge-base/mcp-protocol-sources-20261028.md)、[规范→设计→N01–N25验收矩阵](mcp-protocol-conformance.md)。基线2026-07-28，标准优先于D06第三方参考；矩阵用例尚未实施，当前仅文档链接/静态消息示例核查。

设计入口D03：[Python/VBA生命周期故障矩阵与L1–L5](python-vba-lifecycle-protocol-v2-plan.md)。L1–L4已接入，新会话生成v2；[真实收尾](close-v2-l5-acceptance.md)、[Controller退出](controller-exit-l5-acceptance.md)及[HOM恢复](hom-interruption-l5-acceptance.md)分别记录实际范围。完整L5仍pending，不把部分窗口通过扩大为全矩阵保证。

审计入口D04：[GUI退出、异常资源与发布目录占用](gui-exit-and-directory-lock-audit.md)。定位F14/F44主窗口closeEvent、RunnerController.detach/request_shutdown，F43的RunnerClient.connect工作目录，F45/F12执行资源边界；只记录现状、受控复现及未实施修正，不能当作新退出接口。

2026-10-25修正入口D05：[GUI完整退出与资源清理](gui-exit-resource-cleanup.md)；D04保留修正前证据，现行行为以D05及测试为准。

|ID|功能|源码|函数/类|测试或操作工具|说明文档|
|---|---|---|---|---|---|
|F92|临时Mesh/扩窗/窄窗失败恢复与v4检查点|[hom_scan.py](../csttool/hom_scan.py)|`AdaptiveHomScanner._recover_interval`, `ScanCheckpointStore.save`, `ScanCheckpointStore._load_document`|[确定性恢复/中断/迁移](../test/hom_failure_recovery_test.py)|[恢复流程及边界](hom-solver-failure-recovery.md)|
|F93|已结束失败退出1的严格退役|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker.retire_failed_session`|[协议假对端/篡改/缺ACK](../test/production_close_v2_test.py)、[默认隔离](../test/cstmanager_test.py)|[非标准退役](hom-solver-failure-recovery.md)|
|F90|HOM检查点只读缓存与模式结果表|[hom_dashboard.py](../GUI/hom_dashboard.py)|`HomDisplayReader.read`, `HomModeTableModel.set_modes`, `HomDashboard.update_snapshot`|[数据/缓存/覆盖/大表测试](../test/hom_dashboard_test.py)|[工作台设计](gui-hom-workspace.md)|
|F91|主工作台/详细信息分层及主界面异常摘要|[main_window.py](../GUI/main_window.py)|`MainWindow.__init__`, `MainWindow.renderRunnerSnapshot`, `MainWindow.renderCstProgress`, `MainWindow.onRunError`|[页面/错误测试](../test/hom_dashboard_test.py)、[主窗口回归](../test/gui_main_window_test.py)|[显示分层与边界](gui-hom-workspace.md)|
|F88|有界失败诊断ZIP及源文件映射|[diagnostic_bundle.py](../csttool/diagnostic_bundle.py)|`export_failure_bundle`|[边界/大日志测试](../test/diagnostic_bundle_test.py)|[范围及API](failure-diagnostic-export.md)|
|F89|GUI一键后台导出与退出保护|[main_window.py](../GUI/main_window.py)、[diagnostic_export.py](../GUI/diagnostic_export.py)|`MainWindow.exportFailureLogs`, `MainWindow._diagnosticsFinished`|[Qt异步/错误/关闭测试](../test/gui_diagnostic_export_test.py)|[使用与限制](failure-diagnostic-export.md)|
|F84|同会话停止请求幂等与并发发布|[runtime_protocol.py](../csttool/runtime_protocol.py)|`FileProtocol.request_stop`, `_stop_publication_lock`|[重复/并发/冲突测试](../test/runtime_protocol_test.py)、[失败后重复停止](../test/production_close_v2_test.py)|[现场诊断与边界](solver-failure-stop-idempotency-20261025.md)|
|F85|任务级表达式撤销及逐阶段诊断|[生产宏](../data/runtime_managed_worker_v1_main.vb)|`CSTPMW_RestoreGoodParameters`, `CSTPMW_CloseSession`|[当前VBA契约](../test/vba_document_contract_test.py)、[真实副本工具](../test/support/validate_batch_restore_close.py)|[任务级撤销边界](task-parameter-undo.md)|
|F86|单会话收尾预算及有界阶段观察|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker.stop`, `ManagedCSTWorker._observe_close_progress`|[预算与长日志测试](../test/managed_cstworker_test.py)|[等待边界](parameter-restore-close-budget.md)、[真实验收](batch-restore-real-acceptance-20261025.md)|
|F87|失败重试从预处理基准启动并保留确认结果|[cstmanager.py](../csttool/cstmanager.py)|`CSTManager._execute_task`, `CSTManager._replace_worker`|[失败HOM来源与成功回收](../test/cstmanager_test.py)|[基准与快照区别](parameter-restore-close-budget.md)|
|F81|每用户记忆最后项目选择|[session_store.py](../GUI/session_store.py)|`GuiSessionStore.last_project`, `GuiSessionStore.remember`|[损坏/缺失/跨实例测试](../test/gui_session_restore_test.py)|[自动找回使用与边界](gui-session-restoration.md)|
|F82|只读恢复原项目设置并自动连接|[runner_backend.py](../GUI/runner_backend.py)|`RunnerBackend.restore_last_project`|[真实GUI重开测试](../test/gui_session_process_test.py)|[后台重连及无自动求解](gui-session-restoration.md)|
|F83|启动填充项目与恢复显示|[main_window.py](../GUI/main_window.py)|`MainWindow._restore_previous_project`|[状态/日志回放测试](../test/gui_session_restore_test.py)|[持久项目与运行门禁](gui-session-restoration.md)|
|F77|GUI完整退出编排与持久错误反馈|[main_window.py](../GUI/main_window.py)|`MainWindow._close_runner_window`, `MainWindow._close_local_resources`, `MainWindow._exit_failed`|[GUI退出状态测试](../test/gui_runner_test.py)|[退出契约](gui-exit-resource-cleanup.md)|
|F78|部分构造和异常收尾资源补偿|[runner.py](../csttool/runner.py)|`LocalExecution.__init__`, `LocalExecution.close`, `working_directory`|[资源句柄测试](../test/exit_resources_test.py)|[资源/工作目录边界](gui-exit-resource-cleanup.md)|
|F79|GUI断开时通信池收口|[runner_controller.py](../GUI/runner_controller.py)|`RunnerController.detach`, `RunnerController.poll`|[停止/取消/断开](../test/gui_runner_test.py)|[断开语义](gui-exit-resource-cleanup.md)|
|F80|独立Qt进程完整退出与Windows目录释放|[exit_gui_probe.py](../test/support/exit_gui_probe.py)|`main`|[真实GUI/假Runner进程](../test/exit_process_test.py)|[验收范围](gui-exit-resource-cleanup.md)|
|F76|真实小网格HOM中断恢复及无中断对照|[HOM退出探针](../test/support/validate_hom_exit_l5.py)|`run_case`, `adoption`, `evidence`, `submissions`, `verify_reports`|[探针断言测试](../test/hom_exit_l5_test.py)、[采用对账测试](../test/checkpoint_adoption_test.py)|[HOM验收及边界](hom-interruption-l5-acceptance.md)|
|F62|L3任务级ACK与失败退役|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker._wait_task_ack`, `ManagedCSTWorker.retiring`, `ManagedCSTWorker._build_macro`|[L3假对端专项](../test/production_close_v2_test.py)|[L3状态/时序](production-close-v2-l3.md)|
|F63|L3生产宏状态采集与v2实际发布|[生产宏](../data/runtime_managed_worker_v1_main.vb)|`Main`, `CSTPMW_PublishFailure`, `CSTPMW_CloseSession`, `CSTPMW_CheckStop`|[L3源码契约](../test/production_close_v2_test.py)|[L3保护与门禁](production-close-v2-l3.md)|
|F64|v2实际任务/模型事实采集|[session_closure.py](../csttool/session_closure.py)|`collect_close_evidence`, `_validate_last_received_task`|[L3停止边界测试](../test/production_close_v2_test.py)|[L3身份/关闭边界](production-close-v2-l3.md)|
|F59|L2收尾回执v2及静态版本|[close_receipt.py](../csttool/close_receipt.py)|`CloseReceipt`, `encode_close_receipt`, `decode_close_receipt`, `declare_close_protocol`, `read_close_receipt`|[v2矩阵](../test/close_receipt_test.py)|[v2协议API与边界](close-receipt-v2.md)|
|F60|VBA收尾回执v2库|[runtime_close_receipt_v2.vb](../data/runtime_close_receipt_v2.vb)|`CSTC2_ReadCloseReceipt`, `CSTC2_WriteCloseReceipt`|[源码契约测试](../test/close_receipt_test.py)|[v2 VBA接口](close-receipt-v2.md)|
|F61|v2隔离契约宏生成及产物核验|[close_receipt_contract.py](../csttool/close_receipt_contract.py)|`prepare_close_receipt_contract`, `verify_close_receipt_contract`|[契约测试](../test/close_receipt_test.py)|[v2验收范围](close-receipt-v2.md)|
|F58|L1关闭证据内核及Python退出观测|[session_closure.py](../csttool/session_closure.py)|`CloseEvidence`, `ClosureAssessment`, `evaluate_closure`, `read_recorded_exit`|[L1故障矩阵](../test/session_closure_test.py)|[L1实现与兼容](session-closure-l1.md)|
|F56|GUI后台服务管理|[runner_management_dialog.py](../GUI/runner_management_dialog.py)|`RunnerManagementDialog`|[GUI测试](../test/gui_runner_test.py)|[后台管理](gui-runner-management.md)|
|F57|Runner有界标准退出核验|[runner_client.py](../csttool/runner_client.py)|`RunnerClient.shutdown_and_wait`|[独立假Runner测试](../test/runner_test.py)|[后台管理](gui-runner-management.md)|
|F53|项目恢复公共门禁与检查点校验|[project_recovery_state.py](../csttool/project_recovery_state.py)|`persisted_project_status`, `validate_recovery_checkpoint`|[状态回归](../test/project_recovery_state_test.py)|[恢复状态对账与TODO](project-recovery-state-reconciliation.md)|
|F54|恢复专用配置加载|[配置管理器](../csttool/projectconfmanager.py)|`ProjectConfigManager.load_recovery_configuration`|[状态回归](../test/project_recovery_state_test.py)|[恢复状态对账](project-recovery-state-reconciliation.md)|
|F55|Runner与持久项目状态对账|[Runner](../csttool/runner.py)|`Runner._reconcile_project_state`, `LocalExecution.session_safety`|[GUI恢复入口测试](../test/gui_runner_test.py)|[恢复状态对账](project-recovery-state-reconciliation.md)|
|F01|任务批量调度|[cstmanager.py](../csttool/cstmanager.py)|`CSTManager.run_batch`|[manager测试](../test/cstmanager_test.py)|[Manager API](cstmanager-api.md)|
|F02|工程预处理与历史设置|[cst_preprocessor.py](../csttool/cst_preprocessor.py)|`CstProjectPreprocessor.preprocess`|[预处理测试](../test/cst_preprocessor_test.py)|[作用域修正](concave-expression-scope-rebuild-fix.md)|
|F03|Managed任务与停止|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker.run_task`, `ManagedCSTWorker.stop`|[Worker测试](../test/managed_cstworker_test.py)|[生命周期与回滚](failed-rebuild-stop-recovery.md)|
|F04|VBA参数恢复与批退出|[Managed模板](../data/runtime_managed_worker_v1_main.vb)|`CSTPMW_CaptureTaskParameters`, `CSTPMW_RestoreGoodParameters`, `CSTPMW_CloseSession`|[直接停止探针](../test/support/validate_failed_rebuild_stop.py)|[生命周期与回滚](failed-rebuild-stop-recovery.md)|
|F05|会话发现与恢复|[project_session_recovery.py](../csttool/project_session_recovery.py)|`discover_managed_sessions`, `recover_project_sessions`|[Ack测试](../test/ack_shutdown_contract_test.py)|[运行协议](python-vba-runtime-protocol.md)|
|F06|字段读取与支持域校验|[field_artifacts.py](../csttool/field_artifacts.py)|`read_field`, `artifacts_from_result`|[导出生命周期测试](../test/saved_field_export_lifecycle_test.py)|[算子执行方案](postprocess-operator-execution-plan.md)|
|F07|场匹配诊断|[field_diagnostics.py](../csttool/field_diagnostics.py)|`run_field_diagnostic`|[真实诊断探针](../test/support/validate_managed_field_diagnostic.py)|[六阶段验收](mode-field-selection-implementation-status.md)|
|F08|保存场导出|[saved_field_export.py](../csttool/saved_field_export.py)|`export_saved_fields`|[效率探针](../test/support/benchmark_field_efficiency.py)|[算子执行方案](postprocess-operator-execution-plan.md)|
|F09|求解失败分类与恢复|[Managed模板](../data/runtime_managed_worker_v1_main.vb)|`Main`|[求解失败探针](../test/support/validate_solver_failure_recovery.py)|[历史与失败对照](cst-history-persistence-and-solver-failure.md)|
|F10|历史持久性对照|[持久性探针](../test/support/validate_history_persistence.py)|`main`, `validate_states`|[持久性探针](../test/support/validate_history_persistence.py)|[历史与失败对照](cst-history-persistence-and-solver-failure.md)|
|F11|日志与JSONL上下文|[logging_config.py](../csttool/logging_config.py)|`ContextLogger`, `JsonLineFormatter`|[测试指南](testing-guide.md)|[当前状态](current-status.md)|
|F12|应用后端准备与恢复|[application_backend.py](../csttool/application_backend.py)|`CstApplicationBackend.prepare_run`, `CstApplicationBackend.recover_project_sessions`|[后端测试](../test/application_backend_test.py)|[后端API](application-backend.md)|
|F13|日志事件到源码映射|[log_event_index.py](../csttool/log_event_index.py)|`render_event_table`|[事件同步门禁](../test/log_event_index_test.py)|[事件索引](log-event-index.md)|
|F14|GUI运行控制|[run_controller.py](../GUI/run_controller.py)|`GuiRunController`|[GUI流程测试](../test/gui_fake_worker_flow_test.py)|[GUI路线](gui-refactor-todo.md)|
|F15|任意轴运行时复杂后处理|[EigenResult_Complex.vb](../data/postprocess/EigenResult_Complex.vb)|`EigenResult_Complex`|[VBA语义门禁](../test/vba_document_contract_test.py)|[算子执行方案](postprocess-operator-execution-plan.md)|
|F16|恢复失败真实注入与死会话收口|[故障探针](../test/support/validate_recovery_faults.py)|`run_case`, `reconcile_report`|[停止故障门禁](../test/failed_rebuild_stop_test.py)|[停止故障验收](failed-rebuild-stop-recovery.md)|
|F17|缺场及损坏工件分析恢复验收|[场故障探针](../test/support/validate_field_failure_recovery.py)|`main`, `diagnose_saved_faults`|[工件恢复测试](../test/field_failure_recovery_probe_test.py)|[缺场与工件验收](field-failure-recovery-acceptance.md)|
|F18|共同域与体积求积|[physical_domain.py](../csttool/physical_domain.py)|`common_quadrature`, `sampling_convergence`|[物理域测试](../test/physical_domain_test.py)|[全域验收](physical-domain-pillbox-acceptance.md)|
|F19|原生几何/材料掩码|[geometry_support.py](../csttool/geometry_support.py)|`render_material_support`, `load_material_support`|[Pillbox探针](../test/support/validate_pillbox_full_domain.py)|[全域验收](physical-domain-pillbox-acceptance.md)|
|F20|独立Pillbox双模基准|[pillbox_reference.py](../csttool/pillbox_reference.py)|`tm110_reference`|[Pillbox探针](../test/support/validate_pillbox_full_domain.py)|[全域验收](physical-domain-pillbox-acceptance.md)|
|F21|Pillbox全域第二网格与小网格Tracker验收|[跨网格探针](../test/support/validate_pillbox_cross_mesh.py)|`compare_pair`, `verify_mesh_counts`, `validate_tracker`|[追踪测试](../test/vacuum_mode_tracking_test.py)|[全域验收](physical-domain-pillbox-acceptance.md)|
|F22|封闭真空腔固定参考模式追踪|[vacuum_mode_tracking.py](../csttool/vacuum_mode_tracking.py)|`select_vacuum_modes`, `VacuumModeTracker.evaluate`, `track_saved_sequence`|[追踪测试](../test/vacuum_mode_tracking_test.py)|[第一版API与使用](vacuum-mode-tracking-v1.md)|
|F23|工程前提预检与自动掩码登记|[vacuum_domain_registry.py](../csttool/vacuum_domain_registry.py)|`register_vacuum_domain`, `load_registered_support`, `export_registered_vacuum_fields`|[登记测试](../test/vacuum_domain_registry_test.py)|[登记API与边界](vacuum-domain-registration.md)|
|F24|Managed可选退出后登记|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker._finish_domain_registration`|[可选链测试](../test/managed_vacuum_domain_test.py)|[GUI与生命周期](managed-vacuum-domain-gui.md)|
|F25|GUI真空域设置开关|[algorithm_settings_dialog.py](../GUI/algorithm_settings_dialog.py)|`AlgorithmSettingsDialog.setValues`|[GUI配置测试](../test/gui_config_models_test.py)|[GUI与生命周期](managed-vacuum-domain-gui.md)|
|F26|Managed固定参考模式匹配|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker._run_vacuum_matching`|[匹配链测试](../test/managed_vacuum_matching_test.py)|[GUI与生命周期](managed-vacuum-domain-gui.md)|
|F27|GUI登记/匹配假Worker流程|[假Worker验收](../test/gui_vacuum_matching_fake_flow_test.py)|`MatchingFakeWorker`, `MatchingFakeBackend`|[流程测试](../test/gui_vacuum_matching_fake_flow_test.py)|[GUI与生命周期](managed-vacuum-domain-gui.md)|
|F28|随机谱HOM假Worker与异常扫描|[hom_fake_worker.py](../test/support/hom_fake_worker.py)|`ProbabilisticHomWorker`|[随机谱测试](../test/hom_probabilistic_fake_worker_test.py)|[HOM假Worker验收](fake-hom-acceptance.md)|
|F29|预处理阶段监测、修改明细与失败保留|[cst_preprocessor.py](../csttool/cst_preprocessor.py)|`CstProjectPreprocessor._run`, `CstProjectPreprocessor._log_details`, `CstProjectPreprocessor._observer`|[预处理测试](../test/cst_preprocessor_test.py)|[预处理诊断](preprocess-diagnostics.md)|
|F30|HOM预处理保留mesh选项与恢复策略|[projectconfmanager.py](../csttool/projectconfmanager.py)|`ProjectConfigManager.prepare_project`|[mesh策略测试](../test/projectconfmanager_mesh_test.py)|[预处理诊断](preprocess-diagnostics.md)|
|F31|GUI预处理保留mesh交互|[algorithm_settings_dialog.py](../GUI/algorithm_settings_dialog.py)|`AlgorithmSettingsDialog._set_preserve_mesh`|[GUI配置测试](../test/gui_config_models_test.py)|[预处理诊断](preprocess-diagnostics.md)|
|F32|CST任务级归属、共享实例诊断与退出门禁|[acceptance_session.py](../csttool/acceptance_session.py)|`wait_probe`, `task_project_processes`|[进程监测测试](../test/acceptance_session_test.py)|[预处理诊断](preprocess-diagnostics.md)|
|F33|GUI长日志有界批量显示与滚动（无清空API）|[log_view.py](../GUI/log_view.py)|`QPlainTextEditLogger.emit`, `QPlainTextEditLogger.flush_pending`|[日志显示测试](../test/gui_log_view_test.py)|[日志显示性能](gui-log-performance.md)|
|F34|GUI事件模型、组合筛选、详情及原始文件入口|[event_log_view.py](../GUI/event_log_view.py)|`EventTableModel.append_events`, `EventFilter.filterAcceptsRow`, `StructuredLogHandler.show_details`, `StructuredLogHandler.file_path`|[结构化日志测试](../test/gui_event_log_view_test.py)|[结构化事件使用](gui-structured-log.md)|
|F35|可读摘要、完整文本上下文及异常传播引用|[logging_config.py](../csttool/logging_config.py)|`DiagnosticTextFormatter.format`, `normalized_context`, `log_failure`|[日志配置测试](../test/logging_config_test.py)、[Worker顺序测试](../test/managed_cstworker_test.py)|[六链日志设计](readable-logging.md)|
|F36|Worker不取任务锁的协作停止|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker.request_stop`|[停止及续跑测试](../test/cooperative_stop_resume_test.py)|[停止与覆盖续跑](cooperative-stop-and-hom-resume.md)|
|F37|VBA步骤停止检查与中断求解保留|[Managed模板](../data/runtime_managed_worker_v1_main.vb)|`CSTPMW_CheckStop`|[停止及续跑测试](../test/cooperative_stop_resume_test.py)|[停止与覆盖续跑](cooperative-stop-and-hom-resume.md)|
|F38|可读运行日志目录、摘要、旧目录总览|[run_overview.py](../csttool/run_overview.py)|`RunOverview.update`, `RunOverviewHandler.emit`, `rebuild_log_index`|[运行总览测试](../test/run_overview_test.py)|[可读日志目录](readable-log-directories.md)|
|F40|运行级持久停止意图与最小契约|[execution_contract.py](../csttool/execution_contract.py)|`StopIntent.check`, `StopIntent.request`, `ArtifactRef`, `validate_command`|[恢复测试](../test/runner_recovery_test.py)|[本机Runner](local-runner.md)|
|F41|独立Runner及持久本机命令|[runner.py](../csttool/runner.py)|`Runner.command`, `Runner.snapshot`, `LocalExecution.run`, `serve`|[进程验收](../test/runner_test.py)|[本机Runner](local-runner.md)|
|F42|控制器OS所有权与受保护目录|[runner_ownership.py](../csttool/runner_ownership.py)|`RunnerOwnership.acquire`, `protect_directory`|[进程验收](../test/runner_test.py)|[统一计划](execution-platform-implementation-plan.md)|
|F43|本机Runner发现/启动/CLI|[runner_client.py](../csttool/runner_client.py)|`RunnerClient.connect`, `RunnerClient.command`, `main`|[进程验收](../test/runner_test.py)|[本机Runner](local-runner.md)|
|F44|生产GUI客户端与重连|[runner_controller.py](../GUI/runner_controller.py)|`RunnerController.poll`, `RunnerController.detach`|[GUI测试](../test/gui_runner_test.py)|[本机Runner](local-runner.md)|
|F45|有限标准批次和持久采用|[standard_batch.py](../csttool/standard_batch.py)|`StandardBatchAlgorithm.start`|[真实副本验收](../test/runner_cst_integration_test.py)|[本机Runner](local-runner.md)|
|F46|完成未接收的结果核验导入|[result_reconciliation.py](../csttool/result_reconciliation.py)|`recover_completed_result`|[恢复测试](../test/runner_recovery_test.py)|[本机Runner](local-runner.md)|

## 从日志定位

|功能ID|目的|源码|函数|测试|说明|
|---|---|---|---|---|---|
|F73|检查点已确认采用标记补写|[checkpoint_adoption.py](../csttool/checkpoint_adoption.py)|`confirmed_tasks`, `reconcile_checkpoint_adoptions`, `mark_adopted`|[身份/幂等/故障矩阵](../test/checkpoint_adoption_test.py)|[采用对账](checkpoint-adoption-l5.md)|
|F74|RunStore日志/索引幂等采用与共享锁|[run_store.py](../csttool/run_store.py)|`RunStore.ensure_adopted`, `RunStore._adoption_events`|[并发/截断/部分写入](../test/checkpoint_adoption_test.py)|[写入顺序及边界](checkpoint-adoption-l5.md)|
|F75|真实采用标记三个退出窗口复核|[validate_controller_exit_l5.py](../test/support/validate_controller_exit_l5.py)|`marker_state`, `marker_hashes`, `verify_adoption_reports`|[真实串行记录](checkpoint-adoption-l5.md)|[Controller验收](controller-exit-l5-acceptance.md)|

|功能ID|目的|源码|函数|测试|说明|
|---|---|---|---|---|---|
|F70|L5 GUI/Runner进程退出与真实恢复|[validate_controller_exit_l5.py](../test/support/validate_controller_exit_l5.py)|`run_case`, `runner_child`, `gui_child`, `verify_reports`|[退出相关回归](../test/controller_exit_l5_test.py)|[六类真实记录](controller-exit-l5-acceptance.md)|
|F71|已完成归档的接收路径恢复|[result_reconciliation.py](../csttool/result_reconciliation.py)|`reconcile_archive_receipt`, `recover_completed_result`, `find_received_result`|[身份/哈希/歧义回归](../test/controller_exit_l5_test.py)|[归档缺口与边界](controller-exit-l5-acceptance.md)|
|F72|线程收尾与客户端可启动状态|[runner.py](../csttool/runner.py)|`Runner.snapshot`|[活跃快照](../test/controller_exit_l5_test.py)、[GUI等待](../test/gui_runner_test.py)|[API及收尾竞态](controller-exit-l5-acceptance.md)|

|功能ID|目的|源码|函数|测试|说明|
|---|---|---|---|---|---|
|F68|Completion清理后的待采用结果恢复发现|[project_session_recovery.py](../csttool/project_session_recovery.py)|`_pending_result_task`, `ManagedSessionRecord.closure`|[停止/ACK回归](../test/stop_ack_l5_test.py)|[实际缺口与修复](stop-ack-l5-acceptance.md)|
|F69|真实停止/ACK时序与产物复核|[validate_stop_ack_l5.py](../test/support/validate_stop_ack_l5.py)|`run_timing`, `read_current_completion`, `verify_timing_reports`|[探针契约](../test/stop_ack_l5_test.py)|[十二时点验收](stop-ack-l5-acceptance.md)|

|功能ID|目的|源码|函数|测试|说明|
|---|---|---|---|---|---|
|F67|L5串行真实副本与故障核验|[validate_close_v2_l5.py](../test/support/validate_close_v2_l5.py)|`run_case`, `run_codec`, `verify_fault_matrix`|[固定收尾快照测试](../test/close_v2_l5_test.py)|[真实验收与剩余](close-v2-l5-acceptance.md)|

|功能ID|目的|源码|函数|测试|说明|
|---|---|---|---|---|---|
|F65|L4生命周期事实与异常原因链|[lifecycle_diagnostics.py](../csttool/lifecycle_diagnostics.py)|`project_lifecycle`, `lifecycle_facts`, `result_observation`, `error_diagnostic`|[事实测试](../test/lifecycle_diagnostics_test.py)|[Runner/GUI事实](runner-lifecycle-l4.md)|
|F66|L4 GUI诊断与源码展示|[lifecycle_display.py](../GUI/lifecycle_display.py)|`lifecycle_lines`, `runner_error_text`|[GUI测试](../test/gui_runner_test.py)|[使用及边界](runner-lifecycle-l4.md)|

Runner审计修复：F41/F43/F44增加`cancel_start`和命令对账，当前API及门禁见[修复记录](runner-audit-fix-20261015.md)。

|功能ID|功能|源码|函数/类型|测试|说明|
|---|---|---|---|---|---|
|F47|有界JSONL游标与异常记录跳过|[event_replay.py](../csttool/event_replay.py)|`read_events`|[审计回归](../test/runner_audit_regression_test.py)|[Runner API](local-runner.md)|
|F48|纯HOM草稿默认值与mesh校验|[scan_settings.py](../csttool/scan_settings.py)|`default_hom_settings`, `validate_hom_settings`|[审计回归](../test/runner_audit_regression_test.py)|[修复记录](runner-audit-fix-20261015.md)|
|F49|配置草稿与显式进程内执行适配|[application_service.py](../GUI/application_service.py)|`ConfigurationDraft`, `ConfigurationService`, `CstApplicationService`|[服务测试](../test/gui_application_service_test.py)|[Runner API](local-runner.md)|
|F50|自动恢复任务摘要及日志保留|[main_window.py](../GUI/main_window.py)|`MainWindow.renderRunnerSnapshot`|[日志恢复测试](../test/gui_log_restore_test.py)|[日志恢复API与边界](gui-log-restoration.md)|
|F51|默认开启的日志自动滚动开关|[event_log_view.py](../GUI/event_log_view.py)|`StructuredLogHandler.set_auto_scroll`, `StructuredLogHandler.go_latest`|[事件显示测试](../test/gui_event_log_view_test.py)、[原始镜像测试](../test/gui_log_view_test.py)|[结构化日志使用](gui-structured-log.md)|
|F52|原生阶段标准键及原文保留（含用户日志四阶段）|[cst_progress.py](../csttool/cst_progress.py)|`normalize_cst_stage`, `CstProgressEvent`|[原生进度测试](../test/native_progress_test.py)、[GUI显示](../test/gui_main_window_test.py)|[原生阶段记录](cst-native-progress-observation.md)|

停止与退出确认：F39，源码 [MainWindow](../GUI/main_window.py) 的 `closeEvent`、`requestStop`、`_confirm_action` 和 [Controller](../GUI/run_controller.py) 的 `_stop_failed`；测试 [GUI测试](../test/gui_main_window_test.py)，说明 [停止/退出](gui-stop-exit.md)。

- 使用run_id→session_id→task_id，先查RunStore与received记录，再查协议目录和lifecycle.log；不能仅按时间猜任务。
- `WORKER_TASK_COMPLETE`：F03；`REBUILD_FAILED`、`SOLVER_FAILED`：F09；`WORKER_STOP_FAILED`：F03/F04/F05。
- `stage=restore-parameters/recovery-rebuild/save/stop-ack/batch-return`：F04；检查点位于工作副本旁`worker-input.cst.last-good-parameters.tsv`。
- 核对最近证据：`docs/current-status.md`→具体验收文档→artifacts/report.json。大型原始模型/场文件可能未提交。

## 维护

F40–F44审计回应：[收悉工作记录及逐项结论](runner-audit-response-20261015.md)保留修复前历史；四项缺陷/M1现已修复，当前验收及剩余门禁见[修复记录](runner-audit-fix-20261015.md)。

F40–F44历史审查边界：[2026-10-15本机分离审查](../knowledge-base/runner-separation-review-20261015.md)，涉及 Runner.snapshot/events 与 RunnerController.poll/_observe/_command；现行映射包括F47–F49，不将原审查“未修复”作为当前结论。

实施总入口D00：[统一实施计划E0–E9](execution-platform-implementation-plan.md)。本机E0–E5主链已实施，实际验收及未完成门禁以该文为准；D01/D02保留设计细节。

规划入口D02（未实施）：[远程/分布式扩展设计](remote-distributed-execution-design.md)，含任务/尝试身份、所有权代次、数据位置、Warm亲和及阶段验收；当前本地源码约束与复用映射见该文第10节。

设计入口D01：[GUI/Runner分离设计与TODO](gui-runner-process-separation-design.md)。历史拟议方案保留，当前接口见[本机Runner](local-runner.md)，实际实现映射见F40–F46。

遵守根目录[AGENTS.md](../AGENTS.md)。索引测试检查本地链接和Python/VBA符号，不自动证明功能完整或更新 prose 内容；实现者必须同步状态、用途、限制与验收证据。

F85/F86/F88现场补证：[2026-10-25 16:51诊断包](field-failure-bundle-20261025.md)。任务级恢复已在复杂用户模型观察到2项/5秒；阻断为退出1及顶层原因缺失，不是收尾预算超时。原包不含模型，不能在本机复核快照。

|F94|GUI扫描目标与首窗频率命名|[algorithm_settings_dialog.py](../GUI/algorithm_settings_dialog.py)|`AlgorithmSettingsDialog.__init__`|[配置与标签测试](../test/gui_config_models_test.py)|[HOM工作台](gui-hom-workspace.md)|

|F95|Worker递增实例身份|[实现](../csttool/cstmanager.py)|`CSTManager._allocate_worker_id`|[回归](../test/cstmanager_test.py)|[迁移对照](local-fix-migration-20261028.md)|
|F96|prepared工程与配套目录复制|[实现](../csttool/managed_cstworker.py)|`ManagedCSTWorker._prepare_project_copy`|[回归](../test/managed_cstworker_test.py)|[迁移对照](local-fix-migration-20261028.md)|
|F97|前向优先HOM续扫与缺口补算|[实现](../csttool/hom_scan_algorithm.py)|`HomScanAlgorithm.start`|[回归](../test/hom_scan_test.py)|[迁移对照](local-fix-migration-20261028.md)|
|F98|停止期间CST进度与旧会话过滤|[实现](../GUI/main_window.py)|`MainWindow.renderCstProgress`|[回归](../test/gui_main_window_test.py)|[迁移对照](local-fix-migration-20261028.md)|

|F99|本机配置生成与忽略约定|[配置管理](../csttool/globalconfmanager.py)|`GlobalConfigManager.__init__`|[文档索引](../test/documentation_index_test.py)|[本机产物](local-generated-files.md)|
