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

后续清理已完成：Manager 只接受 GlobalSettings / ProjectSettings，旧配置输入转换已删除；ConfigManager 的 settings 为唯一运行状态，conf 为序列化副本，修改副本必须重新赋回才能生效。旧 INI 文件解析继续在 configuration 模块中保留，供已有工程读取。

结果文件读取迁移到 postprocess_readers，ModeRec_All 按需加载原有 utils 实现，utils 文件保持不变。已删除未进入生产链的 ModeRec.py、algs/others/gd.py、csttool/result.py 及对应旧结果读取测试；这些文件可从 Git 历史恢复。

后处理配置及 VBA 编译仍由 CstPostProcessor 组织；与结果文件读取职责已经分离。

测试覆盖 Python 调用契约、GUI 假 Worker、HOM 扫描及优化器配置入口。真实 CST 集成测试需要单独执行。
