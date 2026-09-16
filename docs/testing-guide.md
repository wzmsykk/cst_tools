# CST Tools 测试基础

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

该 Gate 通过后，下一步才是把相同 Codec 接入一份独立 Worker v1 Pattern，然后用 default CST 工程验证 Rebuild/Solve/`.rd0`。
