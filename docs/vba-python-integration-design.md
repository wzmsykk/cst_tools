# CST VBA 与 Python 联合架构设计

状态：历史完整架构提案；当前只实施其最小子集
版本：0.1  
日期：2026-09-17

当前 P2.5–P6 没有采用通用 Operation ABI、Manifest 或 Profile Schema；实际边界见[当前状态与实施路线](./current-status.md)。本文继续作为长期设计素材，不是当前完成度说明。

> 优先级说明：在实施完整 Operation ABI 前，必须先完成原生结果可读性验证。若主要指标均可由 CST 工程内部结果直接读取，本设计中的后处理 Operation 范围应收缩为少量必要的 VBA Extension。`.cst` 静态信息、能力清单和 Project Profile 指纹统一由 `cst_project` 层提供，不允许 Worker、Provider 和生成器各自解析容器。参见 [Warm CST 与原生结果知识库](./cst-warm-native-results-knowledge-base.md)、[CST `.cst` 项目文件知识库](./cst-project-file-knowledge-base.md) 和 [原生结果优先 TODO](./cst-native-results-todo.md)。

## 1. 背景

项目当前通过 Python 生成 CST VBA/BAS，启动 CST，使用文件传递任务，再由 Python 读取后处理结果。现有方式已经能够运行，但 Python 生成器直接知道 VB 文件名、函数名、参数顺序、输出文件名和解析函数，导致两侧高度耦合：修改 VB 往往必须同步修改 Python，反之亦然。

本设计把以下内容视为一个完整子系统：

- Python Pipeline 与代码生成器；
- CST Worker Runtime；
- VB Operation 模块；
- 任务与结果文件协议；
- 结果 Codec；
- Profile 与项目配置；
- 版本和兼容策略；
- 静态检查及真实 CST 集成测试。

目标是先稳定双方契约，再分别演进内部实现。

## 2. 设计目标

- VB 仅承担 CST API 必须在 CST 内完成的操作。
- Python 负责调度、校验、依赖解析、代码生成和结果建模。
- 新增物理量时不修改通用生成器。
- 修改 VB 内部公式但不改变输入输出时，不修改 Python。
- 所有操作具有明确版本、参数 Schema、输出 Codec 和错误语义。
- 生成产物可追踪到确切的配置和源文件哈希。
- 无 CST 环境时可以验证绝大部分生成和解析逻辑。
- 旧 `pps.json` 在迁移期间继续可用。

## 3. 非目标

第一阶段不处理：

- 跨主机或分布式任务调度；
- 使用 JSON 作为 VB 必须解析的运行时格式；
- 在 VBA 中实现复杂对象系统；
- 一次性重写全部历史 VB；
- 修改已经验证过的物理公式；
- 立即删除旧 PPS 和 Pattern。

## 4. 总体架构

### 参数发现不进入 VBA Operation

参数发现是静态项目读取，不再建模为运行时 VBA Operation。统一由 `cst_project` 层读取 `.cst` 中当前 scope 的 `Model/Parameters.json`，返回名称、表达式、求值结果和描述。

VB/COM 前处理仅保留给会改变 CST 工程状态的准备操作，例如：

- 创建 `fmin/fmax/nmodes` 等标准参数；
- 将 Solver 设置绑定到参数；
- 写入 HISTORY LIST；
- 安装 Result Template；
- Rebuild 并保存 prepared project。

若输入工程已经满足 Profile，Preparation 阶段也应跳过。若仍需运行 Preparation Macro，宏结束后由 Python 直接读取保存后的 `.cst` 参数，不再串联 `GetParamList.vb`。

```text
优化算法 / 用户配置
        │
        ▼
PipelineSpec
        │
        ▼
Python Pipeline Compiler
  ├─ Schema Validation
  ├─ Operation Resolution
  ├─ Capability Validation
  ├─ Dependency Resolution
  ├─ Symbol/ABI Validation
  ├─ VBA Emission
  └─ Build Manifest
        │
        ├──────────────► build-manifest.json
        ▼
      main.bas
        │
        ▼
CST Worker Runtime
  ├─ Prepare Phase
  ├─ Solve Phase
  └─ Postprocess Phase
        │
        ▼
Versioned Result Files
        │
        ▼
Python Result Codecs
        │
        ▼
SimulationResult
```

## 5. 目录结构

每个 Operation 的实现、接口描述和测试放在一起：

