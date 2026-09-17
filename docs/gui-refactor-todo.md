# GUI 重构 TODO

状态：P0–P7 已完成；当前实施记录

## 目标与边界

GUI 重构先修复线程、状态和生命周期边界，再调整布局和交互。当前仍通过适配层调用 legacy `cst_tools_main`；本阶段不切换生产 `CSTManager` 后端，也不修改 Python/VBA Runtime Protocol。

## P0：无界面安全网与确定性启动边界

- [x] 使用 `QT_QPA_PLATFORM=offscreen` 在默认 pytest 中运行真实 Qt Widget。
- [x] 主窗口允许注入假业务后端和假对话框，测试不读取真实配置、不启动 CST。
- [x] 只有项目目录与 CST 文件都已选择时才启用“开始”。
- [x] 取消文件对话框不再用当前目录冒充用户选择。
- [x] `wininit()` 或运行配置准备失败时不启动后台线程。
- [x] 启动后所有操作按钮保持禁用，直到后台 `_signal_end` 到达。
- [x] 后台任务使用 `try/except/finally`，异常时同时发布错误和结束信号。
- [x] Python logging 通过 Qt signal 回到 GUI 线程，不由 Worker 直接修改文本控件。
- [x] 保持现有 `.ui` 布局、算法设置和后处理设置入口不变。

验证记录：GUI P0 定向测试为 `8 passed`；完整默认测试为 `96 passed, 12 deselected`。测试覆盖初始/Ready/Running 状态、输入选择顺序、初始化失败、取消选择、跨线程日志以及后台异常恢复，不需要 CST 或可见桌面。

## P1：运行状态与控制器解耦

- [x] 引入明确的 `RunState`：`IDLE`、`READY`、`RUNNING`、`STOPPING`、`FAILED`。
- [x] 将按钮状态集中为一个状态渲染函数，删除分散的 freeze/unfreeze 方法。
- [x] 用组合式 Qt Worker 替代 `QThread + cst_tools_main` 多重继承。
- [x] 定义最小 `GuiBackend` Protocol，使窗口不依赖 legacy 具体类。
- [x] 将准备阶段放到后台，避免 `prepareProject` 等耗时操作阻塞 GUI 线程。
- [x] 为重复启动、失败后重试和非法状态转换增加测试。

实现记录：`GuiRunController` 独立持有状态与每次运行的 `QThread`，普通 `QObject` Worker 组合调用后端；窗口只提交启动请求并按状态渲染按钮。后台依次执行 flags、环境初始化、工程准备和任务，成功回到 `READY`，失败进入 `FAILED` 且允许重试。GUI 定向测试为 `10 passed`，完整默认测试为 `98 passed, 12 deselected`。

## P2：受控关闭与进度

- [x] 窗口关闭时区分空闲和运行中状态。
- [x] 运行中关闭先请求 Manager/Worker 正常停止并等待完成。
- [x] 标准停止未证明无效时禁止用强制结束进程代替生命周期。
- [x] 增加初始化、准备、运行、停止和完成阶段，以及状态栏进度条和可操作错误信息。

实现记录：运行中关闭会拒绝当前 close event，进入 STOPPING，在独立线程中调用后端 request_stop()；只有运行线程和停止线程都结束后才自动重新关闭窗口。重复关闭不会重复发送停止请求。当前 legacy 算法没有可靠的总任务数/完成任务回调，因此 P2 只显示真实阶段进度 1/4–4/4，不伪造任务百分比。GUI 定向测试为 13 passed，完整默认测试为 101 passed, 12 deselected。

## P2.5：Fake Worker GUI 全流程 Gate

- [x] 保留真实主窗口、GuiRunController、QThread 和 CSTManager，只替换最底层 CST Worker。
- [x] 通过界面按钮完成目录/CST 选择和启动，不直接调用 Manager。
- [x] 成功流程提交两个任务，验证返回顺序、双 Worker 并发和标准关闭。
- [x] Fake Worker 返回 Failure 时，GUI 进入 FAILED、显示可操作错误并允许重试。
- [x] Fake Worker 阻塞期间关闭窗口，验证 STOPPING、CSTManager.stop() 和全部 Worker 停止。
- [x] Gate 不读取真实 CST 配置、不启动 CST，也不创建可见窗口。

验证记录：Fake Worker GUI 全流程 Gate 为 3 passed；完整默认测试为 104 passed, 12 deselected。成功流程的并发峰值为 2，结果顺序为 band-1、band-2；失败和关闭流程最终 Manager 均为 CLOSED，所有创建的 Fake Worker 均收到 stop。

## P2.6：GUI 可调 Worker 并发数

