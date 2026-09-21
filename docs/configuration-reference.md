# 配置字段参考

## 存储约定

全局配置和项目配置使用 UTF-8 INI。相对路径分别以应用工作目录和项目目录为基准。程序生成的 `current.ini` 与 `project.ini` 是运行状态的一部分，应通过 GUI 或配置管理器修改；带详细注释的模板位于 `config/default.ini` 和 `config/project.example.ini`。

后处理定义、参数清单、运行身份和检查点使用 JSON；扫描与 Mesh 收敛结果使用 CSV。所有程序写入的 INI/JSON 都通过同目录临时文件原子替换。

## 全局配置

### `config`

- `schema_version`：配置结构版本，当前为 `3`。缺失时按旧 schema 1 迁移；高于当前版本时拒绝加载。
- `document_type`：固定为 `global`，便于诊断误用文件。

### `paths`

- `data_dir`：VBA 模板、默认后处理定义等应用资源。
- `temp_dir`：非项目级临时文件。
- `log_dir`：应用日志输出位置。
- `result_dir`：默认结果根目录。项目可以使用自己的结果目录。

### `cst`

- `version`：CST 主版本号，必须与可执行文件安装目录一致。
- `executable`：`CST DESIGN ENVIRONMENT.exe` 的完整路径。版本切换功能会同时更新这两个字段。

### `project`

- `current_directory`：最近使用的项目目录；为空时不自动选择。

### `superfish`

- `directory`、`version`：可选 Superfish 后端信息，不影响 CST HOM 流程。

## 项目配置

### `project`

- `name`：项目显示名称，默认取目录名。
- `description`：可选说明，不参与数值计算和运行身份。

### `paths`

- `result_dir`：正式结果和 Worker 快照目录。
- `temp_dir`：协议文件、生成宏和 Worker 工作副本目录。

### `cst`

- `project_file`：预处理后的 CST 工程副本。Worker 不直接修改输入模板。
- `project_digest`：工程完整性摘要。
- `digest_algorithm`：新工程使用 `sha256`；迁移旧工程时允许 `md5`。

### `execution`

- `use_mpi`：是否启用 MPI。
- `mpi_node_list`：MPI 节点定义，仅在启用 MPI 时生效。
- `use_remote`：是否使用 CST 远程计算服务。
- `controller_address`：远程控制器地址，仅在启用远程计算时生效。

这些字段属于工程级执行策略，不应作为单个 HOM 扫频任务参数反复提交。

### `artifacts`

- `parameters`：CST 参数清单 JSON。预处理完成后生成。
- `postprocess`：版本化后处理定义 JSON。Mesh 收敛分析与正式扫描使用同一份定义。

### `mesh`

- `fixed`：为 `True` 时关闭四面体自适应网格。
- `cells_per_wavelength`：固定网格密度，单位为 cells/λ，必须为正整数。

Mesh 在项目初始化前确定。恢复已有项目时若请求值与记录不一致，程序拒绝继续；修改 Mesh 应创建新项目。启用收敛分析时，分析得到的推荐值会写入正式项目。

### `task`

- `status`：项目生命周期状态。允许值为 `READY`、`RUNNING`、`DONE`、`STOP_REQUESTED`、`INTERRUPTED`、`FAILED`、`RECOVERY_REQUIRED`。

该字段由 Manager 更新，用于恢复和重复提交保护。运行期间不得手工编辑。

## GUI 算法设置

- `fmin`、`fmax`：首次单模求解频段，单位 MHz。
- `endfreq`：HOM 扫描停止频率，单位 MHz。
- `mesh_cells_per_wavelength`：未运行收敛分析时采用的固定 Mesh。
- `mesh_convergence_enabled`：是否在正式项目创建前运行收敛分析。
- `mesh_convergence_start/stop/step`：收敛分析的 cells/λ 序列。
- `mesh_convergence_tolerance`：相邻 Mesh 后处理结果允许的最大相对变化；`0.01` 表示 1%。

收敛分析要求所有选定单模标量后处理结果连续两个级别满足容差。报告输出到 `mesh_convergence/mesh_convergence.json` 和 `.csv`。
