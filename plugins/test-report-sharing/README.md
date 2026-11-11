# 测试报告分享插件

将已有测试报告收集成可浏览站点，用于本地预览或用户要求的公开分享。此 skill 用于报告收集、预览和分享；仅运行测试或诊断失败，不代表要求生成报告站点或再次运行测试。

## 使用项目的独立性

收集器读取已有报告，不让项目测试依赖本 AI 插件的收集、查看或隧道脚本。普通测试报告和覆盖率插件仍为有效依赖；项目自有报告或持久集成属于另行要求的变更。

## 工作流程

```bash
plugins/test-report-sharing/scripts/collect-test-results.sh
plugins/test-report-sharing/scripts/generate-report-site.sh
plugins/test-report-sharing/scripts/start-ngrok.sh --local-only
```


Claude agent 路由可用时，`test-report-operator` 协调同一流程。

已安装插件使用绝对脚本路径。每个命令接受 `--project-dir DIR`，默认当前目录，用作报告搜索、相对自定义报告目录和默认缓存的基准。收集会发现 HTML 根目录，以及各搜索根目录下最多四层目录内的嵌套 JUnit XML。重叠 HTML 根目录去重；不同路径下的同名 XML 分别保留并从站点链接。输出应位于被复制报告之外。


`start-ngrok.sh --local-only` 在 `127.0.0.1` 提供站点。普通启动模式在 ngrok 缺失或认证失败时也保留本地服务。凭据来自已保存配置或 `NGROK_AUTHTOKEN`。URL 使用期间保持启动器运行；Ctrl+C 只停止它自己的服务和隧道。

skill 在预览或未明确受众时选择仅本地模式。公开分享必须由用户要求，仅有保存的 ngrok 凭据不会选择公开模式。启动器未指定 `--local-only` 时，其普通模式仍会尝试隧道。

`.sh` 是轻量兼容启动器。每个命令都有同名 `.py` 入口，例如 `python /path/to/plugin/scripts/start-ngrok.py --local-only`。收集、站点组装和服务使用相同 `--project-dir`，以共用默认缓存。

默认缓存键现使用原生 Python 项目路径。升级后重新生成报告，或传入相同的显式 `--output-dir` 来复用旧缓存。

```bash
python /path/to/plugin/scripts/collect-test-results.py --project-dir /path/to/project
python /path/to/plugin/scripts/generate-report-site.py --project-dir /path/to/project
python /path/to/plugin/scripts/start-ngrok.py --project-dir /path/to/project --local-only
```

显式相对 `--output-dir` 和 `REPORT_OUTPUT_DIR` 以原调用目录解析。扫描和复制的报告目录树排除已注册子模块，包括显式指定的搜索根目录。从 Git 仓库收集时需要 Git 识别注册子模块；非 Git 项目不需要 Git。对于旧版未排除子模块时收集的报告，使用全新输出目录。

## 配置


| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `REPORT_OUTPUT_DIR` | 收集报告的输出目录 | `~/.cache/test-reports/<project-hash>` |
| `TEST_RESULT_DIRS` | 兼容旧版的冒号分隔报告目录，`REPORT_DIRS` 为别名；Windows 盘符路径使用重复的 `--test-dir DIR` | 自动检测 HTML/JUnit 位置 |
| `NGROK_AUTHTOKEN` | ngrok 令牌覆盖值 | 未设置时使用保存凭据 |
| `NGROK_PORT` | 对外提供的本地端口 | `8080` |
| `PYTHON_COMMAND` | 所有命令使用的 Python 3.10+ 可执行文件 | 先 `python3`，后 `python` |


## 环境要求

- 兼容 `.sh` 启动器需要 **Bash**；原生 Python 入口也可不依赖 Bash 运行。
- **ngrok**：公开分享所需；否则使用本地服务 URL。
- **Python 3.10+**：全部报告和预览命令所需，无需第三方 Python 包。

## 许可证

本插件属于 me 插件集合。

## 插件打包

`plugin.json` 是可移植元数据的权威来源。客户端清单与完整 skill 资源会生成到 `me.claude` 和 `me.codex`，请从这两个仓库安装。源 skill 使用可移植的 frontmatter。Claude 路由按 skill 目录保存在 `extensions.com.anthropic.claude.skillFrontmatter` 中，仅注入生成的 Claude skill。Codex 的 skill 文件保持源文件原样复制。

## 快照发布

每次收集发布包含站点的完整替换快照。重复收集不会让当前视图重复报告；源报告删除后，下一快照不再包含它。收集失败保留旧版本。启动器 URL 打开最新快照，已打开页面保留原资源。旧代次继续保留，因此只有服务和读取者结束后，才移除专用报告缓存。

链接资源在发布时复制并物化到每个快照，后续源变化不改变已打开报告。目录循环会使收集失败，复制失败保留上次发布；不保留指向源的实时链接。

## 改进反馈

插件问题向 [storytellerF/me issues](https://github.com/storytellerF/me/issues) 反馈。报告前，skill 要求检索已打开和已关闭的 issue，使用脱敏或合成示例，并遵循用户已有的发布授权。优先复用已有报告；无法访问时，保留尚未提交的草稿。

独立报告页面默认跟随系统浅色或深色偏好，打开期间切换系统主题也会即时更新。收集的第三方测试报告保留原始样式。
