# 开发

## 报告分享控制器

`diff-sharing` 和 `test-report-sharing` 使用 Python 3.10+ 标准库控制器。同名 `.py` 入口负责参数解析、报告生成与收集、回环服务和隧道生命周期；`.sh` 只选择解释器并转发参数。公开隧道仍需要 ngrok 和凭据。

共享运行时的权威源码为 `scripts/report-sharing/report_runtime.py`。修改后运行 `python scripts/sync-report-runtime.py`，将相同副本打包到两个可独立安装的插件；`--check` 检查副本一致性。维护的页面主体放在各插件 `templates/` 目录。

运行两个插件的轻量 Shell 兼容套件，以及 `python tests/test-report-python.py`、`python tests/test-report-snapshots.py`、`python tests/test-report-launchers.py` 和 `python tests/test-validation-workflow.py`。通过 `uv run --with playwright==1.62.0 playwright install --with-deps chromium` 安装浏览器，再运行 `uv run --script tests/test-report-browser.py`。Windows 将 Git Bash 加入 PATH，或通过 `BASH_TEST_BINARY` 指定其绝对可执行路径，以验证 Shell 分派约定（Windows CI 也这样避免 WSL `bash.exe` shim）。`PLAYWRIGHT_CHROMIUM_EXECUTABLE` 可选择已安装 Chromium。

浏览器测试使用生成的本地快照和确定性的 Difftastic CLI 夹具，不使用真实 Difftastic 安装或公开隧道。每项浏览器约定有独立 unittest 结果。不使用共享设备或已有报告服务。

报告测试覆盖分工：

| 约定 | 套件 |
| --- | --- |
| JSON 摘要、有限扫描、重复 XML 内容、HTML 去重、目录别名、空报告、URL 编码和标签转义 | `tests/test-report-python.py`（含 `report_contracts.py`） |
| Difftastic 配置与载荷、不可用或失败状态、Git 统计、提交和工作区模式、子模块排除 | `tests/test-report-python.py` |
| 实际渲染片段与上下文、安全特殊字符、渲染器和布局切换、Git 回退、系统主题首次加载/动态切换/重载与文字对比度 | `tests/test-report-browser.py` |
| 原子发布失败、重叠快照和不可变链接资源 | `tests/test-report-snapshots.py` |
| 回环服务与隧道生命周期、取消 | `tests/test-report-launchers.py` |
| Shell 目标脚本、准确参数边界、退出状态传播 | `tests/test-report-python.py`（`ShellContracts`，使用记录解释器夹具） |
| Shell 帮助、无效参数、解释器选择 | 插件 `tests/test-*.sh` 套件 |

原生和浏览器套件共享 `tests/report_test_support.py` 夹具。源码字符串断言只用于明确的模板归属约束；交互断言在 Chromium 执行。覆盖检查器发现所有 `tests/test-report-*.py` 入口，并要求接入 CI。新约定保持独立命名，不在同一测试累加无关操作。

原生测试覆盖有限扫描、自定义项目目录、重叠根目录、递归输出拒绝、URL 和 HTML 转义、二进制 Git 统计、提交比较及无效输入。参数解析返回显式项目和输出路径，不改变全局 cwd。Git 查询指定仓库 cwd，报告扫描以 `--project-dir`（默认调用者 cwd）解析根目录，缓存标识使用该项目。

全部 Git 差异查询通过一个共享命令边界排除子模块。收集在发现和复制目录时排除注册 gitlink 及 `.gitmodules` 路径，非 Git 项目不要求 Git。回归覆盖提交内新增、更新、删除，变化或脏子模块，从根目录和子目录执行的两种 `diff.relative` 设置，以及全仓库范围和缓存站点复用。无需再渲染 gitlink 内容，也无需逐查询修补根相对路径。显式工作区比较模式和删除侧为空仍是必要约定。

将 `REPORT_TEST_PLUGINS` 指向生成客户端的绝对 `plugins/` 目录，可测试随包入口。回环测试从子目录启动，验证默认缓存选择、`--project-dir`、取消、ngrok 失败及模拟运行中隧道。Windows 使用新进程组和 Ctrl+Break 验证平滑取消；操作系统强制终止无法运行清理。这些测试不验证真实 ngrok 认证。