```text
cst_operations/
  schemas/
    operation-manifest-v1.schema.json
    pipeline-v1.schema.json

  runtime/
    worker-runtime.vb
    task-protocol.vb
    result-writer.vb
    error-handling.vb

  eigen_scalar/
    operation.json
    eigen-scalar.vb
    test_cases/

  eigen_complex_axis/
    operation.json
    eigen-complex-axis.vb
    test_cases/

  mode_recognition/
    operation.json
    mode-recognition.vb
    test_cases/

  direct_0d/
    operation.json
    reader.py
    test_cases/

  legacy/
    modes_v2.bas
    modes_v3.bas
    ...
```

操作包是最小变更单元。修改某个操作时，它的 VB、Manifest、测试和样本应在同一个变更中完成。

## 6. Operation Manifest

Operation Manifest 是 Python 与 VB 之间的唯一事实来源。

示例：

```json
{
  "schema_version": 1,
  "operation_id": "eigen.scalar",
  "operation_version": 1,
  "generator_abi": 1,
  "execution": "vba",
  "sources": ["eigen-scalar.vb"],
  "entrypoint": "CSTPP_EigenScalar_Run",
  "arguments": {
    "mode": {
      "type": "integer",
      "minimum": 1
    },
    "quantity": {
      "type": "enum",
      "values": [
        "Frequency",
        "Q-Factor",
        "Total Loss",
        "Total Energy"
      ]
    }
  },
  "output": {
    "codec": "scalar-v1",
    "unit_required": true
  },
  "capabilities": ["eigenmode-results"]
}
```

Manifest v1 至少定义：

- Schema 版本；
- 稳定 Operation ID；
- Operation 契约版本；
- 所需 Generator ABI；
- 执行方式：`vba` 或 `python-reader`；
- VB 源文件和依赖；
- 统一入口名称；
- 参数名称、类型、范围和默认值；
- 输出 Codec；
- 所需 CST 能力；
- 可选的兼容别名。

## 7. Pipeline 配置

Pipeline 固定分为三个阶段：

```python
PipelineSpec(
    prepare=[...],
    solve=...,
    postprocess=[...],
)
```

配置示例：

```json
{
  "pipeline_version": 1,
  "profile": "pillbox@1",
  "prepare": [],
  "solve": {
    "operation": "solver.eigenmode",
    "version": 1,
    "args": {}
  },
  "postprocess": [
    {
      "operation": "eigen.scalar",
      "version": 1,
      "result_name": "frequency",
      "args": {
        "mode": 1,
        "quantity": "Frequency"
      }
    }
  ]
}
```

配置不得包含 VB 文件名、VB 函数名、生成文件名或 Python reader 名称。

## 8. Generator ABI v1

所有 VB Operation 使用固定入口语义：

```vb
Public Function CSTPP_Operation_Run( _
    ByVal ..., _
    ByVal outputPath As String, _
    ByRef errorCode As String, _
    ByRef errorMessage As String) As Boolean
```

约束：

- 返回值只表示操作成功或失败；
- 错误通过 `errorCode` 和 `errorMessage` 返回；
- 操作不得写任务级 `.success` 或 `.failure`；
- 操作不得调用 `Quit` 或终止 Worker；
- 操作只写 Manifest 声明的结果；
- 库文件不得定义 `Sub Main`；
- 公共符号使用 `CSTPP_` 前缀；
- 所有生产脚本必须使用 `Option Explicit`；
- 所有参数显式声明 `ByVal` 或 `ByRef`；
- 除 CST API 必须使用的情况外，避免 `Variant`。

任务是否整体成功由 Worker Runtime 决定。

## 9. Task Protocol v1

运行时协议使用 VBA 易于可靠读取的逐行格式，不要求 VB 解析 JSON。

建议任务文件：

```text
CST_TASK_V1
task_id=42
job_name=GEN_0_1
parameter_count=2
radius
100.0
length
250.0
```

文件提交过程：

1. Python 写入 `42.task.tmp`；
2. 完成并关闭文件；
3. 原子重命名为 `42.task`；
4. VB 只读取 `.task`。

结果同样先写临时文件，再原子重命名。任务标志只在结果文件完整后生成。

## 10. Result Codec v1

第一阶段冻结四类结果格式。

### `scalar-v1`

```text
CST_RESULT_SCALAR_V1
status=success
quantity=Frequency
value=500.25
unit=MHz
```

### `mode-map-v1`

```text
CST_RESULT_MODE_MAP_V1
status=success
quantity=Frequency
unit=MHz
count=2
1=500.25
2=700.50
```

### `table-v1`

```text
CST_RESULT_TABLE_V1
columns=x,y,z,ex_re,ey_re,ez_re
rows=1
0,0,0,1,2,3
```

### `fileset-v1`

