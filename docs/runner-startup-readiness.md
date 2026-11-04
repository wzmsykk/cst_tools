# Runner冷启动就绪与诊断

基线cd5a820；本批排查不启动CST、不提交仿真任务。原现场“15秒后报就绪超时、同一Runner后来可达”没有在本轮普通启动中复现，不能声称已证明其唯一根因。实测、已复现缺陷和未确认项分别保留。

## 现行流程

GUI与MCP仍经同一个RunnerClient连接，CLI/HTTP业务合同及14个MCP工具不变。connect默认15秒；该预算现在涵盖初始状态探测、协作启动等待及HTTP就绪轮询，每次网络探测使用剩余预算与2秒中的较小值。原逻辑首次探测在15秒计时之外，末次轮询也可能再等待完整2秒。没有延长默认预算，更不改变正常求解不设总时限的规则。

CreateProcess、文件系统持久化和调度不是硬实时可中断操作，真实墙钟可略超网络探测预算；这不是求解超时。受控静默端点0.35秒预算实际约0.37秒，预算耗尽后没有启动新进程。

|边界|职责|
|---|---|
|control/bootstrap.lock|合作客户端启动临界区，等待就绪/超时后释放；其它客户端只等待连接，不再派生启动进程|
|control/runner.lock|实际Runner的OS唯一所有权；不会依据心跳、旧PID或日志来强占|
|项目运行锁|原后台执行链的工程修改/恢复互斥；HTTP就绪不授予绕过该锁的能力|
|控制租约|原client_id/claim命令控制权；启动临界区不代替租约|

持启动锁后的再次探测如果发现别人刚启动完成，只连接，不覆盖原启动者的诊断记录。已有Runner所有权却暂时不可达时，在预算内等待；不会替换它。原启动客户端超时后保留launch_attempted；后续只重新连接，同一客户端不自动重复启动。父客户端崩溃与子Runner接锁之间仍以实际Runner OS锁作最终仲裁，不宣称跨崩溃可以证明从未派生过竞争启动器。

## 诊断入口

control/bootstrap.json是最新受管连接尝试的摘要，不是任务状态或原生会话证明。包含attempt_id、started_at、startup_state、phase、launcher_pid/exit_code、首个及最后一个探测错误、实际探测数、elapsed_seconds和源码入口；就绪时另有ready_instance_id/runtime。端点仅记录PID/端口/实例ID，绝不写令牌。

control/bootstrap.log追加两类有界启动里程碑，不逐轮输出轮询或运行时长：

- RUNNER_STARTUP_CLIENT：spawn/wait/ready/timeout等尝试摘要，保留之前的失败和后续重连。
- RUNNER_STARTUP：子Runner实际PID、UTC时间、相对耗时、源码及阶段。阶段依次包含module-ready、protect-directory、runner-ownership、project-identity、restore-status、reconcile-intents、restore-checkpoint、reconcile-project、persist-status、state-ready、binding-http、publishing-endpoint、serving。

state-ready只表示内存/状态初始化完成，serving表示控制服务可用；ownership-released只表示Runner自身锁释放，均不是CST安全关闭或结果可采用证明。初始化/HTTP绑定失败保留明确失败阶段，且释放已取得的Runner锁；未创建HTTP服务器时也能正确收尾。

现有失败诊断ZIP增加bootstrap.json/log及manifest.startup摘要，即便尚无run_id或旧status仍显示COMPLETED，也可以看见独立启动失败。bootstrap不可读会明确记录，不吞掉已有运行日志。runner.json/endpoint.json仍因令牌被排除；文件数/体积/路径边界、离线导出及取消策略沿用原实现。

## 错误与恢复