- [x] 主窗口提供 1–64 的 Worker 数量选择，默认保持 2。
- [x] 启动时将选择值冻结到本次运行，并在 RUNNING/STOPPING 期间锁定控件。
- [x] legacy GUI 后端不再硬编码 maxTask=2，由运行请求设置 CSTManager 的池大小。
- [x] Fake Worker Gate 验证选择 1 时只创建一个 Worker，实际并发峰值为 1。
- [x] 不在 GUI 中复制 Manager 调度逻辑。

验证记录：GUI 与 Fake Worker 定向测试为 18 passed。并发数从窗口经 GuiRunController、GuiBackend 传入 CSTManager；运行结束后控件重新启用。

## P3：配置对话框与数据模型

- [x] 算法设置使用有类型配置对象和 Qt Validator。
- [x] 后处理设置使用稳定 method key，显示名称与协议名称分离。
- [x] 列表模型使用 `beginInsertRows/endInsertRows`、`beginRemoveRows/endRemoveRows` 和 reset 通知。
- [x] JSON 文件增加版本、结构校验和明确错误反馈。
- [x] 保留现有配置的兼容读取路径。

实现记录：新增 `AlgorithmSettings` 与 `PostProcessSetting` 类型边界。算法设置校验数字、频率上下限及继续频率；后处理设置校验受支持 method、结果名、Mode Index 和复杂积分参数，并拒绝重复结果名。历史协议 key `Shunt_Inpedence` 保持不变，界面显示为 `Shunt Impedance`。新导出文件使用 `schemaVersion: 1` 与 `postProcesses`，同时继续读取旧的顶层列表；传给 legacy 后端时仍输出原字典结构。P3 与既有 GUI 定向测试为 26 passed，完整默认测试为 114 passed, 12 deselected。

## P4：统一视觉主题

- [x] 建立单一主题模块，主窗口和三个配置窗口共享颜色、字体、边框与交互状态。
- [x] 主操作、次要操作和危险操作使用语义化视觉角色，不按按钮文字硬编码样式。
- [x] 日志区使用高对比深色等宽样式，输入区、列表、进度条和状态栏形成统一层级。
- [x] `RUNNING`、`STOPPING`、`FAILED` 状态拥有明确状态栏反馈。
- [x] 改善窗口标题、占位提示、工具提示和对话框操作文字。
- [x] 保持业务布局、运行协议和 Qt 状态机不变。

实现记录：主题集中在 `GUI/theme.py`，窗口只声明 primary、quiet、danger 等语义角色。主窗口使用“CST Batch Studio”标题，项目/CST 路径改为只读展示，避免用户输入未同步到后端。Qt 离屏渲染成功；主题及既有 GUI 定向测试为 30 passed，完整默认测试为 118 passed, 12 deselected。

## P5：响应式主窗口显示结构

- [x] 删除主窗口固定坐标布局，使用顶层 VBox 与可伸缩双栏工作区。
- [x] 左栏按项目目录、CST 模板、计算配置、执行资源组织输入和操作。
- [x] 右栏作为独立日志面板占用剩余空间，随窗口尺寸变化。
- [x] 设置最小窗口尺寸与左侧合理宽度边界，避免缩放后控件重叠。
- [x] 保持原控件 objectName 与信号入口，业务代码和测试无需改写。
- [x] `.ui` 仍是布局源文件，并通过 PyQt UI 编译器校验。

实现记录：默认窗口从 987×713 调整为 1120×720，最小尺寸为 900×600。设置面板宽度限定为 440–560 px，日志面板获得横向和纵向剩余空间；标题、副标题和分区标题形成清晰信息层级。响应式布局及既有 GUI 定向测试为 31 passed，完整默认测试为 119 passed, 12 deselected。

## P6：GUI 功能语义收口与源文件命名

- [x] 算法设置只有校验成功才关闭；取消恢复最后一次已提交值。
- [x] 后处理设置使用工作副本，保存才提交，取消完整回滚。
- [x] 双击后处理条目可编辑，编辑使用 dataChanged 通知而非删除重建。
- [x] 新增、整体替换和 JSON 解码均拒绝重复结果名。
- [x] 设置窗口归属于主窗口；运行期间主窗口和已打开设置窗口一并冻结。
- [x] “继续运行”和“安全模式”可由用户选择并传给后端。
- [x] 算法、后处理和新增结果窗口使用响应式 Qt Layout。
- [x] 删除空白示例入口，仅保留 `gui_app.py`；同步更新打包和启动脚本。
- [x] 手写模块重命名为 `main_window.py`、`algorithm_settings_dialog.py` 和 `postprocess_settings_dialog.py`。

实现记录：GUI 现在具有明确的“编辑工作副本 → 保存提交 / 取消回滚”语义。主窗口是所有设置窗口的 Qt owner，关闭主窗口不会遗留独立顶层窗口。启动命令统一为 `python gui_app.py`，PyInstaller 使用 `gui_app.spec`。GUI 功能 Gate 为 36 passed，完整默认测试为 124 passed, 12 deselected。

## P6.5：真实启动与打包 Gate