可直接通过 `python /path/to/plugin/scripts/<command>.py` 运行报告。跨平台自定义根目录使用重复 `--test-dir DIR`；`--test-dirs`、`TEST_RESULT_DIRS` 和 `REPORT_DIRS` 保留旧冒号分隔方式。升级旧收集缓存后使用全新输出目录。

## 使用项目的集成规则

协作 skill 定义共享独立性原则；文档 skill 将其应用到 README、DEVELOPMENT.md 和 AGENTS.md。每个面向项目的 skill 也包含简短领域边界，使独立安装不依赖通用插件。路由 agent 提示词与所属 skill 保持一致。

审查时同时核对边界两侧：使用设备锁、模拟器、报告查看器或远程测试环境，不应向项目写入 AI 插件路径或参数；必需 Gradle 插件、Appium 扩展和报告库仍须声明。明确要求的 AI 插件集成，以及插件自身仓库，可以记录对应实现文档。先独立验证可移植 skill，再重新生成两个客户端，验证复制指令、清单、路由及包资源。不为此纯文档规则添加措辞匹配测试。

文档维护语言优先遵循用户明确要求；修改已有文档时沿用其主要语言，新建时默认使用当前对话语言。保留多语言分工，翻译采用自然技术表达并保留条件、限制和要求强度。相应规则由 `project-docs-and-rules` 与文档维护 agent 共同维护。

## 插件规则审计

审计将规则、agent 提示词、示例及 README 声明，与所属运行时、配置默认值、可移植清单和客户端生成逻辑比较。可配置默认值或有限只读探测不自动等于过时技术限制。保留真实归属、协议和资源约束。

| 插件 | 已确认发现与结果行为 |
| --- | --- |
| qemu-guests | 两平台默认均为 128 端口（20000–20127）。显式更大端口池仍受支持，无数量上限。批量注册、实际 bind 和 nofile 失败、Docker 缓存预设、不重叠出站端口和生命周期租约仍然必要。授权措辞遵循已有请求。 |
| android-emulator-profile | 移除全局 AVD 锁删除、无条件 ADB 关闭和强制 DISPLAY 回退。单 AVD 启动 guard 保护配置；原生锁需检查。已有或自定义 userdata 调整需要明确擦除许可；新 AVD 在首次数据创建前设置大小。配置不再使用 eval。AVD 名称精确匹配，arm64 作为架构别名。SDK 下载使用临时存储、保留替换工具并遵循已有归属。 |
| android-device-lock | 单靠原子 mkdir 无法串行化过期接管或令牌读取与删除竞态。设备 guard 现覆盖全部修改和原子元数据发布。随包 JSON 模板通过共享元数据工具渲染明确 JSON 编码的占位值。严格 JSON、类型检查拒绝损坏、不完整、重复键或非有限记录；引号和控制字符经 Python 3 完整往返。未知元数据和中断 guard 保留，超时输出不含令牌。远程删除失败保留恢复令牌，使 release、run 失败，同时不覆盖已有命令失败。固定租约要求有限命令或手动续租，所有参与者使用相同 guard 工具版本。 |
| diff-sharing | ngrok 缺失或认证失败时，文档所述本地回退现可执行。验证 Python 3 别名，显式绑定回环，支持仅本地预览，取消只清理自有子进程。修正 agent 错误的站点生成器文件名。 |
| test-report-sharing | 同样修正服务、认证和生命周期；文档中的目录别名现可用。XML 复制创建目标、保留不同路径的同名文件，只统计成功复制。先处理父 HTML 根目录，避免重复复制；输出不能递归收集自身。站点链接嵌套 XML。 |
| client-ui-best-practices | Kotlin、Swift 示例保留取消并拒绝被取代的完成结果。串行执行器、actor 不会让跨挂起点的整个请求串行化，React 有相同异步顺序要求。明确可移植与客户端路由措辞。 |
| recyclerview-best-practice | 状态和副作用归属与共享 Host 规则一致。哨兵改变差异位置，但屏幕外时不保证插入可见或锚定。Paging 页眉需要 ConcatAdapter 或 insertHeaderItem，仅映射不够。 |
| kotlin-coding-practices | 协程失败转换时显式重新抛出 CancellationException。结构化并发、不可变快照、密封状态变体及小型平台互操作边界仍适用。 |
| general-coding-practices | 审查两个 skill 和文档 agent。README、DEVELOPMENT、AGENTS 权威分工、根因诊断、聚焦验证及隐私规则仍有效，无需为形式删除规则。 |

