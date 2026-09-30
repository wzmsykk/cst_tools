# Python API 清理记录

生产 Backend、Manager、Worker、算法与后处理接口已迁移到 snake_case。

| 原调用 | 当前调用 |
| --- | --- |
| `myAlg` | `Algorithm` |
| `myAlg01` | `HomScanAlgorithm` |
| TM020 `myAlg_nsga` | `Tm020NsgaAlgorithm` |
| WTC `myAlg_nsga` | `WtcNsgaAlgorithm` |
| `setJobManager` | `set_job_manager` |
| `setCSTParams` | `set_cst_parameters` |
| `getEditableAttrs` / `setEditableAttrs` | `get_editable_attributes` / `set_editable_attributes` |
| `runWithParam` | `run_task` |
| `getResultDir()` | `result_directory` 属性 |
| `VBPostProcessor` | `CstPostProcessor` |

旧算法类名与 camelCase 包装已移除，外部脚本需要按上述表迁移。
TM020、WTC 原来缺少配置抽象方法，现支持 population_size、generations、mesh_cells_per_wavelength；恢复执行仍受各算法自身的 checkpoint 能力限制。

尚存的历史实现：ConfigManager 内部 INI 状态处理、Manager 的旧配置输入转换、ModeRec_All 的模式识别实现，以及未进入生产链的离线分析脚本。后续应分别迁移并验证，不应将本次命名迁移视为它们已完成重构。

测试覆盖 Python 调用契约、GUI 假 Worker、HOM 扫描及优化器配置入口。真实 CST 集成测试需要单独执行。