|结果|含义与操作|
|---|---|
|RunnerStartupTimeout（TimeoutError子类）|预算内未确认就绪，不等于进程已死；读取诊断及最后子阶段，仅重新连接，不重新提交任务|
|RunnerStartupError（RuntimeError子类）|启动器早退、派生失败或所有权检查失败，带diagnostics；保留实际退出码/原因及日志位置，不杀进程、不替换后台|
|读取/身份失败|损坏端点作为ValueError诊断；HTML/403等未经确认的响应仍属HTTP传输失败，不当作已鉴权业务拒绝|
|RunnerRejected|保留实际Runner的JSON/409业务拒绝；不因已知拒绝制造transport unknown|
|显式重连成功|更新同一客户端尝试的可达状态，保留previous_startup_state及事件历史；当前实例身份另核对，不凭“后来可达”证明原进程健康|

诊断写入失败不掩盖原始启动错误，异常对象仍携带diagnostic_write_error。launch=False查询不创建启动记录或后台。初始化恢复旧项目状态仍保持既有RECOVERY_REQUIRED规则，不自动start、recover或重算。

## 已复现的问题与修正

Windows原RunnerOwnership先检查空文件、写首字节再加锁；两个客户端同时创建时，另一方可能已锁住该字节，使flush抛PermissionError。并发真实Python Runner测试捕获了这一竞争，单独运行不一定出现。移除加锁前写入，保留原文件内容并直接锁定偏移0的一字节。

[Microsoft _locking定义](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/locking?view=msvc-170)明确允许锁定EOF之后的字节；本机另验证空文件首持有者取得锁、第二独立句柄被拒绝、释放后可再取得，文件保持0字节。旧非空锁文件无需迁移。这个已证实竞争不能自动当成原现场15秒超时的根因。

其它修正包括：保留启动器对象以检测早退；初始探测纳入统一预算；内部预算耗尽不覆盖最后真实网络错误；连接后来成功时同步摘要；协作客户端只连接到已就绪实例时不覆盖原启动记录。对应源码为runner_client.py、runner.py和runner_ownership.py，不引入第二套服务或运行时文档系统。

## 本轮验证及剩余边界

未改代码时，3次新目录启动约0.94–1.05秒，其中一次启用导入耗时记录；另复制43条命令及结果状态到新目录启动约0.65秒。未复制CST文件、未操作原后台。这不能证明所有冷缓存、机器负载或网络盘情形都足够快。

最终受控纯Python进程通过：两次正常启动约0.94/0.86秒且标准退出0；注入初始化失败约0.84秒识别为早退并自身退出1、锁释放；一次0.3秒预算下迟就绪超时后重连，启动次数仍为1并标准退出0；静默旧端点0.35秒预算约0.37秒返回、启动次数0。这是机制对照，不是原现场根因证明，也不能把两批时长差归因为性能优化。

30项专项覆盖预算、早退/派生失败、权限/损坏端点、只读连接、令牌遗漏、锁交接、真实双客户端启动、初始化/绑定清理及迟就绪重连。更广回归与轻量记录见[验收JSON](../knowledge-base/runner-startup-readiness-20261105.json)。测试原始目录在artifacts，可能清理，不保证随Git迁移；不作为CST求解或完整故障矩阵验收。

原现场首次超时的唯一原因仍未确认。若再次发生，先保留bootstrap.json/log，按attempt_id、实际子PID、阶段时间及端点发布时间对账；不得由沙箱进程枚举缺失推断后台已退出。A1/GEO许可仍按各自源版本门禁检查，不因启动服务可用而自动升级。

最终组合236项通过（203.34秒），包含GUI重连/退出、Runner恢复、启动故障、诊断导出、MCP/SDK、文档登记及实际源码包。两项首轮失败已修正：鉴权测试精确核对HTTP 403，不依赖JSON解析副作用；F43原始标题保留以满足136项功能原意/顺序迁移门禁，新增实现另映射。专项30/47/107集合与本组重叠，不相加。最后仅元数据复核另记；原生CST未启动。

升级后需正常重载GUI/MCP客户端，已加载的旧Python模块不会因磁盘改源而自动采用新预算/诊断；本批未中断其它桌面会话。