```text
CST_RESULT_FILESET_V1
status=success
count=2
e_field=e-field.txt
h_field=h-field.txt
```

Python 只维护少量通用 Codec，不为每个物理量创建独立 reader。

## 11. 错误模型

第一版标准错误代码：

```text
INVALID_ARGUMENT
PARAMETER_NOT_FOUND
PARAMETER_REBUILD_FAILED
SOLVER_FAILED
SOLVER_TIMEOUT
MODE_NOT_FOUND
RESULT_TREE_NOT_FOUND
POSTPROCESS_FAILED
OUTPUT_WRITE_FAILED
CST_PROCESS_EXITED
PROTOCOL_ERROR
INTERNAL_VBA_ERROR
```

失败结果必须包含：

- Operation ID；
- 所在阶段；
-错误代码；
-错误消息；
-任务 ID；
-是否建议重试；
-是否建议重启 Worker。

Python 根据错误类别决定重试策略，而不是对所有 Failure 无条件重启。

## 12. Profile

Profile 描述模型差异，不再复制整个 Pattern：

```json
{
  "profile_id": "pillbox",
  "profile_version": 1,
  "solver": "solver.eigenmode@1",
  "capabilities": ["eigenmode-results"],
  "sources": ["pillbox-hooks.vb"],
  "hooks": {
    "prepare": "CSTPROFILE_Pillbox_Prepare",
    "after_solve": "CSTPROFILE_Pillbox_AfterSolve"
  }
}
```

Profile Hook 签名由 ABI 固定，不允许任意插入自由代码。

## 13. Pipeline Compiler

Python 生成器重构为编译管线：

```text
Load
  → Schema Validation
  → Operation Resolution
  → Capability Validation
  → Dependency Resolution
  → Symbol Collision Check
  → VBA Emission
  → Static Validation
  → Build Manifest
```

输出：

- `main.bas`；
- `build-manifest.json`。

Build Manifest 记录：

```json
{
  "generator_abi": 1,
  "task_protocol": 1,
  "pipeline_version": 1,
  "profile": "pillbox@1",
  "operations": ["solver.eigenmode@1", "eigen.scalar@1"],
  "sources": {
    "worker-runtime.vb": "sha256:...",
    "eigen-scalar.vb": "sha256:..."
  }
}
```

## 14. 静态检查

启动 CST 前至少检查：

- 不存在未替换的 `%PLACEHOLDER%`；
- 最终产物只有一个 `Sub Main`；
- Operation entrypoint 均存在；
- 没有重复公共符号；
- 没有空的生产 VB 文件；
- `Sub/Function` 与结束语句基本配对；
- 生产代码不使用禁止的 `On Error Resume Next`；
- Manifest 参数全部可生成；
- Codec 已注册；
- 依赖文件哈希已记录。

## 15. 版本策略

三个版本独立管理：

| 版本 | 升级条件 |
|---|---|
| Task Protocol | Python 与 Worker 文件结构不兼容变化 |
| Generator ABI | VB 公共入口或错误返回方式变化 |
| Operation Version | 某项操作的参数或输出语义不兼容变化 |

仅优化 VB 内部算法且输入输出不变时，不升级 Operation Version，也不修改 Python。

## 16. 兼容迁移

迁移期间增加：

```python
legacy_pps_to_pipeline(old_pps) -> PipelineSpec
```

迁移顺序：

1. 冻结 v1 契约；
2. 建立 `eigen.scalar@1` 纵向样板；
3. 兼容旧 PPS；
4. 迁移 TM020；
5. 迁移 WTC；
6. 迁移 Pillbox、Enlarged、HOM；
7. 迁移场导出和模式识别；
8. 完成真实 CST 回归后删除重复旧代码。

## 17. 测试策略

测试分层：

1. Manifest Schema 测试；
2. 依赖解析和参数校验测试；
3. 生成调用区 Golden Test；
4. Result Codec 单元测试；
5. VB 静态检查；
6. 每个 Operation 的最小 CST Contract Test；
7. Profile 集成测试；
8. 完整 Python → CST → Python 端到端测试。

不建议对整个 `main.bas` 做脆弱的全文快照，应比较模块清单、入口、调用区、Build Manifest 和标准化哈希。

## 18. 决策冻结点

实现前必须评审并冻结：

1. Operation Manifest v1；
2. Generator ABI v1；
3. Task Protocol v1；
4. 四种 Result Codec v1；
5. 错误代码和重试分类；
6. Pipeline 三阶段模型。

冻结后，任何不兼容修改都必须通过版本升级，而不是静默同步修改 Python 和 VB。
