# me.claude

从 [storytellerF/me](https://github.com/storytellerF/me) 生成的 Claude Code 插件。请编辑源仓库；同步 PR 只由其 GitHub Actions 工作流生成。

## 安装

将生成的 Claude 仓库添加为插件市场：

```text
/plugin marketplace add storytellerF/me.claude
```

从市场安装插件：

```text
/plugin install android-emulator-profile@me
/plugin install android-device-lock@me
/plugin install recyclerview-best-practice@me
/plugin install general-coding-practices@me
/plugin install client-ui-best-practices@me
/plugin install test-report-sharing@me
/plugin install diff-sharing@me
/plugin install qemu-guests@me
```

安装后运行 `/reload-plugins`，将插件加载到当前 Claude Code 会话。

所有插件列于 `.claude-plugin/marketplace.json`。agent 提示词打包在各插件 `agents/` 目录；仅安装并不能保证所有客户端都加载 agent。

## 从 storytellerF/me 迁移

移除旧市场：

```text
/plugin marketplace remove me
```

再按上方安装步骤添加 `storytellerF/me.claude`，重新安装所用插件。市场名称仍为 `me`。

## 从 Kotlin 编码实践迁移

`kotlin-coding-practices` 已并入 `general-coding-practices`。安装或更新后者，通过客户端插件管理器移除旧 Kotlin 插件。将显式 `kotlin-project-rules` 引用改为 `code-design-rules`；Kotlin 指引保留在其平台参考中。
