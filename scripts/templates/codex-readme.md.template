# me.codex

从 [storytellerF/me](https://github.com/storytellerF/me) 生成的 Codex 插件。请编辑源仓库；同步 PR 只由其 GitHub Actions 工作流生成。

## 安装

将生成的 Codex 仓库添加为插件市场：

```bash
codex plugin marketplace add https://github.com/storytellerF/me.codex.git
```

从市场安装插件：

```bash
codex plugin add android-emulator-profile@me
codex plugin add android-device-lock@me
codex plugin add recyclerview-best-practice@me
codex plugin add general-coding-practices@me
codex plugin add client-ui-best-practices@me
codex plugin add test-report-sharing@me
codex plugin add diff-sharing@me
codex plugin add qemu-guests@me
```

安装后开启新的 Codex 对话，以加载插件 skill 和 MCP 工具。

所有插件列于 `.agents/plugins/marketplace.json`。源 skill 从可移植仓库原样复制；Codex 包不包含 Claude agent 提示词和路由。

## 从 storytellerF/me 迁移

移除旧市场：

```bash
codex plugin marketplace remove me
```

再按上方安装步骤添加 `storytellerF/me.codex`，重新安装所用插件。市场名称仍为 `me`。

## 从 Kotlin 编码实践迁移

`kotlin-coding-practices` 已并入 `general-coding-practices`。安装或更新后者，通过客户端插件管理器移除旧 Kotlin 插件。将显式 `kotlin-project-rules` 引用改为 `code-design-rules`；Kotlin 指引保留在其平台参考中。