- [x] 真实 `cst_tools_main` 后端可创建并标准关闭主窗口，不启动 CST。
- [x] `gui_app.py --smoke-test` 提供自动创建、处理事件和标准退出路径。
- [x] PyInstaller spec 使用项目相对路径，不再引用旧用户桌面目录。
- [x] 打包收集 `data/` 与默认配置模板，并关闭发布版控制台窗口。
- [x] 排除 pytest、Sphinx、Jupyter、Dask 等未使用的开发/可选集成模块。
- [x] 实际构建 `dist/gui_app.exe`，并从仓库外独立临时目录启动。
- [x] 打包进程以退出码 0 结束，无需用户通过 UI 关闭。

验证记录：源码与入口定向 Gate 为 39 passed；完整默认测试为 127 passed, 12 deselected。单文件产物大小为 331,751,465 bytes，SHA-256 为 `74148BEB43962CF645E8A57B4DB635D4D06F64977218E96AB10C367FCF8B40B8`。当前体积较大源于 legacy 算法生产路径直接依赖 NumPy、pandas、Matplotlib 和 SciPy；体积优化不阻塞 P6.5 功能 Gate。

## P7：Application Service 边界

- [x] GUI 定义稳定的 `GuiApplicationService` Protocol。
- [x] 启动参数收敛为不可变 `RunRequest`，在边界验证 Worker 数量。
- [x] 主窗口只使用面向 GUI 的 snake_case 操作，不导入 `base.py`。
- [x] 运行控制器只负责状态机和线程，不再解释 legacy 返回值。
- [x] Application Service 独占旧方法翻译和失败归一化。
- [x] 保持现有生产 Engine、Manager、Worker 和 Python/VBA 协议不变。
- [x] Application Service 使用独立单元测试覆盖配置、运行、停止和失败路径。

实现记录：主窗口负责呈现和收集输入，控制器负责 RunState/QThread，Application Service 负责应用用例。P7 建立边界时保留旧后端适配器；该临时生产依赖已在 P8 移除。

## P8：旧应用后端迁移

- [x] 将生产编排实现从根目录 `base.py` 迁入 `csttool/application_backend.py`。
- [x] 新后端公开稳定 snake_case 应用 API，GUI 不再导入旧入口。
- [x] GUI 默认创建 `CstApplicationBackend`，旧式 Engine 仅通过私有兼容适配器注入。
- [x] `base.cst_tools_main` 降为旧批处理脚本兼容壳，不再承载生产实现。
- [x] 保持 Manager、Worker、算法和 Python/VBA 协议行为不变，避免一次迁移跨越两个高风险边界。
- [x] 增加默认装配测试，并通过 Fake Worker 流程和完整回归。

实现记录：新代码的依赖方向为 `GUI -> GuiApplicationService -> CstApplicationBackend -> Manager/Algorithm`。兼容适配器只服务尚未迁移的注入式旧 Engine 和测试替身；生产默认路径不再经过 `base.py`。定向测试为 `23 passed`，完整默认测试为 `131 passed, 12 deselected`。本阶段不把仅支持有界双任务 Gate 的 `protocol_warm_worker` 宣称为通用生产后端；其接入需单独的真实 CST Gate。

## P9：新后端内部收口

- [x] 新后端内部只保留 snake_case API，删除 camelCase 转调链。
- [x] 将命令行解析和旧返回值语义移入 `base.cst_tools_main` 兼容壳。
- [x] 建立 CREATED、INITIALIZED、PREPARED、RUNNING、STOPPING、STOPPED、FAILED 生命周期。
- [x] 拒绝重复初始化、未准备执行和运行期修改配置等非法顺序。
- [x] 初始化失败后允许显式重试，成功运行后允许下一次运行。
- [x] 算法异常通过 `finally` 标准停止并释放 Manager。
- [x] GUI 停止线程和执行清理共享一次性停止栅栏，避免重复关闭。
- [x] 增加后端生命周期、异常清理和重试契约测试。
- [x] 保持 Manager、Worker、算法和 Python/VBA 协议不变。

实现记录：`CstApplicationBackend` 不再包含 argparse、进程退出或旧方法名；`base.py` 是唯一旧 API/CLI 兼容入口。P9 与 GUI 兼容定向测试为 `29 passed`，完整默认测试为 `137 passed, 12 deselected`。API、状态和兼容范围见 `application-backend.md`。

## 明确不做

- [x] P0–P3 不提前混入视觉主题；P4 在生命周期和配置边界稳定后独立实施。
- [ ] 不直接编辑生成的 `ui_*.py` 作为长期布局来源；布局变化应修改 `.ui` 后重新生成。
- [ ] 不在 GUI 中复制 Manager 调度、Profile 校验或结果读取逻辑。
- [ ] 不让 GUI 线程等待 Solver、文件协议或 Worker 退出。
