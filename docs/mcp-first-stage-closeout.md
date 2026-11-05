# MCP首阶段收口与使用边界

2026-11-06。实现基线4738f62加本批MCP边界修正；本页描述已实现范围，不取代外部协议或完整COMSOL对齐计划。

## 完成范围

首阶段为本机CST2022根MWS：通过14个公共工具新建工程、参数化几何、设置、保存重开验证、单次Eigenmode计算、Frequency/RQ结果采用及JSON/CSV导出，再正常关闭。公共定义的GUI/CLI/MCP入口复用ApplicationService、Runner、Managed Worker与RunStore，没有新增求解框架。

受限A1和geometry-v1的具体契约见[类型化接口](typed-definition-service.md)与[GEO实现](geometry-production-implementation.md)。当前闭环是PEC背景/内部真空、Default/Tet固定密度、nmodes=1；GEO仿真目标限定六面electric。实体集合可用；面/边稳定选择、多材料及其它求解器不属于本阶段承诺。几何目标保存成功不等于仿真ready。

已有真实证据：2026-11-03[桌面正常链](codex-desktop-acceptance-20261103.md)，2026-11-04[桌面GEO链](codex-desktop-geometry-20261104.md)、XYZ原生小网格及[独立A1校准](a1-recalibration-20261104.md)。本批未重新启动CST，不把旧数字当新代码运行验收；G01–G08分项见[现行门禁](g01-g08-progress.md)。

## 调用顺序与身份

1. `list_installations`获取服务器授权的installation_ref；`connect_project(client_id, launch=True)`显式启动/连接独立Runner，取得control_handle，再`control_project(operation="claim")`申请控制权。只读查询不启动Runner或CST。
2. `create_project`返回操作身份；轮询`get_project_status`，核对同一run_id和执行状态，再用`get_operation_result`取得document_id及document_revision。提交回执不是操作完成。
3. `apply_model_changes`提交类型化声明和expected_document_revision。geometry-v1可先`save_project(validation_target="geometry")`；此时geometry_saved不授予ready。修改声明生成候选历史，不向原工程追加同名块冒充替换。
4. `configure_simulation`提交受支持设置及后处理；`save_project(validation_target="simulation")`验证保存重开和原生事实。每次使用返回的新修订；原生会话失败或退出未确认不发布ready。
5. `submit_run`只接受已验证的definition_revision。查询状态后用`get_simulation_results`取得已采用结果及result_revision，再`export_simulation_results`获取本地JSON/CSV工件、大小及hash。
6. `inspect_model`可只读核对保存身份；`close_project`关闭逻辑文档，原生会话已按操作收尾。`control_project(operation="shutdown")`请求后台退出；有活动/待恢复会话时不能把拒绝当已安全退出。

写入受Runner租约检查；句柄不等于控制权，也不等于认证凭据。适配器进程最多64个client_id句柄，同client_id复用，重启适配器后失效；最多8个并发适配调用，超限立即拒绝，不形成额外队列。共享服务重载影响其它使用同一服务的会话，应正常协调。

响应丢失时沿用同一业务request_id及相同载荷，使用新的JSON-RPC请求ID查询/重试；不能换业务ID再次求解。恢复先对账，采集/ACK/关闭证据缺失保留待恢复，不能假定成功。正常求解没有固定总超时；通信、启动及收尾等待仍有界。stdio EOF或协议取消不停止独立计算，停止使用显式control_project及Runner状态确认。

## 协议与错误

实现固定现代MCP 2026-07-28、官方Python SDK 2.3.0的tools-only stdio子集。14工具排序、私有目录ttl=0；每请求版本/能力元数据、请求ID、通知和取消由信封防护与SDK共同处理。无任意VBA、任意安装路径或任意文件读取入口。

按[官方工具错误定义](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)，未知工具返回协议错误-32602；已知工具输入/业务拒绝返回complete、isError=true。非法JSON/请求信封等属于协议错误，不能混成求解失败。后台输出在SDK转换前检查对象根及JSON可序列化、有限数值；非法值返回INVALID_OUTPUT，不能静默转换为成功值。错误后仍允许后续请求。该检查不是逐字段业务结果Schema或完整ErrorDTO保证，成功结果仍须公共服务证据核验。

导出返回本地工件引用，不提供resources/read或远程下载。业务阶段/status不冒充协议progress token；没有声明resources、prompts、订阅、MRTR、Tasks、Streamable HTTP或OAuth能力。Runner内部HTTP不是MCP HTTP；这些未启用扩展不属于本阶段必需功能，也不据此宣称全面规范符合。

## 验收与后续

本批SDK/原始stdio/适配测试32项通过：补充未知工具零业务派发、NaN/Infinity/bytes/非对象拒绝、错误后正常中文/换行线路返回。原始线路解析器拒绝非有限JSON。相关服务恢复/登记组合89项通过，源码包指纹取样问题对齐后包边界及登记10项复验通过（集合重叠，不累加）。A1/GEO源码许可仍有效。报告见[轻量记录](../knowledge-base/mcp-first-stage-closeout-20261106.json)；临时测试目录可再生成，不保证随Git迁移。

后续独立范围：真实Start=0/Start自身异常；完整N01–N25边界/并发组合；其它宿主/版本和跨授权部署；面边/复杂CAD/多材料；完整HOM与模式身份、分布式执行。不以正常对话通过替代这些矩阵。原现场首次15秒冷启动超时尚未唯一归因；已有诊断修正不构成现场复现证明。已加载服务需正常重载才能采用本批代码，本批没有再次桌面热加载验收。
