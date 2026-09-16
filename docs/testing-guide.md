# CST Tools 测试基础

当前阶段和已通过 Gate 汇总见[当前状态与实施路线](./current-status.md)。

## 测试层级

### 1. 默认测试

不启动 CST，适合每次修改后运行：

```powershell
python -m pytest -q
```

覆盖 Python 单元测试、Manager 并发、最小文件协议、fake Worker、golden vectors、VBA 静态契约和 Contract Macro 构建。

### 2. 定向协议测试

```powershell
python -m pytest -q `
  test/runtime_protocol_test.py `
  test/runtime_protocol_vba_test.py `
  test/protocol_contract_test.py
```

这组测试无需安装 CST，应作为修改 Python/VBA 协议时的最低检查。

### 3. 真实 CST/WWB Contract Test

该测试会启动本机 CST，默认永不运行。必须同时覆盖 pytest marker、显式授权开关和可执行文件路径：

```powershell
python -m pytest -q -m integration --run-cst `
  --cst-exe "D:\Program Files (x86)\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe" `
  test/protocol_contract_integration_test.py
```

也可以设置 `CST_TEST_EXE`，但仍必须传 `--run-cst`。

真实测试只验证 WWB 协议 Codec：读取 Task、写 Completion、等待 Ack。它不打开工程、不运行 Solver，是接入生产 `worker.vb` 前的方言兼容 Gate。

测试通过版本化 OLE ProgID（例如 `CSTStudio.Application.2022`）创建 CST，并持有 `studio.NewMWS` 返回的项目对象。Contract Macro 写出 `contract.result` 并返回后，外部控制器依次调用文档规定的 `Project.Quit` 和 `Application.Quit`，分别关闭项目和退出应用。只有控制器正常返回且本次测试新增的 CST 进程全部退出，测试才会通过。

Contract Macro 由外部 OLE 控制器持有项目对象，因此宏内不得调用 `Quit`；宏返回后由控制器调用 `Project.Quit` / `Application.Quit`。应用级 `-m` Worker 则在 Ack 或明确的 fail-fast 终止路径中请求 `Save/Quit`，并由测试继续验证批处理进程最终正常退出。CST 可能在 batch 尚未返回时记录“Unable to close sheet”诊断，但只要批处理随后以退出码 0 结束且无新增进程/UI 残留，生命周期 Gate 仍成立。任何超时、保存对话框或残留进程都会使 Gate 失败；强制清理只用于恢复环境，不算标准退出。

因此真实 Gate 除协议兼容性外，还证明：测试打开或新建的项目得到妥善处理，结束后不留下必须由用户通过 UI 保存或关闭的问题；在标准退出被实际证明失败之前，不以结束进程代替正常生命周期。

## Golden vectors

冻结文件位于 `test/data/runtime_protocol_v1/`。Python 编码器必须逐字节匹配：

- `task.txt`；
- `completion-success.txt`；
- `completion-failure.txt`；
- `ack.txt`。

修改这些文件等同修改协议。必须说明兼容性影响；不兼容变化应创建 v2，禁止静默更新 v1 fixture 使测试重新通过。

## Contract Macro

`csttool.protocol_contract.prepare_contract_workspace()` 为每次测试建立隔离目录：

```text
workspace/
  runtime_protocol_contract.bas
  contract.result
  protocol/
    inbox/
    completed/
    ack/
```

生成的 BAS 由以下模块组成：

- `data/runtime_protocol_v1.vb`：无入口的 Codec；
- `data/runtime_protocol_contract_main.vb`：唯一测试入口。

## 接入生产 Worker 前的 Gate

必须全部满足：

- 默认测试通过；
- Python 与 golden vectors 逐字节一致；
- 生成宏只有一个 `Sub Main`；
- 真实 CST/WWB Contract Test 通过；
- `.tmp` 不会被读取；
- 错误 session 被拒绝；
- Ack 前 Worker 不推进。

该 Gate 已通过，且相同 Codec 已接入独立的一次性 Worker v1。P3 使用 Pillbox 临时副本验证 literal/expression 参数、Rebuild、Eigenmode Solve、Backup Flush、Python 读取 `Result/Frequency (Multiple Modes)/Mode 1.rd0`、Ack 和官方 Save/Quit：

```powershell
python -m pytest -q -m integration --run-cst `
  --cst-exe "D:\Program Files (x86)\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe" `
  test/protocol_worker_integration_test.py
