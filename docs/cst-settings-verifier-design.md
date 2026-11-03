# CST设置验证器：现行设计与证据分层

更新：2026-11-02。详细字段/历史语义规则见[B2](settings-history-projection.md)和[A1允许表](a1-history-command-profile.md)，执行证据见[B3](execution-snapshot-verification.md)/[采集](native-execution-capture.md)，生产入口见[公共服务与G03](single-simulation-service.md)。

## 来源矩阵

|设置/事实|当前可靠来源|限制|
|---|---|---|
|单位、solver身份、结构/持久设置|同scope有效历史投影；G03保存重开后再次核对|不是任意VBA解释器，未知语法/编码拒绝|
|方法、模式数、target、自适应与Tet密度定义|允许表历史、参数表达式、Decimal精确值及保存后投影|不发明live getter；target不能用GetFmin冒充|
|原生身份、频率上下限、网格类型|已加载3D项目的文档化/已校准读回；G03两会话|核对版本、scope、路径、单位及数值分辨率|
|实际求解配置|GetDataBaseValue六字段执行快照，绑定attempt/revision/nonce与DB双hash|Save不刷新旧值，Rebuild后可能缺失；不是当前live设置|
|实际成功|completion/ACK、结果产物、指标、采用及标准退出独立核验|Start=1、退出0或配置匹配单独不足|

## 生产路径

B1共用cst_version严格只读核心 → B2冻结完整A1定义 → 显式G03副本保存/重开 → 公共single-simulation → Managed原生pre/start/post采集 → RunStore关闭后归档/绑定 → 结果采用。预检/验证不为查询设置而额外求解，G03不调用Solver.Start。

2022按用户指定大版本行为一致策略处理，精确安装hash仍保存且尝试内必须不变；实际G03/G04验收仅本机2022.5。[真实记录](single-simulation-g04-acceptance.md)覆盖一次Pillbox正常链，不覆盖所有版本和失败组合。

## 当前门禁与待办

重新验证先撤销旧ready；失败/未知退出保留诊断并阻断提交。未知原始编码、完整旧模板或不可解释控制流继续unsupported。方法/target等没有通用live getter，不把执行库伪装为持久定义读回。

验证会话已接入统一恢复、退出核验及GUI事实展示；真实中断矩阵/显式GUI验证操作、完整Save/Rebuild故障矩阵、跨版本和指定桌面建模闭环仍未完成；公共类型化建模发布与SDK纵向链已有[11月3日验收](typed-public-acceptance-20261103.md)。V01–V06原始逐项校准和56项人工用例身份不改写为全通过；具体来源、数值及原时点结论保留在[归档设计](archive/20261102-progress-consolidation/cst-settings-verifier-design.md)。归档是分析与证据，不是当前接口。
