# CST `.r0d/.r1d` Result Template 文件结构

状态：基于当前 CST 2020 样本的已验证结构  
日期：2026-09-16

## 1. 核心结论

用户关于 `.r0d/.r1d` 的理解是正确的：扩展名中的 `0d/1d` 表示 Result Template 的输出数据维度。文件不是纯结果数据，而是一个可执行模板包，主要由：

```text
二进制文件头
+ UI/脚本设置键值表
+ VBA 模板源码（UI + Define + Evaluate 算法）
```

组成。

对于同一个 `processed.cst`，以下内嵌成员与 CST 展开工作目录中的同名文件逐字节一致：

- `Frequency (Multiple Modes).r0d`；
- `TotalQ_Eigenmode_All.r1d`；
- `e_Abs (Z).r1d`。

三组样本的长度和 SHA-256 均完全相同。因此 `.cst` 内部没有另一套 `.r0d/.r1d` 格式；容器只是保存同一模板文件的字节内容。

## 2. 已验证的二进制布局

当前样本可按下面的顺序解析：

```text
u32_le format_version          # 当前样本为 3
u32_le unknown_1               # 当前 r0d/r1d 样本均为 0，不是输出维度
lp_string writer_version       # 例如 2020|0|20190925\0
lp_string reader_version       # 同上
u32_le setting_count
repeat setting_count:
    lp_string key
    lp_string value
u32_le vba_length
bytes[vba_length] vba_source
```

其中 `lp_string` 为：

```text
u32_le byte_length
bytes[byte_length] UTF-8/ASCII 字符串，通常包含末尾 NUL
```

三个样本的 VBA 长度字段与剩余字节数精确吻合。当前没有观察到 VBA 之后的额外结果数据段。

文件开头第二个 `u32` 不能命名为 `dimension`：`.r0d` 和 `.r1d` 样本中它都为 0。输出维度应综合以下信息判断：

- 文件扩展名；
- 设置表中的 `TemplateType`；
- VBA 暴露的 `Evaluate0D`、`Evaluate1D`、`EvaluateMultiple0D` 等入口；
- CST Result Template 框架调用契约。

## 3. 0D 样本

`Frequency (Multiple Modes).r0d` 的头部设置包括：

```text
Action=Frequency
AllModesCB=1
M0DResult=1
ModeNumbers=All
TemplateType=M0D
a0DValue=Frequency
```

`M0D` 表示一次模板评估可能产生多个 0D 值/多模式表项，但单个输出仍是标量维度。

VBA 主体包含：

- `Option Explicit` 和 CST 库 include；
- UI 对话框及 `DialogFunction`；
- `Define(...)`；
- `StoreScriptSetting/GetScriptSetting`；
- `Evaluate0D`、`Evaluate1D` 或多结果入口；
- Eigenmode Solver 查询和物理量计算；
- 测试用、被框架忽略的 `Main2`。

所以这个文件既定义 UI，也定义结果名称、依赖选择和真正的计算算法。

## 4. 1D 样本

`TotalQ_Eigenmode_All.r1d` 的设置包括：

```text
HfieldMonitor=Eigenmode
LossQ_selection=4
TemplateType=1D
excit=All
sShape=component:shape
```

其 VBA 使用 `Evaluate1D.AppendXY(mode, value)` 构建以 Mode Number 为横轴的一维结果。

`e_Abs (Z).r1d` 的设置还包含坐标范围、分量、复数处理方式和采样规则。VBA 同时支持 `1D/1DC/M0D/M1D/M1DC` 等路径。这说明扩展名表示该模板实例在结果树中的主要输出类型，而脚本本身可以包含多个评估函数和调试入口。

## 5. 设置表的语义

设置表不是通用 UI 描述语言，而是 VBA 通过 `StoreScriptSetting` 保存的实例状态。其 key 与脚本中 `GetScriptSetting/StoreScriptSetting` 的名称对应，例如：

```vb
StoreScriptSetting("excit", dlg.excit)
StoreScriptSetting("HfieldMonitor", ...)
StoreScriptSetting("LossQ_selection", ...)
```

因此修改设置表在技术上比修改整个 VBA 更简单，但仍必须满足：

