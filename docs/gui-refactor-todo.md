# GUI 重构 TODO

状态：P0–P2 已完成；当前实施记录

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

## P3：配置对话框与数据模型

- [ ] 算法设置使用有类型配置对象和 Qt Validator。
- [ ] 后处理设置使用稳定枚举/key，修复显示名称与协议名称混用。
- [ ] 列表模型使用 `beginInsertRows/endInsertRows` 和对应删除通知。
- [ ] JSON 文件增加版本、结构校验和明确错误反馈。
- [ ] 保留现有配置的兼容读取路径。

## 明确不做

- [ ] P0–P1 不重新设计视觉主题。
- [ ] 不直接编辑生成的 `ui_*.py` 作为长期布局来源；布局变化应修改 `.ui` 后重新生成。
- [ ] 不在 GUI 中复制 Manager 调度、Profile 校验或结果读取逻辑。
- [ ] 不让 GUI 线程等待 Solver、文件协议或 Worker 退出。