集成指引已区分 ADB 服务与模拟器具体端点，在添加 Windows 端口代理前检查 gvproxy 已有宿主路由，不再一概要求重启共享 IP Helper。引用当前 [Android 命令行指引](https://developer.android.com/studio/run/emulator-commandline)，但不自动取代显式配置流程。SDK、镜像和包固定版本是环境选择，不是容量上限，也不声称每个已安装版本接受相同参数。状态限制仍是有限只读 I/O 和显示预算。Claude 路由仍从扩展生成，Codex skill 仍原样复制可移植源码。

聚焦审计回归：

```bash
python plugins/qemu-guests/tests/test-port-ranges.py
python plugins/android-device-lock/tests/test-device-lock.py
python plugins/android-emulator-profile/tests/test-start-avd-docker.py
python plugins/android-emulator-profile/tests/test-install-sdk.py
bash plugins/test-report-sharing/tests/test-collect-test-results.sh
python3 tests/test-report-launchers.py
python3 tests/test-validation-workflow.py
```

设备和 SDK、模拟器夹具使用模拟命令及私有临时文件，不能证明真实设备行为、原生 SDK 安装、macOS 或 arm64 执行，以及公开 ngrok 认证。启动器测试使用真实回环 HTTP、模拟 ngrok 失败及运行中隧道，检查响应和自有进程清理。纯提示词变更检查源码与包完整性，并按 API 语义审查，不声称验证模型行为或 Kotlin、Swift 编译应用结果。共享真机、虚拟机磁盘或镜像及已有报告服务不在这些夹具范围。

运行 `bash scripts/build-claude-plugin-package.sh --all` 和 `bash scripts/build-codex-plugin-package.sh --all`，生成相邻目录。先检查已有相邻检出目录：生成的 `plugins/`、市场目录和 README 会替换，无关文件保留。不在本地提交或推送生成仓库。

运行 `python scripts/validate-plugin-packages.py --client claude ../me.claude`、`python scripts/validate-plugin-packages.py --client codex ../me.codex`、`python tests/test-build-plugin-cli.py` 和 `python tests/test-plugin-packages.py`。Python 测试覆盖生成内容、路由、重新生成、清理和路径保护；CLI 套件覆盖两个客户端入口、帮助、参数和分派。验证依赖见 `scripts/requirements-validation.txt`。

同步工作流需要对两个已有目标仓库具备写入及 PR 权限的 `UPSTREAM_GITHUB_TOKEN`。它为各客户端创建独立生成 PR；目标 PR 合并后用户才能收到更新。同步插件更新发布并安装后，开启新的 Codex 对话。

同步 PR 标题包含源提交主题。`scripts/render-sync-pr.py` 使用共享 `scripts/templates/sync-pr.md.template` 渲染受影响插件版本（含移除）、生成差异统计、已完成客户端检查，以及源码和运行链接。工作流刷新已有 PR 的标题和正文。渲染器在生成同步提交后运行，与该提交父版本比较。

## 代码设计 skill 分工

原 Kotlin 插件并入 `general-coding-practices`，其 `code-design-rules` 入口定义与语言无关的控制流、状态和并发不变量。单次回调适配器必须只结算一次并清理；重复监听器使用有明确管理者的流，规定缓冲和终止行为。

原生 API、状态示例、取消差异、文档术语和平台测试指引放在 `references/`。入口链接各支持平台，插件 README 和平台元数据保持一致。Kotlin 插件及 skill 标识停用；生成市场清理旧包，并在两客户端加入新 skill。单独验证源 frontmatter，通过上述发行检查核对全部参考资源和原样复制的 Codex skill。提示词检查不证明应用或模型行为。

## 持续集成

两个验证工作流在每个 PR、推送到 `main` 及手动触发时运行。`validate-client-packages.yml`（Validate client packages）验证全部可移植源码和 Codex、Claude 发行包；`test-plugins.yml`（Test plugins）运行插件运行时套件，并检查每个套件已接入 CI。二者使用不同并发组，共同覆盖：

- 全部八个可移植插件和两个客户端发行包，包括纯提示词插件、skill frontmatter、agent 路由、资源完整性、重新生成、CLI 行为及生成 Codex skill 检查。
- `diff-sharing`、`test-report-sharing` 在独立矩阵作业运行的 Shell 套件。
- Android 状态 UI、后端、浏览器检查和模拟器启动回归。
- QEMU 状态 UI、后端、浏览器检查和虚拟机 Shell 回归。
- Windows Git Bash 配合独立 MSYS2、xorriso，检查备用 PATH 顺序和代理环境向子 Bash 传递。
- Docker 代理 Go 竞态检测测试。
- 非特权 QEMU 容器运行时冒烟。

Python、npm、uv、Go、Playwright Chromium 和 Docker 构建层使用 Actions 缓存。即使 Chromium 已缓存，全新 runner 仍安装浏览器系统依赖。包检查独立于运行时作业只运行一次。新可执行插件必须在 `test-plugins.yml` 添加运行时套件；所有插件清单和可移植提示词自动纳入包验证。提示词检查验证打包和结构，不验证模型行为。

CI 变化时运行 `python tests/test-validation-workflow.py` 检查运行时套件覆盖。

Shell 套件通过 `bash plugins/<plugin>/tests/test-*.sh` 逐文件运行；UI 套件在 UI 目录运行 `npm ci`、`npm run build` 和 `npm test`；浏览器及后端通过 `uv run --script <test.py>`。代理在 `plugins/qemu-guests/scripts/docker-proxy` 运行 `go test -race ./...`。容器作业需要 Docker 和 Linux 运行时，构建与执行命令见工作流步骤。

## Shell 边界回归测试

复杂 Shell 回归驱动现使用 Python `unittest`。从 `me` 源码检出目录运行，需要 Python 3.10+ 和 PATH 中的 Bash（Windows 使用 Git Bash）。`BASH_TEST_BINARY` 可指定 Bash 可执行文件。包套件还需 `python -m pip install -r scripts/requirements-validation.txt`。例如 `python plugins/qemu-guests/tests/test-port-ranges.py -v` 运行一个套件；追加类名或测试名可选择单项约定。这些开发测试依赖仓库级辅助工具，不是独立安装后的插件命令。

`tests/shell_test_support.py` 管理私有临时目录、可执行命令夹具和有限子进程等待。复用仓库 `scripts/process-runtime/command_tree.py`，在成功和失败后停止夹具后代进程：Unix 使用进程组，Windows 使用 Job Object。选择当前运行的 Python 解释器，不使用 Windows `python3` 应用别名。各插件 `tests/fixtures/` 模拟外部命令，不实现生产控制器或复制客户机模板。夹具通过原生控制器传递 Bash 命令时，传所选 Shell 的绝对 `$BASH` 路径。即使外层夹具运行在 Git Bash，裸 `bash` 仍可能解析到 Windows 系统 WSL 启动器。

| 已迁移套件（通过 `python` 运行） | 保留的约定 |
| --- | --- |
| `plugins/android-emulator-profile/tests/test-install-sdk.py` | 项目归档保留、不使用 sudo、复用更新工具、升级备份 |
| `plugins/android-emulator-profile/tests/test-start-avd-docker.py` | 真实配置、创建和启动 Shell 桥接，精确 AVD 名称，拒绝锁冲突和未授权擦除，配置与 argv 传递，首次启动和调整大小幂等性，Unix 取消 |
| `plugins/android-device-lock/tests/test-device-lock.py` | 通过模拟 adb 执行真实 CLI 和远程模板：过期租约竞态、错误归属、续租、无效 JSON 或类型、发布失败、控制字符、命令状态与恢复令牌 |
| `plugins/qemu-guests/tests/test-apk-mirror-selection.py` | 自动和手动选择、HTTPS 验证、回退及无效输入 |
| `plugins/qemu-guests/tests/test-port-ranges.py` | 平台、默认与显式边界，冲突，出站分离，渲染客户机监督器启动和恢复失败，seed 清理和信号清理 |
| `plugins/qemu-guests/tests/test-sync-workspace.py` | 真实归档过滤和暂存传输，拒绝不安全目标和缺失源 |
| `plugins/qemu-guests/tests/test-build-docker-proxy.py` | bootstrap 与交叉编译，失败构建或下载保留，暂存清理，跨虚拟机及输出根目录全局串行化，默认存储，超时、取消和拒绝陈旧归属 |
| `plugins/qemu-guests/tests/test-vm-utils.py` | 模板渲染，Shell 配置、工具及加速边界，回调 guard，锁竞态，停止保护和 SSH 密钥恢复；已有源码接线检查仍单独标记 |
| `tests/test-build-plugin-cli.py` | 两客户端启动器的帮助、无效参数、默认分派和输出覆盖 |
| `tests/test-plugin-packages.py` | 独立报告的完整性、重新生成、不安全路径、无效路由和开发产物排除 |
| `tests/test-report-launchers.py` | 六个独立插件及模式场景，保留各服务的启动、发布和取消生命周期；可选插件名过滤仍可用 |

原生 `test-controller.py`、`test-profile-controller.py`、`test-vm-state.py`、`test-vm-transitions.py` 和 `test-vm-shell-handoff.py` 继续负责直接控制器及状态机测试。迁移套件测试真实 Shell 入口和远程模板，不再添加仅 mock 的算法副本。反向虚拟机端口范围断言由端口边界矩阵覆盖，不在工具套件重复。参数输入使用 `subTest`；独立操作使用独立测试方法。清理失败后用令牌恢复等有依赖流程保留在一起。

Linux CI 保留这些运行时入口，Windows CI 也运行八个插件 Shell 边界套件。Git Bash 不能向原生 Windows Python 发送平滑信号，因此 AVD Unix 信号场景在 Windows 跳过，由已有原生配置套件验证 Ctrl+Break。`test-msys2-path.sh`、`test-linux-testcontainers.sh`、`test-container-runtime.sh`、报告插件小型 Shell 兼容检查及 Go、Node 测试保留各自平台和运行时约定。迁移 Shell 套件不需要真机、真实虚拟机或外部网络；启动器集成绑定私有回环端口并模拟 ngrok。

## 设备租约控制器

`android-device-lock/scripts/adb-device-lock.py` 管理宿主机租约操作。Shell 入口选择 Python 3.10+；`lock-metadata.py` 仍是可导入的严格元数据验证器，并保留兼容命令入口。设备修改继续通过远程 mkdir guard 串行执行。归属令牌在元数据发布前持久化，远程删除失败时保留。

运行 `python plugins/android-device-lock/tests/test-device-lock.py` 测试模拟设备竞态与失败，运行 `python plugins/android-device-lock/tests/test-controller.py` 测试原生控制器及取消，不代表真实设备验证结果。

命令管理使用带启动门的 Windows Job Object：包装器加入 job 后用户代码才开始。清理终止 job 并等待活动进程数为零。Unix 即使根进程已退出也向进程组发送信号。清理错误保留设备租约。原生控制器测试覆盖抗信号后代、正常根进程退出、清理失败及 Python、Bash shebang 参数转发，在 Linux 和 Windows CI 均运行。Windows job 语义遵循 [Job Objects API](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)。

`command_tree.py` 管理各平台命令生命周期，`command-worker.py` 是带启动门的 Windows 入口。租约控制器只启动、等待并停止该管理者，确认清理后才释放。清理期间暂时屏蔽取消处理器，随后恢复。

## 虚拟机生命周期与状态控制器

`vm-state.py` 管理状态 guard、操作令牌、单例预留和原子身份、PID 发布。`lib/vm-state.sh` 是安装和客户端兼容外观层。通用 Shell 回调通过令牌校验的 Python guard 获取和释放；回调失败或收到信号仍释放 guard。

`vm_phase.py` 定义不可变生命周期快照、进程证据变体和合法转换。`vm_lifecycle.py` 管理启动、停止、就绪及失败清理；`vm-lifecycle-step.sh` 保留平台、客户机规划和客户机探测。原生 QEMU 创建与句柄发布由 Python 负责，只有旧安装路径仍需 Bash PID 映射。Python 直接管理并等待原生 gvproxy 控制器子进程；辅助工具仍验证可执行文件和创建时间。安装保持分阶段 Shell 编排，每次 QEMU 启动前标记创建不确定，使用相同 Python 注册和终止路径。原生 Windows 启动器 PID 带显式标记，不按 MSYS PID 解释。身份检查未知与已确认不存在或无关 QEMU 进程返回不同失败状态。

运行 `python plugins/qemu-guests/tests/test-vm-state.py`、已有 `test-vm-utils.py` Shell 边界套件、`python plugins/qemu-guests/tests/test-vm-transitions.py`，以及需要真实 QEMU、并将 `GVPROXY_BINARY` 指向已验证工具的 `test-vm-lifecycle.py`。生命周期夹具使用私有状态、mock 客户机 I/O 和不被改动的合成磁盘；Windows 在新进程组启动原生 Python，并测试 Ctrl+Break 清理。不安装真实客户机，不查看或停止其他虚拟机。已有 gvproxy 控制器和生命周期测试仍适用。

虚拟机客户端夹具保持 QEMU 探测 mock，在向 PATH 添加模拟命令前，将 `QEMU_STATE_PYTHON` 指向真实解释器。这会真实执行操作租约获取、释放，而非连状态控制器一同模拟。

`test-vm-state.py` 还在身份及两个 PID 发布边界注入失败、模拟清理失败，并用合成进程身份执行后续停止恢复。检查未知或不完整发布、拒绝跨虚拟机接管和 PID 复用，不向真实进程发信号。配置回归用真实 Bash 描述适配器和私有状态，覆盖配置优先级、环境隔离、默认值、SSH 就绪及平滑、强制停止。

状态管理者在修改前解析持久进程证据和兼容 PID、身份文件。`run/active-vm.lock/lifecycle.json` 是包含预留代次、阶段和带标签进程证据的单个原子快照。原生身份先在该处发布，再发布旧 `.qemu.json`、`.pid` 指针；兼容发布不完整不能抹掉归属。没有快照的旧预留保留谨慎的旧身份、PID 恢复。代次不匹配会拒绝过时发布和清理。操作租约令牌串行化整个命令；虚拟机或未知启动仍存在时，持久预留比命令存活更久。即使没有虚拟机锁，已有辅助进程或控制器也会阻止获取。

| 阶段 | QEMU 证据与归属 | 取消或失败 |
| --- | --- | --- |
| 无预留 | 本命令不管理资源 | 只释放自己的操作租约；幂等健康检查失败后绝不清理已有虚拟机。 |
| `reserved` | 本代次持有全局预留，尚无新 QEMU | 只清理本操作资源，再释放预留。 |
| `network-starting`、`network-ready` | 尚无 QEMU；原生网络控制器必须先退出，才能继续清理 | 取消或等待控制器，停止其自有辅助进程，再释放。无法确认控制器退出时保留操作租约，阻止迟到发布。日志及预检 I/O 在进程创建前完成。 |
| `spawning` | 创建结果可能未知 | 将已处理信号推迟至句柄赋值或明确 `Popen` 失败回滚之后。已知创建失败回到 `network-ready`；强制终止或中断导致未知启动时保持预留。 |
| `launched` | 原生或旧 Shell PID 已在身份检查前持久化 | 验证原生可执行文件和创建时间。失败或身份未知时保留辅助进程和预留；已验证进程可以停止。 |
| `registered` | 不可变原生身份已持久化，兼容指针可能不完整 | 停止已验证 QEMU，等待本命令适配器结束，再停止网络并清除归属。 |
| `ready` | 就绪已提交，后台虚拟机管理其预留 | 这是启动完成边界；之后取消不撤销已提交虚拟机。 |
| `stopping` | 关机期间保留相同进程证据 | 平滑或强制停止被取消时保留归属，供后续停止继续；确认 QEMU 退出及辅助进程、控制器清理后才释放。 |
| `recovery-required` | 启动清理失败后保留最后进程证据 | 后续有归属的停止可重试。创建或检查未知、清理失败均需要检查，不按锁年龄删除。 |

成功清理移除预留，即终态停止。安装清理使用 `keep-lock` 时，则回到 `reserved` 供验证启动。嵌套状态 guard 修改（含 teardown）推迟而非丢弃信号；获取和创建完成有限归属发布后才交付取消。就绪和辅助网络 I/O 绝不在状态 guard 内执行。只在最终清理期间忽略额外信号，之后恢复处理器。

`resource_ownership.py` 为虚拟机状态、QEMU 启动和 gvproxy 控制器提供相同嵌套取消边界。获取前建立清理作用域；句柄赋值或明确创建失败回滚完成后，才交付已处理信号。向本调用创建的 guard 写元数据失败时，移除该新 guard，让后续操作可重试；绝不以此回收已有 guard。辅助控制器在创建、身份发布和就绪期间持有独占预留；身份发布前取消，也要先终止并等待进程句柄，再移除待定记录。终止失败或有限等待超时，保留待定或已发布证据供检查。网络就绪在边界外保持可取消。

`test-vm-transitions.py` 检查完整合法及非法阶段矩阵、证据验证、代次替换、租约和 guard 获取、spawn、READY 边界取消、日志打开及明确创建失败、每个原子发布边界、失败清理及重试、停止取消和借用虚拟机或辅助进程保护。使用合成进程及私有状态。真实生命周期夹具还在启动隔离真实辅助进程后使日志打开失败，并在 QEMU 创建前的私有夹具屏障取消原生控制器；检查完整清理后，执行正常启动、停止和取消，不打开合成磁盘。

`test-gvproxy-control.py` 在创建真实私有子进程后、返回句柄前，确定性地交付各支持信号，断言子进程在归属消失前退出，并覆盖创建失败、清理中重复取消、终止或等待失败及已有 guard 保护。状态套件在每次初始 guard 元数据写入前后注入失败，检查回滚、重试并保留已有未知 guard。原 guard 泄漏和创建窗口孤儿问题在旧代码上均无法通过这些测试。

Shell 归属使用调用者生成的令牌和预先安装、校验令牌的清理。内部 `vm-state.py begin` 与 `guard-acquire` CLI 要求 `--token`；`new-token` 不获取资源。`publish_claim` 在创建和本地归属赋值期间推迟取消，元数据发布或刷新输出失败时回滚自己的归属。Shell 在创建前就知道令牌，因此交付失败或创建者随后非零退出不会丢失清理能力。guard 回滚幂等且校验归属、令牌，不移除其他调用者或未知 guard。

`claim_vm_state` 等待 exec 后的原生创建者时，临时记录已处理 Shell 信号；即使 `wait` 被中断，也等待该进程结束，恢复调用者 trap 后报告取消。回滚不能先于仍可能发布的创建者。`begin_vm_operation keep-traps` 保留已有构建清理；获取失败也先回滚，再返回错误处理调用者。此协议覆盖可处理取消和已知错误；强制终止及未确认清理仍需检查。已持有归属的 Shell 嵌套获取，会在改变令牌或 trap 前被拒绝；其他失败请求恢复调用者原上下文。

运行 `python plugins/qemu-guests/tests/test-vm-shell-handoff.py`，在私有状态上执行真实 CLI 到 Bash 测试。夹具解释器在元数据和输出边界注入取消、输出失败，以及发布后非零退出。独立屏障将创建停在发布前后；Shell trap 标记证明信号已交付，再允许创建者结束。测试覆盖两类资源、正常和自定义 trap、回滚与重试，以及已有未知归属保留。

## 模拟器配置控制器

`profile_controller.py` 负责字面配置解码、工具查找、参数映射和原子 INI 替换。配置保留在字典或 Shell 关联映射中，与继承进程环境分离。只向工具转发明确的 Android 路径和显示约定。`start-avd.py` 管理单 AVD guard 和模拟器进程。Shell 安装编排只使用内部 `profile`、`tool`、`args` 桥接模式，不使用 eval。AVD 路径解析和 INI 读写由原生启动控制器直接调用。Windows 原生等待有限，让 Ctrl+Break 能进入清理；只终止自有进程树。

运行已有模拟 SDK、模拟器 Python Shell 边界套件及 `python plugins/android-emulator-profile/tests/test-profile-controller.py`。原生测试覆盖空格和 Unicode 路径、CRLF、拒绝展开、参数、重复键、原生锁、竞争、失败和取消，以及忽略继承配置与擦除权限、拒绝批处理末尾反斜杠。Windows 和 Unix 均运行原生套件。Git Bash 冒烟的 Windows 信号覆盖交由该原生测试。

## QEMU 配置边界

共享 `lib/config.sh` 解析器先暂存字面值，再发布新的文件配置。固定支持键命名空间会清除继承或陈旧虚拟机设置，移除导出属性。Shell 使用者读取普通配置值，生命周期适配器显式接收配置路径。宿主工具、路径和解释器控制项留在配置命名空间外。Alpine ISO 默认值在配置加载后的使用时解析。客户机和测试环境仍只接收明确命令约定。

`test-vm-state.py` 检查继承生命周期设置被忽略、必需值缺失、子环境隔离、连续加载和宿主设置保护。合成生命周期夹具在配置中设置就绪超时。

## 作用域命令管理与报告发布

作用域命令运行时权威源码在 `scripts/process-runtime/`。修改后运行 `python scripts/sync-process-runtime.py`；`--check` 验证模拟器和两个报告插件中的随包副本。CLI 主线程创建交接推迟取消，直到句柄已归属。Windows 使用带启动门的 worker，在用户代码运行前加入关闭即终止的 Job Object；停止等待活动进程数为零。Unix 在根进程退出后仍清理整个进程组；命令不得 daemonize 或将 worker 脱离。持久 QEMU 服务使用已有阶段、代次和身份管理者，不使用作用域退出即终止抽象。

`AvdSession` 管理配置串行化及命令作用域，清理失败保留 guard。QEMU 普通启动直接从 Shell 计划生成原生 argv，持久化带类型的原生启动证据，就绪前注册已验证进程。原生启动变体和结构化待定 PID 记录区分原生与旧 Shell PID，无需旁路标志文件。旧 Shell PID 保留转换路径；未知启动或身份失败仍阻止接管，并保留恢复信息。

两个报告插件均在私有相邻暂存目录构建完整站点，重命名为 `generations/<id>`，再原子替换 `current.json`。指针是发布边界。替换前失败保留旧站点；中断发布可能留下未引用的完整代次或相邻 `.building-*` 目录。手动移除前确认生成器已停止。站点组装复用完整不可变站点；旧平面缓存只物化发布一次。链接的资源文件和目录物化到快照；目录循环会中止构建，不替换旧版。不编辑或自动删除已发布代次。HTTP 根重定向到当前代次 URL，使各页面相对资源在另一构建发布时仍固定。迁移期间无指针的平面缓存仍可读取。自动使用者读取报告前先解析 `current.json`；摘要报告路径相对于其代次。服务和读取者停止后才清理专用缓存，没有自动保留策略。

运行 `python tests/test-report-snapshots.py`、`python tests/test-report-python.py`、`python tests/test-report-launchers.py`，模拟器 `test-command-tree.py`、`test-profile-controller.py`，以及 QEMU `test-vm-state.py`、`test-vm-transitions.py`。测试覆盖发布失败、重叠构建、幂等收集、旧资源 URL、无效引用、渲染器失败、取消交接和原生 PID 恢复。原生套件也在 Windows CI 运行。QEMU 生命周期夹具使用真实原生 QEMU、gvproxy 和私有状态，mock 客户机 I/O，不使用客户机磁盘。

通用代码指引现优先修正资源归属、生命周期、状态和接口结构，再考虑补偿补丁，同时为崩溃、不确定外部效果和部分发布保留证据及明确恢复。

Windows Android 工具环境在应用配置覆盖后，规范化三个 Android 目录变量。原生回归将含空格和 Unicode 的 Git Bash 路径直接传给 Python 子进程，覆盖继承值、配置覆盖、原生路径及空值。

### 真实 Alpine 客户机验收

`plugins/qemu-guests/tests/validate-guest-testcontainers.py` 是可选真实客户机检查，与确定性模拟进程 CI 套件分开。为新安装的隔离虚拟机构建 CLI 代理后，通过插件 Testcontainers 包装器运行。验证 cgroup v2 CPU 配额、内存限制、无 swap 下实际 OOM 强制执行、映射 HTTP 就绪、活动 Ryuk 和工作负载移除。安装回归拒绝 `cgroupfs-mount`，保留 OpenRC `cgroups` 服务；真实安装确认该服务由 Alpine 提供，不断言外部包名。

`setup-disk` 安装持久根文件系统时，系统安装使用 Alpine `lbu` 归档。`setup-alpine` 前，通过 `lbu include` 注册受监督 Docker 包装器；若可执行文件只存在于 live ISO 的 `/usr/local`，重启后将不存在。真实新磁盘验证必须检查持久 OpenRC 配置和它引用的可执行文件。

Windows CI 也验证默认 ANSI 的 Python 文本 I/O。Git Bash 路径转换和生成 UTF-8 报告产物必须显式指定编码；不依赖宿主 locale，也不靠启用 UTF-8 模式掩盖缺失边界。原生路径回归在转换真实 Unicode 路径时模拟 CP1252。

测试环境协议 CI 矩阵在 Linux、Windows 运行安装、不可变快照、传输清理、取消和 worker 归属回归。夹具使用模拟进程，不启动已有虚拟机；Node 测试还验证客户机 Appium 启动器和 macOS 自动登录工具。
