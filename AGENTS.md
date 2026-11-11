# 仓库维护规则

本仓库是 `me` 插件集合及其可移植 agent 提示词的权威来源。

## Agent 与 Claude 兼容性

- 可复用 agent 提示词保存在所属插件根目录的 `plugins/*/agents/*.md`，与该插件 `skills/` 目录并列。
- Claude agent 指令使用 Markdown，frontmatter 只包含 Claude 兼容字段：`name`、`description`、`model`、`effort`。
- 源 skill frontmatter 保持可移植。Claude 的 `context: fork` 和 `agent: <agent-name>` 路由按 skill 目录保存在 `extensions.com.anthropic.claude.skillFrontmatter`，只注入生成的 Claude skill。Codex 副本必须保持源 skill 不变。
- 不声称安装插件会自动安装 agent。

## 可移植源码与客户端生成

- 插件身份和版本只在 `plugins/*/plugin.json` 维护，使用 Agent Plugins 1.0.0 schema。客户端清单字段放在 `extensions.com.openai.codex` 和 `extensions.com.anthropic.claude`；生成客户端清单，不重复维护源清单。
- 使用 `scripts/build-claude-plugin-package.sh --all` 将 Claude 包生成到 `../me.claude`，先检查并保留无关工作。使用 `scripts/validate-plugin-packages.py` 验证两套发行包。
- `.github/workflows/sync-client-distributions.yml` 同步 `me.codex` 与 `me.claude`；只有该工作流可以提交、推送或提出生成发行变更。

## Codex 包生成与验证

- 源码变化后运行 `scripts/build-codex-plugin-package.sh --all`，在本地相邻 `../me.codex` 检出目录生成包，供审阅和验证。命令会替换原生成内容，运行前检查相邻目录并保留无关工作。
- 交付前，在本地验证生成的 skill 副本、插件清单、市场和相关安装行为。独立验证可移植源 skill；Codex 专用检查只针对生成的 Codex 包运行。
- `.github/workflows/sync-client-distributions.yml` 是向上游 `me.codex` 提交、推送和提出生成变更的唯一支持路径。它在变更合入 `main` 后运行，也可通过 GitHub Actions 手动启动。
- 不在本地 `me.codex` 检出目录提交生成包，不推送同步分支，也不手动创建 `me.codex` PR。
- 生成与验证逻辑留在源仓库，使本地检查和工作流可复现。
- 交付前验证源码和本地生成变更。工作流发布同步插件变更后，告知用户何时需要开启新的 Codex 对话。

## 文档与版本

- skill 或 agent 变化时，更新所属 `SKILL.md`、`README.md` 及适用的 `CLAUDE.md` 引用。自定义 agent 提示词仍留在插件根目录。
- 每个插件版本使用 `MAJOR.MINOR.PATCH-YYYYMMDDHHMMSS`。生成的 `.codex-plugin/plugin.json` 和 `.claude-plugin/plugin.json` 版本与可移植清单完全一致，不添加环境或工具标签。
- 同一 PR 中，插件语义版本（`MAJOR.MINOR.PATCH`）最多升级一次。首次升级后，后续提交保持语义版本不变；只有新 PR 才再次升级。`YYYYMMDDHHMMSS` 时间后缀不受此限制，同 PR 后续插件变更可以刷新。生成客户端清单版本必须与可移植清单一致。

## 使用项目的独立性

- 每个会修改或操作使用插件的项目的 skill，都必须自行说明适用的项目独立性边界，不要求另装 skill。agent 提示词保持一致。共享原则见 `plugins/general-coding-practices/skills/project-collaboration-rules/SKILL.md`；文档指引见 `project-docs-and-rules`。
- 除非用户要求集成，否则不将 AI 插件实现和编排细节写入使用插件的项目。保留 Gradle 插件、Appium 驱动或扩展等正常项目依赖。本仓库维护 AI 插件本身，因此可以记录其安装和实现。

## 隐私

- 提示词保持通用并保护隐私。不得向本仓库复制原始账户对话、机密或个人标识。
