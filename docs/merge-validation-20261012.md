# 2026-10-12 远端合并验证

- 本地基点：`7090439`；远端 `origin/master`：`3844ec0`。接续工作区已有的未完成合并，执行 fetch 确认远端未出现新的提交。
- 解决 14 个冲突文件，保留本地现代命名、类型化 WorkerConfig / SimulationResult、上下文日志、故障诊断、Qt 子进程环境隔离和单次 HOM 模式数量修正。
- 合入远端的原项目续算配置恢复、FAILED 项目安全恢复、HOM 区间重试及缺口记录、可读 CST 存档命名和结果索引。
- 远端新增调用迁移到当前方法名；SimulationResult 增加 task_id / result_directory，在算法边界输出 TaskID / ResultDirectory，保留存档追踪能力。
- 非集成验证：`python -m pytest -q test -m "not integration"`，314 passed / 19 deselected。包含恢复配置、任务确认后存档、单模式约束及 GUI 假 Worker 流程测试。
- 19 项真实 CST 集成测试本次未执行；普通测试通过不代表真实求解、性能或窗口交互验收。
- `utils` 无改动；本次不推送远端。
