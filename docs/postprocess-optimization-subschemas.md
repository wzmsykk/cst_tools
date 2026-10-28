# 后处理算子与优化策略子契约冻结

日期：2026-10-28。静态冻结稿；不代表实现或真实验收。上层见[统一契约](unified-interface-contract.md)，运行迁移见[删除清单](unified-interface-migration.md)。本文冻结输入及明确不支持项，不添加Python模型、运行Schema文件或生成器代码。

## 1. 源码依据与统一表示

核查[CstPostProcessor.configure/_append_configured_step/render_vb](../csttool/postprocess_cst.py)、[METRICS](../csttool/postprocess_metrics.py)、[读出器](../csttool/postprocess_readers.py)、[SamplingSpec](../csttool/field_artifacts.py)、[Simple宏](../data/postprocess/EigenResult_Simple.vb)、[Complex宏](../data/postprocess/EigenResult_Complex_All.vb)、[ModeRec宏](../data/postprocess/ModeRec_All.vb)，以及两种优化器从构造到convertResult/start的消费链。固定本轮源码SHA256保存在`artifacts/mcp-sdk-host-static-20261028/local-source-hashes.json`，原始快照不保证随Git迁移。

现有生成器支持11个简单指标、2个积分指标，各自单模和_All，再加ModeRec_All、Direct_PPS_0D、ExportModeField，共29个方法名。新公共契约保留13个指标ID及3个特殊操作ID，用显式mode选择替代_All后缀；不保留旧别名。旧PPS→内部生成调用转换只在一个执行适配点发生。

公共条目字段为metric_id、method_id、settings，全部必填；metric_id为稳定ASCII ID，不用于拼文件名，展示标题另由目录/元数据取得。数组最多128项，metric_id唯一。所有对象拒绝未知字段；字符串数值、布尔冒充整数、非有限数拒绝。

## 2. 指标目录与实际行为