- key 是脚本实际认识的设置；
- value 符合脚本期望的字符串编码和枚举范围；
- key/value 数量和每个长度前缀同步更新；
- 模板依赖的结果树路径在目标 scope 中存在；
- 修改后由 CST 打开并重新 Evaluate；
- 不能把设置表中看起来像结果的缓存值当成权威求解结果。

例如 `e_Abs (Z).r1d` 中出现 `MaximumM0D`、`MeanM0D` 等设置值。这可能是模板保存的脚本状态或上次计算产生的辅助值，不能仅凭字段名把它们作为当前任务结果。

## 6. `.r0d/.r1d` 与实际结果数据

需要区分三层：

| 层 | 示例 | 含义 |
|---|---|---|
| 模板定义 | `.r0d/.r1d` | UI 状态 + VBA 算法 +依赖配置 |
| 结果交换/导出 | `Result/<name>.rd0`、ASCII/CSV | 已计算的标量或曲线交换数据 |
| CST 结果数据库/缓存 | `Model.res`、`Model.rdb`、`Storage.sdb` 等 | Solver/结果树内部数据，私有格式 |

`.r0d/.r1d` 告诉 CST“如何计算和显示结果”，不等于已计算结果本身。删除模板文件和删除求解结果也不是同一种操作。

## 7. 对当前架构的影响

这一发现让后处理重构可以采用“编译 Result Template Artifact”的模型：

```text
声明式 ResultTemplateSpec
  → 设置表编码
  → VBA 模板源码
  → .r0d/.r1d artifact
  → CST 注册/导入
  → prepared project
```

它比“每任务生成一段 VB 并通过文件通信执行”稳定，因为模板可以：

- 在 Profile 构建时生成一次；
- 用 SHA-256 固定版本；
- 从 `.cst` 中提取并反编译为设置表 + VBA；
- 对 UI 设置与算法源码分别 diff；
- 在批量 Warm 任务间复用。

但生成一个格式正确的文件不等于已经在 CST 中正确注册。仍需验证：

- 将新 artifact 放入 `Model/3D` 是否足以出现在结果树；
- CST 是否还维护额外索引或 cache；
- 新增、改名、删除时如何同步 `PC_integration.json`；
- 多工程结构下 artifact 属于哪个 `ProjectScope`；
- CST Save 是否会规范化或重写该文件；
- 模板何时重新 Evaluate，旧结果如何失效。

在这些问题验证前，推荐通过 CST Result Template API/Preparation Macro 完成注册，内部编码器先用于读取、diff、校验和实验性生成。

## 8. 推荐对象模型

```text
ResultTemplateArtifact
  format_version
  unknown_header_fields
  writer_version
  reader_version
  settings: ordered map[str, str]
  vba_source
  declared_output_kind
  project_scope
  sha256
```

其中：

- parser 必须保留未知字段和原始字节；
- settings 保持原顺序，避免无意义重写；
- writer 默认只允许从已解析 artifact 派生，不凭空猜未知头字段；
- `declared_output_kind` 从 extension、`TemplateType` 和 VBA 入口交叉验证；
- 若三者矛盾，拒绝写回并要求 CST 验证。

## 9. 推荐验证实验

1. 在 CST UI 中只改一个模板选项，保存前后 `.r0d/.r1d` 并比较设置表和 VBA。
2. 只改模板名称，观察成员名、内部设置和 `PC_integration.json`。
3. 修改模板 VBA 算法但不改 UI，观察 CST 是否接受并重新计算。
4. 复制现有 artifact 为新名称，观察是否自动注册。
5. 通过 CST API 创建相同模板，与 Python 编码结果逐字段比较。
6. 在 root 与 `SP/<name>` scope 中分别创建同名模板，验证作用域。
7. 在 CST 2020/2022 重复，比较 `format_version`、header 和 VBA 版本。
8. 修改参数但不重新 Evaluate，确认设置表中的缓存字段是否陈旧。

## 10. 当前安全边界

- 可以安全读取并拆分 header、settings 和 VBA。
- 可以对内外 artifact 做 SHA-256 和语义 diff。
- 可以把 `.r0d/.r1d` 纳入 Profile 能力清单和版本控制。
- 暂不把 header 中未知字段赋予未经验证的语义。
- 暂不把设置表中的缓存字段作为生产结果。
- 暂不绕过 CST 直接向权威工程注册新模板。
- 写回实验必须在副本中进行，并通过 CST 打开、Evaluate、Save、Reopen 验证。

