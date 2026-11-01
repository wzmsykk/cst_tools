# GUI布局和恢复退出边界（2026-11-02）

源码/离线证据：动态insertWidget会改变QLayout位置索引；插入错误标签后硬编码setStretch(1,1)将剩余高度赋给标签。固定选择实际workspaceSplitter，不能凭最大化截图归因为Qt绘制或CST。离线几何回归覆盖两个尺寸及tab切换；offscreen无字体截图不作为文字视觉通过。

项目RECOVERY_REQUIRED与CST物理安全不同：确认进程都已退出后，Runner可保留逻辑恢复标记正常退出；running/unknown仍拒绝。拒绝shutdown不应靠清空检查点或结束控制台绕过。参见[实现与验收](../docs/gui-maximize-and-recovery-exit.md)。未操作真实CST或现场进程。
