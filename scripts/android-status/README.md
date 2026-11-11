# Android 状态面板源码

本目录维护模拟器和设备锁插件共用的 MCP Apps UI 及 ADB 读取工具。各插件仍可独立安装：`npm run build` 为每个所属插件写入自包含 HTML 资源及 `android_probe.py` 副本。在此修改共享源码后重新生成，不直接编辑生成文件。每个插件自行维护收集器和 stdio MCP 服务。

从仓库根目录运行：

```bash
npm ci --prefix scripts/android-status
npm run build --prefix scripts/android-status
npm test --prefix scripts/android-status
uv run --script tests/android-status/test-status.py
uv run --with playwright==1.62.0 playwright install chromium
uv run --script tests/android-status/test-panels.py
python plugins/android-emulator-profile/tests/test-start-avd-docker.py
bash scripts/build-codex-plugin-package.sh --all
python3 scripts/validate-generated-codex-skills.py ../me.codex
```

浏览器测试使用模拟 MCP Apps 宿主和伪设备快照；收集器及协议测试使用模拟 ADB，绝不启动模拟器或修改真实锁。可通过 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 选择已有 Chromium。`ANDROID_PANEL_SCREENSHOTS` 可将伪快照预览图输出到已存在目录。

测试覆盖初始结果呈现、刷新、过时快照、未知与空闲或停止的区别、安全文本呈现、租约倒计时、显式序列号截屏、元数据脱敏，以及响应式和深色布局。运行宿主需支持 MCP Apps，以及 `openai/ui` 全局侧栏和对话入口。不提供设置扩展。
