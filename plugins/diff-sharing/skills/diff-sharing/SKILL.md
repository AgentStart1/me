---
name: diff-sharing
description: 用户需要可浏览的 HTML 代码差异报告，或预览、分享分支、PR、提交及工作区变更的 URL 时使用。没有报告、预览或分享请求的普通 Git 查看、代码审查和补丁编辑不触发。
---

# 代码差异分享

预览或分享测试报告时，若可用，使用 `test-report-sharing`。本 skill 生成差异站点；普通代码查看或审查无需启动报告服务。

## 使用项目的独立性

通过外部定位的辅助工具和插件报告缓存渲染、提供差异。不能仅为分享差异就修改项目构建、CI、依赖或文档，内置辅助工具，或添加 AI 插件命令。隧道凭据和进程状态留在项目外。用户明确要求时，可以添加项目自有文档、报告产物或持久集成；正常 Git 和构建插件依赖不受影响。

## 必需行为

- 生成当前分支相对于 `main` 或用户指定基准引用的 HTML 差异报告。
- Difftastic（`difft`）可用时，优先作为初始渲染器，同时提供 Git diff 选项。
- Difftastic 不可用时，Git 是唯一可用的默认渲染器，明确报告缺少该可执行文件；不自动安装。
- 不论从哪个子目录调用，Git 操作和缓存标识都以检测到的仓库根目录为准。默认缓存和所有比较查询使用该根目录。已提交版本比较不得混入工作区内容；删除的一侧必须保持为空。
- 统计、Git 补丁和 Difftastic 输出均排除子模块变更。
- 保留 Difftastic 的行内和并排布局切换、新旧源码上下文及变更结构片段的强调显示。
- 将差异组装到静态报告站点。本地预览或未明确受众时使用 `--local-only`；用户要求公开分享时使用 ngrok。仅有已保存凭据不能决定公开分享。
- 返回实际公开或本地 URL、比较引用、默认渲染器和差异统计。
- 从已安装插件根目录定位脚本，在目标项目中通过绝对路径调用。下方相对路径快速示例用于源码检出目录。

## 运行时

全部控制逻辑使用 Python 3.10+ 标准库。已有 `.sh` 是轻量启动入口，每个都有同名 `.py` 供原生直接执行。显式相对输出路径以原调用目录解析，不改变调用者工作目录。运行时不依赖 GNU 文本工具或 jq。

## 快速开始

```bash
plugins/diff-sharing/scripts/generate-diff-report.sh
plugins/diff-sharing/scripts/generate-diff-site.sh
plugins/diff-sharing/scripts/start-ngrok.sh --local-only
```

## 配置

- `REPORT_OUTPUT_DIR`：生成产物目录，默认 `~/.cache/diff-reports/<project-hash>`。
- `NGROK_AUTHTOKEN`：令牌覆盖值，也支持已认证的保存配置。
- `NGROK_PORT`：对外提供的本地端口，默认 `8080`。
- `PYTHON_COMMAND`：所有 Shell 启动器使用的 Python 3.10+ 可执行文件，默认依次尝试可用的 `python3`、`python`。
- `start-ngrok.sh --local-only`：仅在回环地址提供报告，不尝试隧道。
- `GIT_BASE_REF`：差异基准引用，默认 `main`。
- `GIT_COMPARE_REF`：`GIT_INCLUDE_UNCOMMITTED=false` 时的比较引用，默认 `HEAD`。
- `GIT_INCLUDE_UNCOMMITTED`：是否包含未提交变更，默认 `true`。
- `DIFFTASTIC_COMMAND`：Difftastic 可执行文件名或路径，默认 `difft`。
- `DIFFTASTIC_WIDTH`：捕获 Difftastic 输出的宽度，默认 `160`。
- `DIFFTASTIC_SKIP_UNCHANGED`：省略未变更文件，默认 `true`。
- `DIFFTASTIC_PARSE_ERROR_LIMIT`：回退逐行比较前允许的解析错误数，默认 `100`。

## 随包资源

- `scripts/generate-diff-report.sh`：生成 Git 与 Difftastic HTML 报告。
- `scripts/generate-diff-site.sh`：组装包含差异的静态站点。
- `scripts/start-ngrok.sh`：通过 ngrok 或本地服务提供站点。
- `templates/diff-report.html` 与 `templates/diff-report.css`：差异页模板和样式表。

## 失败处理

- Git 或指定基准引用不可用时报告失败，不发布误导性比较。
- Difftastic 不可用或无法生成结构化差异时，保留可用的 Git diff，并说明切换默认渲染器的原因。
- ngrok 不可用或未配置时，回退到本地 HTTP 服务 URL。
- 公开隧道需要来自环境变量或已保存配置的有效 ngrok 凭据，不声称支持匿名免费访问。本地服务绑定 `127.0.0.1`，持续到调用者停止启动器；只停止该启动器的子进程。
- `python3` 低于 3.10 或无法运行时，使用通过版本检查的 `python`。需要明确解释器路径时遵循 `PYTHON_COMMAND`。

## 快照发布

每次成功生成都会发布完整快照。构建失败时旧报告仍可访问，已打开页面保留原资源。启动器 URL 打开最新快照。旧代次继续保留；只有服务和读取者均结束后，才移除专用报告缓存。无效比较引用明确失败，不替换为其他历史。Difftastic 已安装但渲染失败时，页面选择可用的 Git diff。

## 上游改进反馈

- 发现有明确改进方向的插件缺陷或可复用的改进建议时，向 [storytellerF/me](https://github.com/storytellerF/me/issues) 反馈，并注明插件和 skill。若问题仅属于当前项目，且没有插件缺陷的证据，则不在此范围内。先完成主要任务，再处理不影响当前工作的反馈。
- 搜索或发布之前，将证据整理为不含隐私的最小摘要或合成复现案例。不得泄露原始对话、私有代码、日志、截图、凭据、个人或账户信息，以及私有路径和 URL。如果无法安全披露，就只在本地保留发现。
- 搜索已打开和已关闭的 issue，阅读可能匹配的报告及其解决方案。优先复用已有报告；如果是不同的回归问题或尚未覆盖的场景，可另建 issue 并关联原报告。发布新 issue 或有实质帮助的评论必须已经获得用户授权；本规则本身不授予发布权限。未获授权时，准备一份尚未提交的草稿。
- 反馈应包含插件和 skill 版本、实际与预期行为、复现步骤或建议，以及重复报告的检索结果。新 issue 的标题应以插件名开头。访问或提交失败时，保留草稿并说明阻碍。提交结果不确定时，先确认是否已成功，再考虑重试。返回报告链接，或明确标注草稿尚未提交。
