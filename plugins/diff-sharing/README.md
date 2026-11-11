# 代码差异分享插件

生成优先使用 Difftastic 的可浏览 Git 差异站点，用于本地预览或用户要求的公开分享。`difft` 不可用时，Git 仍可作为回退渲染器。此 skill 用于差异报告或预览、分享 URL 请求；普通 Git 查看、代码审查和补丁编辑不需要报告服务。

## 使用项目的独立性

通过外部辅助工具和报告缓存分享，不向被比较项目的构建、CI 或文档添加 AI 插件脚本或安装路径。用户可以明确要求项目自有产物或持久集成；普通项目依赖保持不变。

## 工作流程

```bash
plugins/diff-sharing/scripts/generate-diff-report.sh
plugins/diff-sharing/scripts/generate-diff-site.sh
plugins/diff-sharing/scripts/start-ngrok.sh --local-only
```


`difft` 成功渲染比较时，页面默认选择 Difftastic；否则选择 Git diff，并说明渲染器缺失或失败的原因。

已安装插件使用绝对脚本路径，可从 Git 仓库内任意目录调用。所有命令自动使用仓库根目录。

统计、Git 补丁和 Difftastic 始终比较相同的全仓库范围，三者均排除子模块变更。已提交版本比较只使用选定 Git 历史；即使当前工作区有同名文件，已删除文件的删除侧也保持为空。


`start-ngrok.sh --local-only` 在 `127.0.0.1` 提供站点。普通启动模式在 ngrok 缺失或认证失败时也保留本地服务。凭据来自已保存配置或 `NGROK_AUTHTOKEN`。URL 使用期间保持启动器运行；Ctrl+C 只停止它自己的服务和隧道。

skill 在预览或未明确受众时选择仅本地模式。公开分享必须由用户要求，仅有保存的 ngrok 凭据不会选择公开模式。启动器未指定 `--local-only` 时，其普通模式仍会尝试隧道。

`.sh` 是轻量兼容启动器。每个命令都有同名 `.py` 入口，例如 `python /path/to/plugin/scripts/start-ngrok.py --local-only`。生成、站点组装和服务共用以 Git 仓库根目录为键的缓存，即使从不同子目录调用也一致。

默认缓存键现使用原生 Python 项目路径。升级后重新生成报告，或传入相同的显式 `--output-dir` 来复用旧缓存。

显式相对 `--output-dir` 和 `REPORT_OUTPUT_DIR` 以原调用目录解析，不改变调用者工作目录。

## 配置


| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `REPORT_OUTPUT_DIR` | 生成产物目录 | `~/.cache/diff-reports/<project-hash>` |
| `NGROK_AUTHTOKEN` | ngrok 令牌覆盖值 | 未设置时使用保存凭据 |
| `NGROK_PORT` | 对外提供的本地端口 | `8080` |
| `PYTHON_COMMAND` | 所有命令使用的 Python 3.10+ 可执行文件 | 先 `python3`，后 `python` |
| `GIT_BASE_REF` | Git 基准引用 | `main` |
| `GIT_COMPARE_REF` | 排除未提交变更时的比较引用 | `HEAD` |
| `GIT_INCLUDE_UNCOMMITTED` | 包含未提交变更 | `true` |
| `DIFFTASTIC_COMMAND` | Difftastic 可执行文件名或路径 | `difft` |
| `DIFFTASTIC_WIDTH` | 捕获 Difftastic 输出的宽度 | `160` |
| `DIFFTASTIC_SKIP_UNCHANGED` | 省略未变更文件 | `true` |
| `DIFFTASTIC_PARSE_ERROR_LIMIT` | 文本回退前的解析错误数 | `100` |


## 环境要求

- 兼容 `.sh` 启动器需要 **Bash**；原生 Python 入口也可不依赖 Bash 运行。
- **Git**：代码差异分享所需。
- **Difftastic（`difft`）**：首选结构化渲染器所需。
- **ngrok**：公开分享所需；否则使用本地服务 URL。
- **Python 3.10+**：全部报告和预览命令所需。Shell 入口依次检查 `python3`、`python`，`PYTHON_COMMAND` 可覆盖解释器选择。

## 许可证

本插件属于 me 插件集合。

## 插件打包

`plugin.json` 是可移植元数据的权威来源。客户端清单与完整 skill 资源会生成到 `me.claude` 和 `me.codex`，请从这两个仓库安装。源 skill 使用可移植的 frontmatter。Claude 路由按 skill 目录保存在 `extensions.com.anthropic.claude.skillFrontmatter` 中，仅注入生成的 Claude skill。Codex 的 skill 文件保持源文件原样复制。

## 快照发布

每次成功生成都会发布完整快照。构建失败时旧报告仍可访问，已打开页面保留原资源。启动器 URL 打开最新快照。旧代次继续保留；只有服务和读取者均结束后，才移除专用报告缓存。无效比较引用明确失败，不替换为其他历史。Difftastic 已安装但渲染失败时，页面选择可用的 Git diff。

## 改进反馈

插件问题向 [storytellerF/me issues](https://github.com/storytellerF/me/issues) 反馈。报告前，skill 要求检索已打开和已关闭的 issue，使用脱敏或合成示例，并遵循用户已有的发布授权。优先复用已有报告；无法访问时，保留尚未提交的草稿。