|method_id|settings族|输出/单位约束|能力前提|
|---|---|---|---|
|Frequency|simple|单值或逐模值；新响应MHz|宏返回工程频率单位，适配器必须读单位并转换，不能一律当MHz|
|Q_Factor、Q_Enclosure、Q_Volume、Q_Surface|simple|无量纲Q|除Frequency外当前Simple先选E树项并调用QFactor.Calculate；不能按名称推断只需一个原生标量|
|Q_Ext|simple|无量纲或unavailable|需端口及求解前已启用外部Q；现宏缺端口/低于截止返回-1，不能作为有效Q；未配置不是整个求解失败|
|Total_Loss、Loss_Enclosure、Loss_Volume、Loss_Surface|simple|损耗；归一化条件/单位来源必须登记，未知为unknown|实际来自QFactor GetTotalLossRMS/GetLossRMS，不能按项目UI单位猜数值尺度|
|Total_Energy|simple|储能；单位/归一化来源登记|来自QFactor.GetTotalEnergy，不因名称就跳过E/H前提|
|R_over_Q、Shunt_Impedance|line|积分结果，公式对应Ω；记录beta=1、axis、横向偏移和积分算法身份|有场/网格及有效频率；Complex实际调用全范围积分，非可变路径通用积分器|
|Direct_PPS_0D|native|只读工程现有Result/*.rd0首行数值；单位由登记定义提供|无VBA调用，不创建模板；新输入native_result_ref而非自由路径或显示名|
|ModeRec_All|recognition|逐模式分类记录，非float标量；无量纲分类不等于物理匹配身份|现宏/下游utils基于专门轴对称腔约定；不能声明任意几何/任意束流轴支持|
|ExportModeField|field|HDF5工件摘要；坐标m，E为V/m、H为A/m；不用JSON返回原始全场|h5py可选依赖、CST结果/点数/坐标/哈希校验；ROI有效不代表材料掩码/全域有效|

simple.mode和line.mode为`{selection:one,index:1..32767}`或`{selection:all}`。all遍历EigenmodeSolver.GetNumberOfModesCalculated，不保证请求数，顺序是当前CST模式序号。运行时index越界返回该结果unavailable/failed，不读旧模式。按HOM正常窄窗默认为one/index=1，不能把all偷偷转成多模求解。

line.integration_line固定axis=x/y/z、offset_mm三元素数值数组、beta=1、range=full。沿axis的偏移必须为0，拒绝非零而非悄悄忽略；现宏确实将该分量归零。横向mm必须转换为工程几何单位再进入宏：目前生成器直接传数值，不能证明非mm工程正确。新能力在转换验收前要求预检工程单位为mm；转换后仍记录原单位和比例。

采样为轴对齐长方体、均匀cell-center规则；bounds_m顺序xmin/xmax/ymin/ymax/zmin/zmax，每对严格递增；counts三个正整数且乘积≤2,000,000。scope只允许roi-probe或specified-domain。specified-domain仅是请求域标签，不自动证明整个真空腔，必须另核对已登记掩码/体积权重及工程前提。非矩形CAD/多材料不在本版承诺范围。

## 3. 冻结Schema（文档内设计工件）

下方JSON只用于静态校验与以后生成公共模型，当前运行生成器不消费。跨字段约束和资源乘积见第4节，不能仅凭JSON Schema通过宣称业务有效。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:csttools:design:postprocess-optimization:1",
  "$ref": "#/$defs/PostprocessPlan",
  "$defs": {
    "Mode": {
      "oneOf": [
        {
          "type": "object",
          "properties": {
            "selection": {
              "const": "one"
            },
            "index": {
              "type": "integer",
              "minimum": 1,
              "maximum": 32767
            }
          },
          "required": [
            "selection",
            "index"
          ],
          "additionalProperties": false
        },
        {
          "type": "object",
          "properties": {
            "selection": {
              "const": "all"
            }
          },
          "required": [
            "selection"
          ],
          "additionalProperties": false
        }
      ]
    },
    "Line": {
      "type": "object",
      "properties": {
        "axis": {
          "enum": [
            "x",
            "y",
            "z"
          ]
        },
        "offset_mm": {
          "type": "array",
          "items": {
            "type": "number"
          },
          "minItems": 3,
          "maxItems": 3
        },
        "beta": {
          "const": 1
        },
        "range": {
          "const": "full"
        }
      },
      "required": [
        "axis",
        "offset_mm",
        "beta",
        "range"
      ],
      "additionalProperties": false
    },
    "Sampling": {
      "type": "object",
      "properties": {
        "bounds_m": {
          "type": "array",
          "items": {
            "type": "number"
          },
          "minItems": 6,
          "maxItems": 6
        },
        "counts": {
          "type": "array",
          "items": {
            "type": "integer",
            "minimum": 1,
            "maximum": 2000000
          },
          "minItems": 3,
          "maxItems": 3
        },
        "scope": {
          "enum": [
            "roi-probe",
            "specified-domain"
          ]
        }
      },
      "required": [
        "bounds_m",
        "counts",
        "scope"
      ],
      "additionalProperties": false
    },
    "Simple": {
      "type": "object",
      "properties": {
        "metric_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "method_id": {
          "enum": [
            "Q_Factor",
            "Frequency",
            "Total_Loss",
            "Loss_Enclosure",
            "Loss_Volume",
            "Loss_Surface",
            "Q_Enclosure",
            "Q_Volume",
            "Q_Surface",
            "Total_Energy"
          ]
        },
        "settings": {
          "type": "object",
          "properties": {
            "mode": {
              "$ref": "#/$defs/Mode"
            }
          },
          "required": [
            "mode"
          ],
          "additionalProperties": false
        },
        "on_unavailable": {
          "enum": [
            "fail",
            "record"
          ],
          "default": "fail"
        }
      },
      "required": [
        "metric_id",
        "method_id",
        "settings"
      ],
      "additionalProperties": false
    },
    "ExternalQ": {
      "type": "object",
      "properties": {
        "metric_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "method_id": {
          "const": "Q_Ext"
        },
        "settings": {
          "type": "object",
          "properties": {
            "mode": {
              "$ref": "#/$defs/Mode"
            }
          },
          "required": [
            "mode"
          ],
          "additionalProperties": false
        },
        "on_unavailable": {
          "const": "record",
          "default": "record"
        }
      },
      "required": [
        "metric_id",
        "method_id",
        "settings"
      ],
      "additionalProperties": false
    },
    "Integral": {
      "type": "object",
      "properties": {
        "metric_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "method_id": {
          "enum": [
            "R_over_Q",
            "Shunt_Impedance"
          ]
        },
        "settings": {
          "type": "object",
          "properties": {
            "mode": {
              "$ref": "#/$defs/Mode"
            },
            "integration_line": {
              "$ref": "#/$defs/Line"
            }
          },
          "required": [
            "mode",
            "integration_line"
          ],
          "additionalProperties": false
        },
        "on_unavailable": {
          "enum": [
            "fail",
            "record"
          ],
          "default": "fail"
        }
      },
      "required": [
        "metric_id",
        "method_id",
        "settings"
      ],
      "additionalProperties": false
    },
    "Native": {
      "type": "object",
      "properties": {
        "metric_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "method_id": {
          "const": "Direct_PPS_0D"
        },
        "settings": {
          "type": "object",
          "properties": {
            "native_result_ref": {
              "type": "string",
              "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
            }
          },
          "required": [
            "native_result_ref"
          ],
          "additionalProperties": false
        },
        "on_unavailable": {
          "enum": [
            "fail",
            "record"
          ],
          "default": "fail"
        }
      },
      "required": [
        "metric_id",
        "method_id",
        "settings"
      ],
      "additionalProperties": false
    },
    "Recognition": {
      "type": "object",
      "properties": {
        "metric_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "method_id": {
          "const": "ModeRec_All"
        },
        "settings": {
          "type": "object",
          "properties": {},
          "required": [],
          "additionalProperties": false
        },
        "on_unavailable": {
          "enum": [
            "fail",
            "record"
          ],
          "default": "fail"
        }
      },
      "required": [
        "metric_id",
        "method_id",
        "settings"
      ],
      "additionalProperties": false
    },
    "Field": {
      "type": "object",
      "properties": {
        "metric_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
        },
        "method_id": {
          "const": "ExportModeField"
        },
        "settings": {
          "type": "object",
          "properties": {
            "mode_index": {
              "type": "integer",
              "minimum": 1,
              "maximum": 32767
            },
            "field_kind": {
              "enum": [
                "E",
                "H"
              ]
            },
            "sampling": {
              "$ref": "#/$defs/Sampling"
            }
          },
          "required": [
            "mode_index",
            "field_kind",
            "sampling"
          ],
          "additionalProperties": false
        },
        "on_unavailable": {
          "const": "record",
          "default": "record"
        }
      },
      "required": [
        "metric_id",
        "method_id",
        "settings"
      ],
      "additionalProperties": false
    },
    "PostprocessPlan": {
      "type": "array",
      "maxItems": 128,
      "items": {
        "oneOf": [
          {
            "$ref": "#/$defs/Simple"
          },
          {
            "$ref": "#/$defs/ExternalQ"
          },
          {
            "$ref": "#/$defs/Integral"
          },
          {
            "$ref": "#/$defs/Native"
          },
          {
            "$ref": "#/$defs/Recognition"
          },
          {
            "$ref": "#/$defs/Field"
          }
        ]
      }
    },
    "WtcOptions": {
      "type": "object",
      "properties": {
        "population_size": {
          "type": "integer",
          "minimum": 4,
          "maximum": 4096,
          "default": 400
        },
        "generations": {
          "type": "integer",
          "minimum": 1,
          "maximum": 10000,
          "default": 100
        }
      },
      "required": [],
      "additionalProperties": false
    },
    "Tm020Options": {
      "type": "object",
      "properties": {
        "population_size": {
          "type": "integer",
          "minimum": 4,
          "maximum": 4096,
          "default": 100
        },
        "generations": {
          "type": "integer",
          "minimum": 1,
          "maximum": 10000,
          "default": 40
        }
      },
      "required": [],
      "additionalProperties": false
    },
    "Optimization": {
      "oneOf": [
        {
          "type": "object",
          "properties": {
            "strategy_ref": {
              "const": "wtc-nsga2-v1"
            },
            "options": {
              "$ref": "#/$defs/WtcOptions"
            }
          },
          "required": [
            "strategy_ref",
            "options"
          ],
          "additionalProperties": false
        },
        {
          "type": "object",
          "properties": {
            "strategy_ref": {
              "const": "tm020-nsga2-v1"
            },
            "options": {
              "$ref": "#/$defs/Tm020Options"
            }
          },
          "required": [
            "strategy_ref",
            "options"
          ],
          "additionalProperties": false
        }
      ]
    }
  }
}
```

## 4. Schema之外的统一校验与失败契约

- metric_id全局唯一；native_result_ref必须来自服务授权目录并绑定具体工程/子工程、树项/文件、单位及可选CST结果run id。不能把任意字符串连接成路径；Direct_PPS_0D旧resultName同时充当路径的做法需替换。
- line偏移沿axis为0；counts乘积、bounds递增、累计输出预算与数值有限性在公共校验器检查。field单次最多2,000,000点，最多16项field导出且整任务点数之和≤2,000,000，防止128项组合绕过预算；这些是新设计限制，不是旧实现行为。
- 标量/分类响应每页默认100模式、最多500、≤1MiB；字段过大返回工件引用/截断说明，不丢模式冒充完整结果。all在执行前核对实际模式数和预算，超出拒绝该算子，不擅自减少求解结果。
- 输出以`status=available|unavailable|failed|needs_regeneration`、value或null、unit、source、error_ref表达。schema额外固定`on_unavailable=fail|record`，默认fail；Q_Ext固定record（未配置是预期缺项），field固定record（保持现有可选工件隔离）。fail使任务不可被消费者当完整成功采用，但不得损坏已求解快照；优化器声明的必需指标即使record也必须在策略消费前检查，不可用则该候选无效。
- ModeRec是已知会写FieldType等工程参数的后处理，不得宣传成无副作用查询；它是求解任务内的执行算子，执行后禁止为恢复该参数而Rebuild破坏场。其适用几何、分类置信度、字段存储需预检。新服务默认不给任意工程启用，项目显式登记该算法适用前提后才能用。
- 导出support_verified当前只含CalculationBox和点读取的检验，不能被新契约改名为材料支持证明。掩码/权重可信度随独立域登记事实返回；只读list_modes不触发重新导出或求解。

## 5. 优化策略冻结与固定问题定义

公共optimization对象为`{strategy_ref, options}`；options只允许population_size、generations。网格统一使用Submission.mesh，不在optimizer options中重复mesh_cells_per_wavelength；后端适配到现有属性。默认值由具体策略展开并持久化，不能读取可变类默认后悄悄改变续跑身份。options整数population_size∈[4,4096]、generations∈[1,10000]；更大的资源预算另需配置授权。既有代码有余数分支，不要求population是4的倍数。

|策略ref|默认population/generations|固定变量与边界（当前代码数值；新契约预检长度单位mm）|目标和约束|
|---|---|---|---|
|wtc-nsga2-v1|400 / 100|C2[1,500]、C3[1,200]、C4[1,100]、d1x[1,200]、d2x[500,800]、d2y[1500,1800]、g[1,1000]、L0[1,1000]|min abs(f−44.4MHz)、min Epk@2MV、max Ra；频率可行阈值0.05MHz（源码以小于判定）|
|tm020-nsga2-v1|100 / 40|Leq[50,90]、deq[340,360]、RCoaxAbsorb[40,60]、WCoaxAbsorb[5,10]、HCoaxAbsorb[20,35]|min abs(f−1500MHz)、min R/Q、max Q、max Shunt；频率阈值0.05MHz，选择首个TM或HX_TM的(0,2,0)|

这两项是专用问题，不是任意模型通用NSGA-II。target_frequency、变量边界、mutation、目标权重、seed、自由Python回调均不开放为options。当前代码同时使用Python random和NumPy随机源，未持久化完整随机状态，不能承诺可复现或中断后逐代一致续跑。新定义固定问题参数及算法身份哈希，未来允许修改必须新增明确问题定义，不暴露任意类属性。

WTC必需输出是sim_output_name列出的八项：Frequency (Mode 1)、R over Q beta=1 (Mode 1)、Q-Factor (Perturbation) (Mode 1)、Shunt Impedance (Pertubation) beta=1 (Mode 1)、Voltage beta=1 (Mode 1)、face1_Max_e、face1_Max_h、R over Q (Mode 1)。Voltage须非零且有限，R/Q分母不能为零；β缩放、Epk/Hpk和TTF的单位/公式来源由注册问题定义绑定，不允许按显示标题自动猜测。现有WTCPPS额外三项可记录，不是八项必需列表的替代。

TM020必需frequency、R_divide_Q、Q-factor、Shunt_Impedance的all-mode值及Mode_Rec分类。找不到目标模须返回MODE_NOT_FOUND候选失败，不能使用ModeIndex -1查询。分类不等于COMSOL场重叠追踪，不能据同一标签证明跨参数物理模式一致。

## 6. 已确认的迁移阻断与非承诺项

|编号|静态事实|实施前处理与能力声明|
|---|---|---|
|O01|TM020 nobj=3，object_name/convertResult给4项|统一目标维数并加向量长度门禁；当前新优化提交能力false|
|O02|TM020 convertResult先getTM020Result再判断TaskStatus；失败分支raw_obj_list/c_iobj_list/objarray可能未初始化，且ndarray不存在append方法|失败先分类，使用结构化无效候选，禁止99999假成功指标；独立失败用例|
|O03|TM020 freqdomstr=Req不在当前变量列表，freqlockmut=False；目标误差表达式写死1500|不公开频率锁定/任意target参数；若以后启用需独立修复/测试|
|O04|两优化器start自动尝试load_dumped_pop，与显式mode=new/resume不一致|后端严格按Submission模式选择，不让新任务自动拾取旧种群；resume验证问题定义/数据来源/完整随机状态策略|
|O05|WTC读取必需值未统一有限/零分母校验，失败用99999罚值；当前PPS目录单位和工程前提未注册|后台统一校验候选有效性，罚值可为优化内部策略，但对外必须标无效；当前新优化提交能力false|
|O06|简单指标mode校验较弱；params多余键可能忽略；SamplingSpec仅局部校验；line输入名mm但宏用工程坐标|使用本文唯一严格模型；新增负例及单位转换门禁，不能直接将旧configure当新Schema验证器|

冻结不等于解锁：两优化策略的输入Schema和固定问题边界已确定，但在O01–O05及公共提交接入验收前统一返回UNSUPPORTED_CAPABILITY。ModeRec任意工程能力同样false；各标量/导出是否可执行按具体工程预检。优化器相关utils不在本轮清理范围。

## 7. 本轮验收与后续

本轮静态校验文档JSON Schema及代表正反例，运行现有生成器/工件/优化入口离线测试；不启动CST，不证明物理单位、分类精度、优化收敛或新接口已实现。实际数量及报告在当前状态记录。后续按O表修复并完成公共服务迁移，再进入假Worker和真实副本门禁。

2026-10-28静态Schema：13定义，35正例、21反例通过，报告artifacts/mcp-sdk-host-static-20261028/subschema-static-checks.json。既有定向离线28 passed（11.92s）；测试是旧实现回归，不覆盖新on_unavailable策略、严格模型或优化缺口修复。