```

联合回归可同时运行 `test/protocol_contract_integration_test.py` 和 `test/protocol_worker_integration_test.py`。P3 通过前后都不替换 legacy `data/worker.vb`。

P4 双任务 Warm Gate：

```powershell
python -m pytest -q -m integration --run-cst `
  --cst-exe "D:\Program Files (x86)\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe" `
  test/protocol_warm_worker_integration_test.py
```

该 Gate 验证 task 级独立结果目录、Completion/Ack 串行栅栏、两次不同 `.rd0` 以及 Stop Request/Ack 后的标准退出。它记录时间，但单次双点测试不用于宣称 Warm 性能收益。

P4.5 固定 HOM 结构 Cold/Warm 扫频基准：

```powershell
python -m pytest -q -m integration --run-cst `
  --cst-exe "D:\Program Files (x86)\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe" `
  test/protocol_hom_scan_benchmark_integration_test.py
```

该 Gate 运行两个独立 Cold 频段，再在一个 Warm 进程中运行相同两个频段；逐频段比较 Frequency、Q-Factor、轴上 R/Q、5 mm 偏轴 R/Q、10 mm 偏轴 R/Q 共 5 个原生 `.rd0`，并在 `.pytest_cache/cst-p4-5/<run>/benchmark.json` 保存计时报告。P5 扩展后的当前实测整体墙钟加速约 `1.445x`，但双点结果不替代多频段重复统计。

P5.5 固定模板/动态运行时后处理边界 Gate：

```powershell
python -m pytest -q -m integration --run-cst `
  --cst-exe "D:\Program Files (x86)\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe" `
  test/protocol_hom_runtime_postprocess_integration_test.py
```

该 Gate 只运行一次 Solver，随后以当前场结果调用 `EigenResult_Complex` 分别计算 x、y、z 积分轴；覆盖 x 轴 y=5 mm、y 轴 x=5 mm、z 轴 y=5 mm 和 z 轴 y=7.5 mm。z 轴 5 mm 与预安装原生 Result Template 对照；后处理阶段不得调用 `StoreParameter`、`Update Params`、Rebuild 或第二次 Solver。结果报告写入 `.pytest_cache/cst-p5-5/<run>/report.json`。

P5.6 已注册 Result Template 当前运行评估 Gate：

```powershell
python -m pytest -q -m integration --run-cst `
  --cst-exe "D:\Program Files (x86)\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe" `
  test/protocol_hom_template_evaluation_integration_test.py
```

该 Gate 通过 CST 官方模板迭代器记录求解前和显式评估后的注册 inventory，并在唯一一次 Solver 完成后调用 `EvaluateResultTemplates`。显式评估前后的 Frequency `.rd0` 必须一致，期间不得修改工程参数、Rebuild 或再次启动 Solver。报告写入 `.pytest_cache/cst-p5-6/<run>/report.json`。CST 2022 没有公开模板注册/删除 VBA API，因此模板安装保留为 Project Profile 的一次性制备步骤，不进入运行期 Python/VBA 协议。

P6 复用同一集成测试文件，并增加缺失能力的 fail-fast Gate。正向 Gate 验证 `hom-2022-v1` 的五个模板；负向 Gate 临时要求一个不存在的模板，必须返回 `PROFILE_CAPABILITY_MISSING`，且不产生 timing/result 文件、不启动 Solver、不留下 CST/UI 进程。
