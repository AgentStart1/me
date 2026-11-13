# QEMU 客户机

需要运行桌面应用测试、在不同于当前宿主机的环境测试，或准备 Docker 测试环境（含 Testcontainers）时，使用本 skill。请求可以直接描述测试目标，例如“运行桌面测试”“从这台 Windows 宿主机测试应用的 Linux 版本”或“为集成测试准备 Docker”，无需点名 QEMU、Appium 或安装流程。

skill 在内部选择、协调所需环境，优先复用合适的已有配置。测试同时需要桌面和 Docker 时，可组合桌面客户机与独立 Docker 后端。启用 skill 不意味着创建虚拟机，明确目标要求始终优先。普通宿主机本地单元测试和无关 Docker 工作不在此入口范围；明确管理、查看已有 QEMU 测试环境状态和屏幕仍受支持。

[skill 入口](skills/qemu-guests/SKILL.md)集中说明环境选择、共享执行规则和只读状态指引；仅在需要时加载工作客户机准备、macOS、宿主机驱动测试、Alpine 操作与配置、插件维护等参考。普通测试复用合适环境，新安装验证使用隔离资源。Alpine 自动加速回退及真实 Go 代理构建属于后端专用行为，不放宽工作客户机加速器或构建位置规则。

本插件在 Linux 容器和 Windows 上并发运行 QEMU 工作虚拟机，同时保留一个持久 Alpine Linux Docker 后端。工作客户机拥有独立磁盘和无人值守安装介质，是带 Appium 的独立测试环境，宿主测试运行器经 SSH 连接。Alpine 后端独立为宿主机 Docker、Testcontainers 提供服务。

普通 Linux 宿主机上的纯 Docker 流程直接使用 Docker。安装了 QEMU 和 Python 的 Linux 宿主机也可运行工作客户机监督器。

## 使用项目的独立性

使用插件的项目通过标准 Docker、Appium 端点及可移植产物和服务配置工作，不依赖本 AI 插件启动器安装路径或私有虚拟机配置。正常 Appium 驱动或扩展、Gradle 插件和其他必要项目依赖仍是应记录的前提；操作者配置留在项目外。

## 并发工作虚拟机

插件已从 `qemu-alpine-docker` 重命名为 `qemu-guests`。客户端发行包发布后安装新名称。已有 Alpine 磁盘和密钥有意保留在 `~/.qemu-alpine-docker`；`QEMU_ALPINE_BASE_DIR` 仍用于覆盖后端存储位置。重命名不移动或重建磁盘。VM & Containers 面板同时显示后端及已注册工作虚拟机，并为运行中的图形客户机提供实时只读屏幕。

| 客户机 | 无人值守安装 | 要求 |
| --- | --- | --- |
| Ubuntu | 官方 cloud 镜像、NoCloud seed、SSH 和 Appium bootstrap | 已校验 amd64 cloud-init qcow2 镜像 |
| Windows | 随包 Autounattend.xml 和 PowerShell bootstrap | 英文 amd64、兼容 BIOS 的 ISO，匹配镜像版本，可用 Windows OpenSSH 可选功能 |
| macOS | Recovery 终端自动化、`startosinstall`、首次启动 product package 和 Appium LaunchAgent | 已准备英文 Intel macOS 安装 ISO、匹配固件和 OpenCore 硬件、宿主 Tesseract，以及在 macOS 构建的 bootstrap product package |
| 其他 | 自定义 seed 和 QEMU 安装参数 | 对应系统的无人值守安装器和 bootstrap |

Windows 模板使用 BIOS/MBR、IDE 存储和 e1000 网卡，面向兼容的 Windows 10、Server 介质；不包含原版 Windows 11 TPM/UEFI 或 arm64 安装器。其他固件、驱动或安装需求使用自定义适配器。内置 macOS 流程面向支持 `startosinstall --volume --installpackage` 的 Intel Recovery 安装器；Apple Silicon IPSW 恢复属于独立流程。

Windows 示例默认四 vCPU 和 `qemu_runtime: "whpx-reset"`。Windows 11 x64 上，`install`、`run` 在启动客户机前构建或验证插件管理的 QEMU 11.1.2。此运行时只含 WHPX，使用 `Westmere,-vmx,-svm`；构建或加速器失败即终止，不回退 TCG。安装在同一 QEMU 进程中使用客户机热重启。`plan`、`status`、`stop` 从不触发构建。Ubuntu 示例也显式选择 WHPX；Linux 上选择 `qemu_runtime: "system"` 和 KVM。

受管构建需要 MSYS2 UCRT64 和 Python 3.12+。构建器在 `~/msys2` 或 `C:/msys64` 查找 MSYS2，其他位置通过宿主控制项 `QEMU_MSYS2_ROOT` 指定。首次构建安装必需 MSYS2 编译包，下载并验证固定版本源码，应用随包重置及 CET/XSAVE 补丁，将可执行文件、依赖 DLL 和固件打包到 `~/.cache/me/qemu-whpx/<version-recipe>/runtime`。每次构建在选择缓存前冻结模板、有序补丁和源码元数据；后续源码修改用于下一次调用，当前构建保留捕获输入。绝不覆盖系统 QEMU。创建磁盘仍需要已有 `qemu-img`。源码、日志和失败构建工作区保留在缓存供检查。构建中断后，移除 `build.lock` 前检查该锁及遗留编译器进程。

可在客户机安装前提前准备运行时：

```powershell
python scripts/whpx_runtime.py
```

普通 Windows 配置无需可执行路径或额外 DLL PATH，自动选择完整运行时，并在启动前校验所有缓存文件。显式 `qemu` 路径让已有配置继续使用系统或自定义运行时；`qemu_runtime: "system"` 可退出受管模式。不将 `whpx-reset` 与 `qemu` 覆盖或安装器冷启动预算组合。

使用 QEMU 11.1.2 及 `qemu_args: ["-accel", "whpx", "-cpu", "Westmere,-vmx,-svm"]` 时，四 vCPU 冷启动成功。未经修改的程序在客户机发起热重启时仍以 `Unexpected VP exit code 4` 失败。改为 Q35、UEFI 或屏蔽 x2APIC 没有解决实测故障。仅升级 QEMU 不足以证明兼容。

随包 [WHPX 分区重置补丁](patches/qemu-11.1.2-whpx-partition-reset.patch)改编自[上游提案](https://patchew.org/QEMU/20260421205749.55060-1-mohamed@unpredictable.fr/)，不属于原版发行。Windows 11 上四 vCPU Windows Server 2025 热重启通过；当前 Appium 模式也通过宿主机运行的桌面 E2E 场景。重启验收在每次重启后，于已有周期超时内等待认证后的 Appium 就绪；只有 SSH 就绪不够。见[构建与验证](DEVELOPMENT.md#whpx-四-vcpu-windows-重启)。重置 API 要求 x64 Windows 11；Windows 10 和修补后的 UEFI 安装未验证。

受管运行时还包含 [CET/XSAVE 能力修正](patches/qemu-11.1.2-whpx-cet-xsave.patch)。WHPX 宿主默认值不能启用所选客户机 CPU 模型排除或其 XSAVE/XSAVES 状态路径不支持的 CET 特性，避免向早于 XSAVE 的 Westmere 模型暴露影子栈。补丁变化选择新缓存，不触碰已有虚拟机进程和磁盘。

实验 CPUID 缓存运行时在 Windows 11 WHPX 上，以四 vCPU、4 GiB RAM 完成 Sonoma 14.8.9 安装。修复首次启动服务加载和 SSH 访问组成员关系后，桌面登录、SSH 版本及 CPU 检查、已注册 QMP 捕获通过，未做 Docker 验证。它使用私有 Recovery 适配器，不等于随包完整安装 ISO 流程的端到端验收。范围及限制见 DEVELOPMENT.md。受管 Windows 运行时保持不变。Recovery 键盘输入区分按下和释放，并在安装交接前等待 Shell 提示。

公开报告与这些症状相符：[QEMU #2042](https://gitlab.com/qemu-project/qemu/-/issues/2042)描述四 vCPU WHPX 重启失败，[#2402](https://gitlab.com/qemu-project/qemu/-/issues/2402)描述 Windows/UEFI 重启挂起。[qemu-virgl-whpx 项目](https://github.com/Tsuki-Bakery/qemu-virgl-whpx#Windows-guests)提供 Windows 启动示例，但也将重启失败列为限制。[dockur/windows](https://github.com/dockur/windows) 等 Linux KVM 配置可参考安装方式，不能作为 WHPX 重启修复证据。

仅旧系统运行时配置可通过 `install_reboots: 4` 显式允许 Windows 安装期间最多四次冷启动。QEMU 退出而不内部重置；验收前干净退出后，监督器以同一磁盘、seed 和加速器再次启动，优先磁盘而非安装介质。崩溃、停止请求、预算耗尽或原就绪截止时间到达会结束此流程。验收检查 bootstrap 和 Appium 就绪。受管运行时直接支持热重启，拒绝此选项。

每台工作虚拟机有独立 `state_dir`、qcow2 磁盘、监督租约和宿主 SSH 端口，可同时运行多台。分配不同宿主 SSH 端口，并与 Alpine 宿主转发不重叠。工作客户机不要求 Alpine，也不接收 Docker 代理、后端凭据或容器端口隧道。

### 统一测试环境入口

`bash scripts/run-test-env.sh --config /path/to/test-env.json -- <host command>` 组合 Docker、Testcontainers 配置与透明客户机 Appium 传输。旧 `run-testcontainers.sh` 保留为轻量兼容入口；`--profile <alpine.profile>` 保留原纯 Docker 行为、操作租约、CLI 代理、Ryuk、指标和命令退出码。

测试环境 JSON 与虚拟机安装 JSON 分开。`version: 1`、`workspace`、可选 `docker.profile`、可选 `appium` 和可选字符串 `environment` 值选择服务，不在插件内写项目专用代码。路径相对工作区解析，工作区相对配置目录解析。私有配置路径支持 `${VARIABLE}` 展开；变量未设置时在测试前失败。项目省略 `docker.profile` 或 `appium.guest` 时，操作者变量 `TEST_ENV_DOCKER_PROFILE`、`TEST_ENV_GUEST_PROFILE` 提供私有连接。未选择 Docker 时保持其现状。项目文档应描述端点要求和普通测试命令，不写 AI 插件安装路径或提供方专用设置。明确角色 schema 见 `profiles/test-env-windows.json`。

Windows 传输通过 SSH stdin 发送带 UTF-8/base64 帧的 PowerShell 脚本，使完整套件的远程命令参数保持有界。PowerShell 和原生命令失败保留退出状态。转发通道使用不启动远程 Shell 的 SSH，避免重复测试残留空闲客户机进程。新会话返回客户端前若输出收集失败，代理删除自有会话；清理不确定时保留客户机租约。

透明 Appium 适配器通过带引号 Java 参数文件支持 Windows 宿主到 Windows 客户机，以及 Windows、Linux 宿主到 Linux 客户机的 JVM 启动。编译完成后，在会话创建时传输更新的宿主构建 classpath 和 Java agent 产物。Windows 还暂存宿主 Java 运行时。Linux 使用已准备目标 JDK 和操作者运行时清单中显式预构建的原生 classpath 补充项，绝不把 Windows JDK 复制到 Linux。配置中的具名 JVM 属性声明私有输入、输出文件、必要目录、额外构建 `artifacts`（如诊断 agent JAR）和 HTTP、WebSocket 服务 URL。代理镜像这些文件，为回环服务创建已认证反向转发，并返回原 WebDriver 响应。会话创建返回前收集 PID 和输出文件；请求 page source 和会话关闭时也收集日志。私有客户机状态跨应用重启保留，只在宿主命令结束时于明确声明的逐用例清理根目录中移除。绝不运行客户机编译器，也不在传输失败时改用本地桌面。

运行器向宿主测试提供 `APPIUM_DESKTOP_SERVER_URL`。原生诊断位于 Appium 服务侧，经 Appium 返回结果；不在宿主机附加客户机 PID。客户端特定 Java 属性名只放在其项目配置。已有 Appium 窗口兼容扩展仍是项目前提。未实现对应适配器的其他宿主、客户机组合和启动格式明确失败。仅运行包装器不启动或创建虚拟机。

Linux 操作者将 `TEST_ENV_LINUX_RUNTIME` 指向私有 JSON，含绝对 POSIX `root`（专用产物镜像目录）、`java`（已有客户机 Java）、`classpath`（宿主预构建 Linux 原生及运行时 JAR 路径），以及可选 `appium_port`（默认 4723）。例如：

```json
{
  "root": "/home/tester/.local/share/test-environments/runtime",
  "java": "/usr/lib/jvm/java-21-openjdk-amd64/bin/java",
  "classpath": ["/operator/prebuilt/linux-native-runtime.jar"],
  "appium_port": 4727
}
```

按下文项目需求初始化隔离图形 Appium 会话。已有准备或自定义运行时，操作者在调用统一入口前提供所需 Linux 驱动、D-Bus、AT-SPI 和已解锁测试密钥环。中继将宿主路径及 JVM classpath 分隔符映射到专用 POSIX 镜像，转发声明的宿主服务，将输出收回原宿主路径。Windows 和 Linux 测试环境 JSON 使用同一 `java-argfile` schema，由客户机配置选择传输。项目只声明正常平台、产物和服务要求，不向使用插件的项目添加操作者清单路径或环境提供方指引。

### 自动桌面运行时初始化

项目可在环境 JSON 旁保留可移植 `version: 1` 桌面需求，由环境的 `requirements` 字段选择。需求文件含 `desktop` 宽高和 `platforms` 映射（`Windows`、`Linux`）：Java 主版本、Appium 服务版本、驱动和插件名称到版本的映射、可选 Linux 运行 `packages`、必需环境变量名及预构建 Maven `classpath` 坐标。不含虚拟机配置路径、SSH 密钥、加速器选择或 AI 插件入口。正常 Appium 扩展源码、依赖和运行需求归项目管理；预构建包与平台连接归操作者管理。

通过 `prepare-appium-runtime.py --base <offline-runtime.zip> --output <new-runtime.zip> --extension <prepared-extension-directory>` 叠加目标兼容的本地扩展，不在客户机执行 npm 或安装钩子。`--windows-desktop` 在 Windows 宿主编译显示工具。`--assets <private-assets.json>` 打包预构建目录、文件和服务环境值（`${RUNTIME}` 展开为已安装运行时）。`files` 条目含 `source` 和相对 `destination`；可选 `classpath` 将 Maven 坐标映射到随包 `assets/...` JAR。资源路径、产物缓存及环境值留在项目外。提供目标兼容、已准备依赖，不将宿主原生依赖树复制到不同客户机 OS。

准备运行时传 `--requirements <project-requirements.json> --platform windows|ubuntu`，运行声明的宿主准备钩子并检查完成包。再通过 `guest-vm.py install <private-guest.json> --requirements <project-requirements.json>` 安装。虚拟机配置描述硬件、介质、WHPX/KVM 和连接；桌面依赖来自项目需求。运行时元数据必须匹配客户机系统及 x64 架构（Windows win32、Ubuntu linux、Intel macOS darwin）。平台或架构缺失、不匹配均在创建磁盘前失败，包括无项目需求的安装。旧包缺架构元数据时，新准备或安装必须在宿主重建；普通运行、测试不会因此重新验证、重写或停止已安装虚拟机。带需求的宿主准备在执行钩子前拒绝异平台基础运行时。扩展、版本、原生产物或必需环境值缺失也在磁盘创建前失败。已有磁盘不重置，空盘验收用独立状态目录。

Ubuntu seed 只携带小型 cloud-init 文本，从只读 seed 介质解包离线载荷。运行包以发行版二进制安装。初始化创建隔离 Xvfb/Openbox 桌面、D-Bus/AT-SPI 会话、临时解锁原生密钥环和 Appium 服务；LightDM 自动登录也支持人工控制台。状态面板投射控制台帧缓冲，与隔离测试显示分开。Windows 使用持久自动登录账户，设置 100% DPI，在所选加速器下热重启，通过宿主构建程序集设置显示模式，在交互会话启动 Appium。不在客户机编译显示工具。

新受管客户机先验证 SSH 转发监听器归监督 QEMU 所有，再将 SSH 主机密钥固定在状态目录 `known_hosts`。后续传输和 Appium 连接使用该固定值。就绪轮询 cloud-init 状态不使用 `--wait`，遗弃 SSH 探测不能留下占内存的 cloud-init 等待者。Java、运行时检查及真实项目 E2E 与 Appium 服务就绪分别判断。

这样初始化的 Linux 客户机自动提供已有 `/usr/bin/java` 和随包原生 classpath 元数据。`TEST_ENV_LINUX_RUNTIME` 仍可作为已有准备或自定义环境的私有覆盖。统一宿主入口在测试前，将初始化指纹与项目需求核对。

### 项目配置钩子

无法声明式表达的依赖，可在各平台需求中使用 `hooks.host_prepare` 和 `hooks.guest_setup`。宿主条目包含 `command`（字面 argv 数组）、`cwd`（相对需求文件）和 `timeout_seconds`。客户机条目包含相对需求文件的自包含 `script` 路径、`interpreter`（`bash`、`powershell` 或预装 `python3`）、字面 `arguments` 和 `timeout_seconds`（1–3600）。宿主钩子在运行时准备期间、测试之前执行。客户机脚本复制到私有 seed 介质，在运行时解包后、Appium 启动前执行。Linux 配置以安装管理员运行，Windows 以安装测试管理员运行。客户机钩子收到 `TEST_DESKTOP_USER`、`TEST_RUNTIME_ASSETS` 作为不透明运行上下文；使用它们，不硬编码提供方用户名或安装路径。脚本必须前台运行并等待自己的工具，不支持脱离的安装器。

例如，Linux 平台条目可添加项目自有钩子（路径相对需求文件解析）：

```json
"hooks": {
  "host_prepare": [
    {"command": ["python3", "scripts/prepare-runtime.py"], "cwd": ".", "timeout_seconds": 600}
  ],
  "guest_setup": [
    {"script": "scripts/configure-runtime.sh", "interpreter": "bash", "arguments": ["--mode", "test"], "timeout_seconds": 120}
  ]
}
```

客户机钩子授权运行配置和预构建依赖安装，不授权客户机内编译。编译器和构建任务留在宿主钩子。执行前审查项目脚本，原始钩子日志私有保留，非零退出或超时即停止初始化。项目需求和客户机脚本只读取一次，形成不可变初始化快照。即使安装期间源文件被修改或删除，预检、seed 生成和记录的指纹都使用该快照；变更在下一次捕获生效。客户机脚本指纹包含有序文件标识及各自内容摘要；在脚本之间移动内容也会使初始化失效。指纹 v2 之前记录的客户机钩子环境，需要新的隔离初始化。已有 v2 输入不变时仍兼容；无客户机钩子的配置保留原指纹。已有虚拟机状态不自动重写。通用引擎不得含使用插件的项目包名、路径或测试命令。

### 取消与清理

配置式本地、纯 Docker 和客户机 Appium 运行遵循同一清理、取消行为。信号记录第一次取消请求，执行在显式检查点响应，不在任意指令中被打断。命令和 SSH 等待短间隔检查请求，启动 HTTP 就绪仍受 10 秒超时限制。清理开始后，后续信号不能中断清理或替换结果。已接受取消即使清理失败也保留信号退出码；干净执行保留宿主命令退出码，普通清理失败返回 1。不为发布结果重启命令或清理。即使 HTTP 将异常转换为错误响应，或后续重试成功，worker 清理失败仍保留。

主线程确认资源 worker 完成并收集报告后，才决定是否释放测试租约。CLI 只报告固定清理类别和数量，不含异常文本、参数、路径或凭据。客户机清理不确定时保留桌面测试租约并输出手动恢复提示；本地和纯 Docker 不获取客户机桌面租约。完全确认清理后释放租约，不输出清理警告。

### Appium 创建结果不确定

会话创建响应丢失、损坏或缺少有效会话 ID 时，中继阻止继续创建，并将客户机测试租约保留为 `cleanup-uncertain`。应用可能仍在运行，因此保留私有测试输入。环境管理者在每个资源清理失败边界持久记录保留要求，再清理其他资源。后续传输或临时目录错误不能释放该租约或掩盖保留状态。普通测试失败在全部自有资源成功关闭后仍释放租约。

SSH 传输即使某个停止失败，也尝试停止每条自有隧道，随后聚合报告并保留租约。清理失败时，取消仍是最终结果：环境管理者清理所有注册资源，重新抛出原取消，并附收集的清理错误。完全确认清理的取消正常释放租约。teardown 期间，将已处理取消信号推迟至全部清理结果和租约决定已提交；重复信号不能打断失败记录或锁保留，确认干净的 teardown 仍先释放租约再传播取消。关闭后的中继在迟到请求启动新工作前拒绝它们。创建请求在途时被中断也适用。

不要自动删除租约后重试：检查该客户机 Appium 会话、进程和私有测试诊断，确认相关应用、会话已停止，再只显式恢复该次运行租约。绝不批量删除无关 Appium 会话。已确认协议拒绝及远程请求前失败可普通清理。默认回归套件不启动 QEMU；原生多虚拟机冒烟要求显式 `QEMU_TEST_ACCEL` 启用，并另行运行。

### 构建与测试位置

工作虚拟机是运行和测试环境。除非用户明确要求客户机编译，否则应用、测试代码、原生依赖和安装钩子应在宿主机或已有指定构建环境编译，再传输构建产物与预构建依赖。安装客户机、配置 Appium 或运行测试不授权在工作虚拟机编译。不能悄悄回退客户机编译或扩充 CPU、内存容纳构建；应解决宿主构建前提或报告限制。工作虚拟机运行 Appium、应用和测试，普通运行时 JIT 不属于构建。

### 安装与运行

1. 安装介质制作支持：`python -m pip install -r scripts/requirements-guests.txt`。
2. 生成客户机访问密钥：`ssh-keygen -t ed25519 -f ~/.ssh/qemu-work`。
3. 在与目标客户机相同 OS、CPU 架构的环境准备离线 Appium 运行时。先使用独立官方 Node.js 发行及受支持 npm；链接私有外部库的发行版、Homebrew 可执行文件不是可移植客户机运行时。构建器固定 Appium 3.2.2，不在准备桌面启动应用。Windows 桌面测试示例：

   ```bash
   python scripts/build-appium-runtime.py /private/appium-windows.zip --driver appium-desktop-driver@2.8.0
   ```

   项目驱动重复指定 `--driver <pinned-npm-package>`，Appium 插件重复指定 `--plugin <pinned-npm-package>`（根据运行时元数据激活）；不需要驱动的 Appium 服务可省略。驱动前提、SDK、JDK 和应用产物归项目管理。Linux 本地驱动、macOS Xcode 和辅助功能权限需相应平台准备；仅装服务不能证明 UI 自动化可用。
4. 将示例 JSON 配置复制到检出目录外，提供厂商介质及已验证 SHA-256、客户机密钥、构建器生成的 `appium.runtime_archive`、`appium.sha256`。`appium.host_port` 为 SSH 隧道选择唯一宿主回环端口。路径相对配置解析，`~` 展开为宿主家目录。设置准确 Windows 镜像版本。seed 生成私有账户凭据。
5. 在独立终端检查计划并安装：

   ```bash
   python scripts/guest-vm.py plan /path/to/ubuntu.json
   python scripts/guest-vm.py install /path/to/ubuntu.json
   ```

   安装无人值守、前台受监督。`Guest ready` 表示验收成功：已认证 SSH、就绪客户机 Appium 服务，以及 Ubuntu cloud-init 完成。监督器在客户机整个生命周期持续运行。另一客户机在另一个终端启动。日志位于 `state_dir`。
6. 从另一终端查看或停止单台虚拟机，之后通过 `run` 重启：

   ```bash
   python scripts/guest-vm.py status /path/to/ubuntu.json
   python scripts/guest-vm.py stop /path/to/ubuntu.json
   python scripts/guest-vm.py run /path/to/ubuntu.json
   ```

   停止请求 ACPI 关机，监督终端报告完成。`stop --force` 只终止该会话已验证原生 QEMU。Ctrl+C 取消监督器并强制停止其自有 QEMU。监督器被强制终止时，移除保留锁或进程记录前检查所记录原生进程。

从独立终端连接宿主测试与客户机服务：

```bash
python scripts/connect-appium.py /path/to/windows.json
# Point your project's Appium client at http://127.0.0.1:<appium.host_port>
```

Appium 只监听客户机回环 4723。OpenSSH 认证并固定客户机主机密钥；首次连接从客户机控制台或其他可信通道验证指纹。隧道仅绑定宿主回环，拒绝占用端口，随管理进程结束。状态面板显示的配置端点需要此隧道。各客户机使用独立隧道和宿主端口。

Windows Appium 以专用测试用户在交互客户机会话运行，绝不在 SSH Session 0。该账户重启后自动登录。不要在可丢弃测试环境使用个人凭据。人工测试可使用独立配置的客户机控制台或远程桌面，状态屏幕仍只读。测试自行在客户机暂存应用和文件，并安排访问宿主、后端服务。只改 Appium URL 不会转换本地路径或回环 URL。插件不包含项目路径、应用或测试选择。

macOS 桌面自动化需要项目要求的 Mac2 驱动和兼容完整 Xcode，仅 Command Line Tools 不够。验证所提供 Xcode 归档的 Apple 签名，选择开发目录并完成许可及首次启动初始化。WebDriverAgentMac 需要在指定 macOS 构建环境准备，或明确例外授权在工作虚拟机构建。在专用测试账户给构建的 runner 和 Xcode Helper 授予辅助功能权限；重建可能使授权失效。验证真实会话、原生 source、截图和点击，服务就绪不等于 UI 验收。见 [Mac2 配置文档](https://appium.github.io/appium-mac2-driver/v4/getting-started/)。

有意拒绝含 `backend`、`proxy_binary` 的旧工作配置：移除这些键，添加 `appium`。已有磁盘绝不替换。Windows 将新渲染载荷复制到 `C:/ProgramData/qemu-guests`，运行 bootstrap 替换插件管理的 Docker 任务、环境和凭据。迁移旧盘时，使用已有账户刷新私有客户机自动登录密码。Ubuntu、macOS 操作者应用新 Appium bootstrap 前，移除旧插件管理的 Docker 隧道或服务、环境条目及后端密钥。创建新私有状态目录是完整无人值守路径。

seed 含生成的客户机账户凭据和 SSH 授权。包括 Windows 在内，状态目录保持私有，位于仓库及共享文件夹外。绝不发布 seed、应答文件或载荷归档。安装拒绝替换已有磁盘和 seed。中断安装用 `run` 继续，介质保留挂载直到验收成功；通过验收的客户机不带安装介质启动。

### 图形系统与实时屏幕

`graphical` 设置为 JSON 布尔值。Ubuntu 默认 `false`，Windows、macOS 默认 `true`。图形客户机需要唯一宿主 `qmp_port`，与 SSH、后端和其他客户机端口分开。QMP 仅绑定 `127.0.0.1`。面板不暴露 monitor，也不接受键盘、鼠标输入。

```json
"graphical": true,
"qmp_port": 2241
```

图形 Ubuntu 安装 XFCE、Xorg 和 LightDM，无头 Ubuntu 省略。账户使用 SSH 密钥；需要桌面密码时，通过已认证客户机管理会话设置。Windows 根据安装 WIM、ESD 元数据选镜像：`graphical` 选择匹配 Server 桌面或 Core 变体。使用介质实际版本名，不同发行命名不同。Windows 客户端版没有 Server Core 变体。macOS 即使无头运行也保留原生图形组件；`graphical: false` 禁用面板屏幕共享，Recovery 自动化仍使用私有 QMP。

按所选 DPI 下套件最大窗口设置桌面尺寸。基础 macOS 帧缓冲可能只暴露启动选定模式：配置私有 OpenCore `UEFI -> Output -> Resolution`（如支持时的 `1920x1080`），重启并在测试前验证实际模式。保留原固件和配置。macOS 关机 SSH 断开可能先于内核停止；等待客户机关机，再强制退出自有 QEMU。

启动或安装在 `~/.qemu-guests/registry` 注册公开状态元数据。停止的虚拟机仍保留。面板区分启动中、就绪、停止中、已停止、未知和需要恢复，孤儿进程不报告就绪。选择 **View screen** 切换图形客户机，可见时约每两秒刷新。捕获失败保留上一帧并明确显示错误，普通状态快照不含截图。运行时捕获文件临时使用，每次请求后删除。屏幕工具只接受已注册客户机 ID，并验证进程身份和回环 QMP 监听器归属。

### Intel macOS 无人值守安装

Apple 通过[官方说明渠道](https://support.apple.com/102662)提供安装下载。开源 [OpenCore macrecovery 工具](https://github.com/acidanthera/OpenCorePkg/tree/master/Utilities/macrecovery)也可在 Windows 从 Apple 下载 Recovery，验证 chunklist 和签名，无需已有 Mac。单独 Recovery 镜像不含本适配器要求的完整安装应用和私有 bootstrap product package，不能与下方准备好的安装 ISO 互换。示例显式选择 WHPX，不回退 TCG；尝试前补齐对应 macOS 版本的 CPU 参数及固件、OpenCore。已测试 WHPX 运行时是上述实验 CPUID 缓存变体，不意味着原版 QEMU 兼容。Linux 宿主必须显式选择 KVM。

1. 在 macOS 准备机器上准备完整英文、兼容 Intel 的安装应用。运行 `scripts/create-macos-media.sh /path/to/Install-macOS.app /absolute/installer.iso`，使用 Apple 工具和新建专用磁盘镜像。记录并验证介质校验和。
2. 补全 `profiles/macos-adapter.json`：兼容私有固件和 OpenCore、`/Volumes/` 下实际安装应用路径、明确目标序列号（如 `serial:work-target`，匹配磁盘设备 `serial=work-target`，比不稳定 BSD 磁盘号更推荐）、Appium 运行时、访问密钥、介质校验和及宿主 Tesseract。`hardware_args` 提供 USB 控制器和键盘；GPT 安装镜像以只读 USB 盘挂载，让 OpenCore 识别 HFS+ 分区。配置 OpenCore 超时，用 `.contentVisibility` 隐藏自身 EFI 项以免自启动循环。固件设置属于启动配置，不属于面板。
3. 通过 `python scripts/prepare-macos-payload.py /path/to/macos.json /private/payload.zip` 导出私有首次启动载荷。在准备 Mac 上运行 `scripts/build-macos-bootstrap.sh /private/payload.zip /private/bootstrap.pkg` 构建，将包复制到配置 `macos.bootstrap_package` 路径。两文件含生成账户密码，保持私有。
4. 与其他客户机一样运行 `guest-vm.py install`。控制器有限 OCR 等待 Recovery，通过快捷键打开 Terminal，交接给挂载 seed 的固定安装脚本。脚本拒绝已分区目标，只格式化明确配置的空客户机磁盘（指定时按序列号匹配），通过 bootstrap product package 执行 `startosinstall`。不点击 Setup Assistant，不在崩溃后悄悄重试破坏性交接。

bootstrap product package 安装到运行目标时显式加载首次启动服务，不在准备或 Recovery 宿主加载。首次启动将配置用户加入已有受限 SSH 访问组，在最后重启前标记用户设置页面完成。Sequoia 还清除已使用 `--agreetolicense` 安装留下的独立条款 cookie。

明确升级系统时，用现有测试账户凭据和 SSH 授权准备新私有 bootstrap 包，交给 `startosinstall --installpackage`，同时指定 `--agreetolicense --nointeraction`。在运行目标安装此包会重新启用首次启动。保留原盘，采用升级前先在独立副本验证。

5. 安装包提供首次启动 LaunchDaemon，创建客户机账户、启用 SSH、将 Appium 安装为用户级 LaunchAgent、完成初始配置并重启。首次启动清除安装器一次性登录标志，为专用账户设置持久 loginwindow 自动登录凭据，将标准 QEMU USB 键盘预设 ANSI、保持桌面唤醒并删除临时密码文件。其他键盘设备和布局需要各自匹配偏好。未选择工具链时，Appium 启动避免原 Git shim 的开发工具安装对话；保留明确配置工具链，不安装构建工具。FileVault 必须关闭；安装失败而不禁用加密。最终验收要求已认证 SSH、预期控制台用户、用户会话 Appium LaunchAgent 及就绪回环 Appium 服务。仅 OCR 和键盘交接完成不等于安装成功。

准备需要 Apple 工具 `createinstallmedia`、`pkgbuild`、`productbuild`、`hdiutil`。Windows、Linux 运行时可使用生成的 ISO 和包，不能用替代工具构建。安装器版本、固件和启动布局必须匹配；交接中断后保留未完成磁盘，检查 `macos-install.json`。不自动擦除部分安装客户机。随包渲染及控制测试不能代替所选 macOS 版本安装测试。

### Linux KVM 上的 Intel macOS

使用 [macos-kvm.json](profiles/macos-kvm.json) 准备 Linux/KVM 配置。它显式选择系统 QEMU、KVM 和用于 Sonoma 的 `Haswell-noTSX` 虚拟 CPU，设置 `stepping=3`，并关闭模型中可能不受 AMD KVM 宿主支持的 PCID。[XNU 拒绝早于 C0 的 Haswell 步进](https://github.com/apple-oss-distributions/xnu/blob/xnu-10063.141.1/osfmk/i386/machine_check.c#L86)：省略该步进可能在内核串口输出建立前反复重启。这里的 Intel 指客户机的 x86-64 平台；AMD 宿主也需要按实际虚拟 CPU 和 macOS 版本验证，不能直接套用 AMD 裸机的内核补丁要求。上游 [OSX-KVM 的 Sonoma 记录](https://github.com/kholia/OSX-KVM/blob/master/notes.md#macos-sonoma-support)也记录了 AMD 宿主使用该 CPU 模型的路径。

将示例复制到仓库外，提供已校验的 Apple 安装介质、bootstrap 包及运行包，填写操作者持有的 SMC 参数、匹配的 OVMF code 和已准备的 raw OpenCore 镜像路径。该配置提供 Q35、AHCI `sata` 控制器、USB 键盘与指针、快照 OpenCore 引导盘、VMware SVGA 显示和回环 SSH 转发。首次安装前，在私有 `state_dir` 放入独立可写的 `vars.fd` 固件变量副本；已有环境继续复用其变量和系统盘。固件、OpenCore、账户及 SSH 材料保留在操作者私有目录。

先核对 `/dev/kvm` 访问权限和实际加速器，再按上述安装流程运行。保留现有宿主 MSR 策略；若发生启动 panic，收集客户机串口和宿主 KVM 诊断，定位具体失败后再选择变更，不能自动更改共享宿主的 `ignore_msrs`。启动、认证 SSH、桌面登录、Appium 就绪及使用预构建 WDA 的原生 Mac2 输入验收分别记录。该示例沿用 CPU 帧缓冲路径，GPU 运行时另行配置。已验证版本和运行边界见 [Linux/KVM 桌面验收](DEVELOPMENT.md#linux-kvm-macos-桌面)。

### Windows 宿主机上的 Ubuntu GPU 运行时

Windows 11 x64 上，`profiles/ubuntu-virgl-whpx.json` 可选择 `qemu_runtime: "virgl-whpx"` 加速 Ubuntu OpenGL。受管运行时使用随包补丁构建固定版本 QEMU 11.1.2 和 VirGLrenderer 1.3.0，验证可执行文件、固件及 DLL，保持系统 QEMU 不变。需要 Python 3.12+、MSYS2 UCRT64、WHPX，以及已登录且原生 OpenGL 驱动可用的 Windows 桌面。隐藏 SDL 仍需要该桌面；宿主注销、会话 0 和宿主开机自动启动未验证。

将示例复制到操作者私有存储，提供已验证 Ubuntu 镜像、SSH 密钥、已准备 Appium 运行时及唯一端口。使用项目的可移植桌面需求，安装必须提供：

```sh
python scripts/guest-vm.py plan /private/ubuntu-gpu.json
python scripts/guest-vm.py install /private/ubuntu-gpu.json --requirements /project/desktop-requirements.json
python scripts/guest-vm.py run /private/ubuntu-gpu.json
```

首次安装自动添加 Ubuntu 二进制 Mesa 诊断工具，通过 LightDM/XFCE 在 Xorg 启动测试会话，设置所需显示尺寸，在 Appium 启动前检查硬件 VirGL。测试 D-Bus、AT-SPI 及已解锁原生密钥环保持隔离。控制台桌面专用于这些测试，人工使用不能与活动测试竞争。普通 Ubuntu 配置保留已有 Xvfb 会话。不允许把已有软件渲染磁盘切换到该运行时，应初始化新状态目录。应用和原生依赖在宿主机或指定构建机器准备，不在工作客户机编译。

此路径加速 OpenGL。CUDA、Vulkan、视频解码和任意宿主 GPU 未验证。受管运行时按需读取当前 GPU 扫描输出，生成私有图像，支持状态面板 QMP 捕获。Appium 截图继续使用应用正常驱动。就绪检查验证当前启动和会话；实际渲染、截图和业务 E2E 验收仍是独立检查。重建和验证见[开发说明](DEVELOPMENT.md#ubuntu-virglwhpx-运行时)。

### Windows 上的 macOS GPU 运行时

对于 Windows 11 x64 上已验证的 Intel macOS 15.8.1（24H32）实验，以 `profiles/macos-reims-whpx.json` 为私有配置起点。其 `qemu_runtime: "reims-whpx"` 构建并验证专用 WHPX-only QEMU、Windows Reims Vulkan 库及 option ROM。插件包含三项外部依赖补丁，并固定公开源码提交，不需要相邻开发检出目录。已有 Windows 客户机配置继续使用独立 `whpx-reset`。

要求原生 Windows Vulkan 驱动兼容 `VK_EXT_external_memory_host`。这不是 WSL/Dozen 路径，也不是通用 GPU 直通；每台宿主仍需原生 GPU 检查。

安装 GNU Rust 工具链（`rustup toolchain install stable-x86_64-pc-windows-gnu`）及 MSYS2 UCRT64 开发工具：GCC 工具链、Git、Clang/LLVM/LLD、CMake、Make、Ninja、Python、pkgconf、GLib、pixman 和 libslirp。MSYS2 位于非标准路径时使用 `QEMU_MSYS2_ROOT`。显式准备运行时：

```powershell
python scripts/reims_runtime.py
```

干净源码验证使用 GNU Rust 1.99.1 和 UCRT64 Clang/LLVM 23.1.3；新编译器或图形驱动版本需要重新进行原生验证。

首次构建下载固定源码及 Cargo、QEMU 构建依赖，在 `~/.cache/me/reims-whpx` 保留日志和失败工作区；后续启动复用已验证运行时。不移除忙碌构建锁。QEMU 构建系统拒绝带空格源码路径。默认缓存路径含空格时，将 `QEMU_REIMS_CACHE` 设为无空格私有路径，例如 `C:/qemu-cache`；受管配置启动也会使用它。独立构建可用 `--cache-dir` 覆盖。

可执行文件、依赖 DLL、固件、许可证文本和补丁配方一同打包并校验。已验证 Windows 呈现路径为无头 QMP 捕获，启动器为此运行时选择 `REIMS_VGPU_WINDOW=0`；原生 SDL 呈现未验证。此栈加速 Metal 渲染，不添加 VideoToolbox 硬件视频解码。

冷启动验证时在 macOS 内正常关机，确认记录的原生 QEMU 已退出后再启动。不要让 ACPI 电源按钮与第二个 SSH 关机请求竞争。睡眠恢复仍未验证，停滞实例保留供检查。

此配置还需要随包时序驱动。选入私有硬件配置前，准备操作者自有 OpenCore 镜像的新副本：

```powershell
uv run scripts/prepare-macos-gpu-boot.py --opencore C:/private/OpenCore.raw --output C:/private/OpenCore-gpu.raw --guest-build 24H32
```

工具验证并安装随包 PvgTimingFix 和固定 Lilu 1.7.2，校验和、写入及最终回执都使用捕获字节。输出镜像及其 `.json` 回执必须都是新路径，不能替换源。失败尝试保留新建部分输出供检查。准备器保留其他 kext，禁用交互启动选择器，不触碰源镜像和系统卷。源 OpenCore 配置必须已有恰好一个启用的 `Lilu.kext` 条目。假定 FAT 分区位于字节 1048576；其他已知布局通过 `--fat-offset` 指定。绝不覆盖已有输出。未知客户机构建在创建镜像前失败，系统更新需要重新审查。

兼容 Apple 安装介质、私有 OpenCore/OVMF 硬件配置、bootstrap 凭据及已准备桌面资源仍由操作者提供。硬件配置必须提供 Q35、Apple SMC、USB、SATA 设备、OVMF 和新准备的 OpenCore 镜像；示例选择 `apple-gfx-pci`，因此不再加其他显示设备。不分发 Apple OS 镜像或私有固件、凭据载荷。

安装后完成下方已准备桌面恢复流程，确认实际 GPU 输出，再运行未经修改的项目测试。运行时缓存、启动镜像和私有配置留在使用插件的项目外。

### 已准备 macOS 桌面的恢复

无人值守安装或明确选择的升级后，使用 `scripts/macos-desktop.py reconcile /private/guest.json --plan /private/desktop.json`。以 `profiles/macos-desktop.json` 为私有清单起点，固定已测试 OS 构建、应用 bundle 标识和 CDHash，保留私有 bootstrap 载荷 ZIP 作为凭据来源。未知构建和签名会失败。使用已安装 Pillow 的 Python 3.10+，以及客户机配置选定的宿主 Tesseract。

提供 Apple 签名 Xcode 和指定准备环境中已构建的 WebDriverAgentMac。WDA 作为独立用户 LaunchAgent 运行 `xcodebuild test-without-building`，模板为 `macos-wda.plist.tpl`。控制器要求该服务，使用 `webDriverAgentMacUrl`。绝不回退客户机编译，也不借用 Appium 管理的 WDA，因为其他驱动会话占用服务时可能停止它。

离线 Appium 还必须包含与客户机 CPU 兼容的 Mac2 驱动及依赖。只有服务的归档可以显示就绪，却没有驱动。原生验证在创建会话前导入准备好的 Mac2 入口，让缺失或不兼容依赖尽早失败。

可选清单 `files` 包含 `source`、安全暂存 `name` 和 `sha256`。可选 `setup_script` 安装预构建产物并配置运行时，以 root 运行，第一个参数为测试账户，可从 stdin 读取一行凭据以恢复该账户自动登录。必须幂等，不能悄悄编译依赖。文件暂存于账户 `.qemu-guests-desktop-inputs`。脚本、归档、凭据及生命周期、升级编排留在项目外。

准备会关闭专用测试账户的空闲屏保，密码和系统安全策略保持不变。原生验证也检查实际控制台锁定状态，因为 SSH、Appium 可以在锁屏后继续就绪。`reconcile` 只在验证控制台身份、系统 loginwindow 安全输入进程和可见密码框后，才可用私有配置凭据对专用账户认证一次。登录成功后由 OS 自行清除锁状态，不删除锁定 cookie。`verify` 不输入登录密码，仍锁定时失败。自动登录识别仅验证英文 Sequoia 1920x1080 控制台，其他锁定布局在输入凭据前失败。

特权工具链初始化使用 root 家目录，安装到测试账户家目录的文件恢复其归属。用户 LaunchAgent 为之后自动登录安装，不从 root SSH 会话加载。已准备桌面顺序为 `prepare`、冷启动、`reconcile`，再冷启动和 `verify`。

恢复先重启已审查 WDA runner，测试实际桌面访问。可用权限保持启用。缺失访问只通过 System Settings 原生辅助功能行和控件修复已审查应用。核对输入的 bundle 路径与启用开关，再重启 WDA 确认访问。只有已识别系统认证对话才能接收私有账户凭据。不编辑 TCC 数据库，不禁用系统安全策略。UI 适配器当前要求英文 macOS 和 ASCII 测试账户键盘布局。

权限授权还要求恰好一个已识别密码字段，OS 安全输入归属必须匹配测试账户内已审查系统授权进程。输入前再次核对提示和进程身份。字段缺失或含糊时，绝不回退到当前键盘焦点。OCR 授权识别已验证范围为 Sequoia 1920x1080 控制台。

`prepare` 只暂存提供的运行时和会话配置，发布 `prepared` 节点。计划冷启动前使用；之后 `reconcile` 复用同一不可变准备清单，不重复传同样归档。配置脚本字节和捕获凭据参与准备指纹，任一变化使该节点失效。需要重新准备时，私有客户机暂存目录中匹配的归档校验和可避免重复传输。替换文件必须通过客户机校验和检查后才能继续配置。

`verify` 不安装内容，也不改变权限。原生验证检查控制台账户、Appium GUI 服务、新 Finder 窗口中的文本输入和读回、两个准确窗口尺寸及 PNG 截图。只关闭新窗口和自有会话。可选具名 `checks` 使用显式客户机参数数组执行附加验证，例如用户提供的 GPU 探测。Finder 验收本身不证明 GPU 渲染或业务套件通过。通过稳定系统窗口编号跟踪新窗口；已有 Finder 窗口及几何保持不变。

随包透明 `java-argfile` 启动中继目前支持 Windows 和 Ubuntu。macOS 业务测试需要另行准备 Appium 启动适配器；GPU 运行时和已准备桌面控制器不提供该中继。

只有验证成功且确认清理完成，才将 `state_dir/macos-desktop/state.json` 发布为 `ready`。会话身份丢失或删除未确认，保留客户机测试租约供检查。冷启动后验证，再运行未经修改的项目业务套件。终态回执在资源和 worker 清理后、仍持有客户机预留时发布。保留预留始终需要检查，即使旧回执写着 `ready`。

已准备介质、固件及兼容清单仍是前提；此命令不选择或下载任意未来 macOS 版本。配置所提供固件自动启动已安装卷；桌面权限控制器无法恢复停在交互启动选择器的虚拟机。

### 自定义无人值守适配器

`os: custom` 接受用户提供的其他系统无人值守安装器。macOS 现已有上方内置流程。

- `seed_dir` 包含平铺自动化文件。工具添加带 Appium 运行时及 systemd、launchd 或 Windows bootstrap 的 `payload.zip`。自定义自动化必须安装载荷、配置客户机访问并运行 bootstrap。其他 OS 家族提供自己的 bootstrap。
- `hardware_args` 可替换默认磁盘和网卡参数，占位符为 `{disk}`、`{state}`、`{ssh_port}`。提供回环 SSH 转发，保留用户网络网关或相应调整 bootstrap。默认 x86-64 IDE/e1000。
- `qemu_args` 每次启动均生效，包括加速和固件。受管 Windows 与随包 Ubuntu 示例显式选择 WHPX；Linux 用系统运行时及显式 KVM。自定义系统运行时必须指定加速器，不假定 QEMU 默认硬件加速。自动加速探测仍只属于后端。monitor、stdin 和生命周期归监督器管理。
- `install_args` 首次验收前生效，支持 `{state}`、`{seed}`。必须启动可无人值守使用 seed 的自动化。通用介质用 IDE CD-ROM 挂载，适配器须提供兼容控制器。
- `acceptance` 是可选宿主参数数组，无隐式 Shell 展开，支持 `{state}`、`{ssh_port}`；自定义客户机必须提供。仅在安装、访问和所需 Appium、测试服务可用后返回零。探测可重复、只读，限时 15 秒。不能用成功的空操作作为安装验收。
- `timeout` 限制就绪秒数，默认 3600。失败保留安装磁盘和 seed。OS 或介质变化要求新状态目录。创建磁盘前检查 `media_sha256`。

厂商格式参考：[Ubuntu NoCloud](https://canonical-cloud-init.readthedocs-hosted.com/en/latest/reference/datasources/nocloud.html)、[Windows 无人值守安装](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/automate-windows-setup)。Apple 的 [Virtualization framework 安装器](https://developer.apple.com/documentation/virtualization/installing-macos-on-a-virtual-machine)是独立平台流程，不是此处随包提供的 QEMU 安装器。

## Alpine Docker 后端架构

- Alpine 无人值守安装到持久 qcow2 系统磁盘。
- 自动加速在有可访问 KVM 的 Linux 上使用 `kvm + host`，在兼容 Windows 宿主上使用 `whpx + host`，其他情况使用 `tcg,thread=multi + max`。硬件加速暴露 hypervisor 可用的宿主 CPU 特性，不使用受限 `qemu64` 基线。已有后端通过正常所属生命周期重启即可应用 CPU 变化，无需重建磁盘。KVM 要求兼容 x86-64 宿主 CPU；其他宿主由 TCG 模拟指令集。
- 环境准备配置从 `templates/` 下文件渲染；脚本提供明确占位值，不通过 heredoc 内嵌生成文件。
- 共享 shell 行为通过 `scripts/vm-utils.sh` 加载，初始化通用路径，并加载 `scripts/lib/` 中聚焦的 runtime、配置、模板、QEMU、guest 访问、Alpine 镜像和 VM 状态模块。
- 首次准备时，Alpine 从官方列表选择最快镜像源，升级为 HTTPS 并验证，必要时回退官方 HTTPS CDN。
- Alpine DHCP 和 Docker 容器使用 `192.168.127.1` 的 gvproxy DNS，同时支持 UDP 和 TCP DNS，不安装 guest DNS 代理。
- Docker 和 SSH 在 guest 自动启动。
- Docker 未认证 API 只通过 gvproxy 宿主回环转发 `127.0.0.1:2375` 暴露。
- 两个平台上，Docker 从 `20000–20127` 自动分配发布端口；QEMU 启动前，gvproxy 将所选范围的每个 TCP 端口转发到相同 guest 端口。
- 后端锁同一时间只允许一个 Alpine 后端，并预留其转发范围。工作 VM 拥有独立锁，可并发运行。后端锁状态通过原子 guard 变更，防止启动器相互覆盖。
- 独立操作租约覆盖 setup、环境准备、启停和客户端命令（测试、Docker、SSH/SFTP、工作区同步和代理构建）。竞争操作在修改 VM 状态前失败。正常退出和已处理信号释放租约；强制终止后，手动移除中断的 `run/vm-operation.lock` 或 `vm-state.guard` 前，先检查所有插件进程。
- QEMU 和 gvproxy 归属记录在终止前核实原生可执行文件和创建时间。已有 VM 只有转发规则及 guest 就绪与 profile 匹配时才被接受。Windows 环境准备和旧 shell PID 转换使用启动 Bash runtime 的工具，普通启动直接保留原生 PID。
- Docker 镜像保留在 qcow2 磁盘，后续测试复用。需要缓存复用时，不重建 VM，也不运行 `docker image prune -a`。
- Testcontainers Ryuk 保持启用，使用 guest Docker socket。

宿主 bind mount 不能直接由远程 guest daemon 使用。测试需要宿主文件时，使用 Docker build context 或命名卷。

### Windows 或外层 Linux 容器通过 SSH 执行 Docker 命令

Gradle 或其他测试命令调用 Docker CLI 时，在测试进程所在环境（Windows 或外层 Linux 容器）编译原生代理：

```bash
./scripts/build-docker-proxy.sh
./scripts/run-test-env.sh -- ./gradlew test
```

编译前先启动 VM。脚本通过已有 SSH 发送代理源码，必要时在 Alpine 安装 Go，在其中测试，并根据运行脚本的环境，以 `CGO_ENABLED=0` 为 Windows amd64 或 Linux amd64/arm64 构建。可执行文件经 SSH 下载，Windows 或外层容器无需安装 Go。Go 和缓存保留在持久 guest，临时构建文件会清理。非默认 VM profile 使用 `--profile <path>`。

Wrapper 将代理加入 PATH，因此 `docker build` 使用 Docker 上游 ignore matcher 筛选本地上下文，并通过 SSH 将 tar 归档发送到 guest 的 `docker buildx build --load`。Dockerfile 专用 ignore 文件优先于上下文 `.dockerignore`。项目 Gradle 任务仍负责准备发行物、选择 target 和命名镜像。其他命令在 guest 执行，不复制宿主文件；不转换宿主 bind mount 或 `docker cp`。命名 context、build secret 和 SSH mount 在具备明确传输支持前会被拒绝，不进行未筛选的工作区传输。

编译后的 helper 由所有项目共用：Windows 为 `~/.local/share/me/docker-proxy/docker.exe`，外层 Linux 容器为 `~/.local/share/me/docker-proxy/docker`。Windows 的 `~` 解析为 Windows 用户 profile，Linux 容器则为容器用户主目录。替换外层容器时，持久化此目录或重建 helper。必要时，编译和测试执行使用相同 `QEMU_DOCKER_PROXY_DIR` 覆盖。

在执行项目专用命令前，将宿主工作区复制到 guest：

```bash
./scripts/sync-workspace.sh --remote-dir /root/my-project /path/to/project
```

脚本通过 SSH 将 tar 流发送到暂存目录，仅在传输成功后替换目标，旧副本保留为 `<destination>.previous`。默认排除 `.git`、`target`、`node_modules`、`dist` 和 `.env`，可通过 `--exclude <pattern>` 添加项目专用排除项。它有意不构建或测试项目。

## 前提条件

在 Linux Bash 或 Windows Git Bash/MSYS2 中运行脚本，需要：

- QEMU（`qemu-system-x86_64` 和 `qemu-img`）。
- 可选 Linux `/dev/kvm` 访问或 Windows Hypervisor Platform；TCG 均不需要。
- `xorriso`。
- OpenSSH 客户端和密钥生成器。
- `curl`、`tar` 和 `sha256sum`。
- 首次安装 Go 和下载依赖时，需要运行中的 Alpine VM 且可访问软件仓库。

Windows 上，已知 MSYS2 工具目录和 Windows OpenSSH 作为回退追加到 `PATH`。已有命令优先，包括启动脚本所用 Bash runtime。这样可使用 MSYS2 `xorriso`，同时不替换 Git Bash 工具。

## 首次环境准备

```bash
./scripts/setup.sh
./scripts/create-vm.sh ./profiles/dev.profile
```

`setup.sh` 下载并验证官方 Alpine virt ISO。`create-vm.sh` 构建无人值守 ISO，选择配置的加速器，直接启动内核以实现确定性自动化，选择并保存可用软件源，配置 Docker 使用 gvproxy DNS，启动磁盘一次，验证 DNS、Docker 和所选仓库，再写入持久 ready marker。只在准备新磁盘时选择镜像源。已有磁盘但缺少 ready marker 时，脚本停止并保留磁盘供检查，不静默重建。

安装日志证明磁盘安装完成、仅启动后验证失败时，可不重装而继续验证。先在恢复 profile 设置 `VERIFY_EXISTING=true`，再运行：

```bash
./scripts/create-vm.sh /absolute/path/to/recovery.profile
```

若希望初始验证时拉取少量镜像，在 profile 中将 `PRELOAD_IMAGES` 设置为逗号分隔列表。镜像引用可包含 registry 路径、tag、digest、点、连字符和下划线。普通 Testcontainers 拉取会自动缓存在持久磁盘。

## 日常使用

后台启动 VM：

```bash
./scripts/start-vm.sh ./profiles/dev.profile
```

通过 guest Docker API 运行宿主测试：

```bash
./scripts/build-docker-proxy.sh # once, and after proxy source updates
./scripts/run-test-env.sh -- npm test
```

Wrapper 在两个平台都向测试进程提供 `DOCKER_HOST`、`TESTCONTAINERS_HOST_OVERRIDE` 和 `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE`。Windows 将其跨 MSYS 到 Windows 进程边界传递，并在启动 JVM 测试前恢复可写原生临时目录。Linux 容器中，测试进程与 QEMU 在同一外层容器运行。Ryuk 保持启用。框架请求 Docker 分配端口时，随机发布端口可用，因为 guest 分配与宿主转发共享配置范围。

默认 `auto` metrics 模式在 Windows 收集宿主全局、QEMU 进程和 Alpine guest 的 CPU 与内存指标，Linux 则直接执行命令，不启用 PowerShell 收集器。Windows 开启收集时，只打印最终平均／峰值摘要，并以结构化报告原子替换 `~/.qemu-guests/metrics/latest.json`。Linux 不生成指标摘要，也不更新该报告。两个平台都保留原命令退出码。报告有意省略命令文本和工作目录路径。极短命令可能在首次采样前结束，因此聚合值为 `null`。

其他操作：

```bash
./scripts/run-docker.sh -- ps
./scripts/sync-workspace.sh --remote-dir /root/my-project /path/to/project
./scripts/connect-vm.sh               # interactive SSH session
./scripts/connect-vm.sh --sftp        # SFTP session
./scripts/stop-vm.sh ./profiles/dev.profile
```

## 配置项

- `VM_NAME`、`VM_MEMORY`、`VM_CPUS`、`VM_DISK_SIZE`。
- `VM_ACCELERATOR=auto|kvm|whpx|tcg`；`auto` 在 Linux 探测 KVM、Windows 探测 WHPX，不可用时回退 TCG。明确选择硬件模式时，不可用即失败。
- `SSH_PORT` 和 `DOCKER_DAEMON_PORT`。
- `TESTCONTAINERS_PORT_START=20000` 和 `TESTCONTAINERS_PORT_END=auto`（两个平台均为 20127）；明确数字范围没有端口数量上限。
- `TESTCONTAINERS_PULL_PAUSE_TIMEOUT` 和 `TESTCONTAINERS_PULL_TIMEOUT` 单位为秒；内置 profile 为 TCG 回退下的大镜像解压提高两者。
- `TESTCONTAINERS_RESOURCE_METRICS=auto|true|false` 和 `TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1`；收集需要 Windows PowerShell，间隔接受 1–60 秒。
- `PORT_FORWARD=host:guest,...` 添加固定回环转发。
- `ALPINE_BRANCH` 和 `ALPINE_MIRROR_BASE`；`auto` 检测最快镜像源，明确 `http://`/`https://` 根 URL 则禁用自动检测。
- `PRELOAD_IMAGES=image,...`。

`auto` 将结束端口计算为所配起点加 127，所以自定义起点仍得到 128 个端口。超过 65535 的池必须明确指定有效边界。

内置开发 profile 自动选择加速，分配 4 GiB guest 内存和四个 vCPU，用于多容器和 JVM Testcontainers 套件。

固定宿主端口不得与 Testcontainers 范围重叠，所有转发绑定 `127.0.0.1`。

gvproxy 管理转发 listener，QEMU 管理一条 TCP transport 连接。旧 Windows QEMU listener 警告不再适用于此后端。128 端口默认值是可配置分配池，不是 gvproxy 容量上限。明确池必须位于 `1024–65535`，留出 guest 出站端口，并避开宿主转发、控制端口和 guest Docker API 2375。启动通过一个 controller 的持久 HTTP 连接注册完整池；绑定或请求失败即中止并清理所属 helper，不重试连接。

Linux helper 为 listener 继承足够文件描述符，另留 256 个用于连接。硬上限较低时，需提高宿主或容器 `nofile` 限制，或选择更小池。宿主端口可用性、内存、描述符和并发连接仍决定实际容量。Ryuk 保持启用并共享此池。插件转发目前全部使用 TCP，脚本不暴露 UDP/SCTP 发布端口。listener 绑定不证明应用响应或负载容量。

新 guest 使用 Docker 启动 wrapper：每次 daemon 执行前设置所选池，初始化缓存 allocator，再将出站内核范围恢复为 `32768–60999`（自定义池重叠时，选择该区间中更大的不相交部分）。池覆盖整个区间时，从 `1024–65535` 选择更大的不相交部分；没有剩余出站端口的池在启动前拒绝。

新 guest 从 guest 文件导入临时 BusyBox 镜像，发布一次验证分配后移除，不拉取 registry。恢复的已发布容器也会初始化 allocator，让完全占满的池仍能重启。启动等待 allocator 初始化和出站范围恢复，再报告成功；缺少 wrapper 的 guest 失败并给出维护说明。Docker 首次使用时缓存发布范围；若将发布范围一直作为出站范围，guest 出站连接会与其竞争。Daemon 失败保留退出状态，OpenRC 监督保持开启。

已有持久 guest 不自动迁移。能安全更新 guest 前，保留其明确 profile 范围。只改宿主 profile 不会改变 Docker 缓存范围，启动会拒绝持久池不匹配。在计划维护窗口，更新 `/etc/sysctl.d/99-testcontainers-ports.conf`，安装新渲染的 wrapper 和 `/etc/conf.d/docker` 配置，使用相同数字池，再重启 Docker 和 QEMU。更新时保留自定义 Docker 服务设置。重启 Docker 会中断容器，先确认归属。运行中 VM 绝不会为应用默认值而重启。

## 实测资源参考

Windows 代理遵循 Docker 的 Windows 归档权限：添加执行位，移除组和其他用户写权限，使脚本无需 Dockerfile 变通即可在 Linux 镜像运行。Linux 容器中保留源文件权限位，脚本必须已具备所需执行位。

一台有 28 个逻辑处理器、31.8 GiB RAM 的 Windows 宿主，使用内置 4-vCPU、4-GiB profile，并开启自动资源收集，执行缓存的 Elasticsearch 8.17 Testcontainers 集成测试。`VM_ACCELERATOR=auto` 选择 WHPX。Wrapper 记录命令成功、耗时 20 秒，Gradle 报告 16 秒，测试用例 14.89 秒，Elasticsearch 在 10.41 秒就绪。收集器得到 13 个有效样本，无采样错误。VM 冷启动到 SSH 和 Docker 就绪为 26 秒。同一持久磁盘上，先前 TCG 运行的 Elasticsearch 启动约 3 分 12 秒。

| 范围 | CPU 平均 | CPU 峰值 | 内存平均 | 内存峰值 |
| --- | ---: | ---: | ---: | ---: |
| Windows 宿主全部活动 | 23.8% | 35.0% | 已用 29,145 MiB / 89.4% | 已用 29,279 MiB / 89.8% |
| QEMU 进程 | 6.5% | 10.2% | 工作集 3,464 MiB | 工作集 3,472 MiB |
| Alpine guest | 44.3% | 71.5% | 已用 1,732 MiB | 已用 2,967 MiB / 75.6% |

宿主和 QEMU CPU 百分比按所有宿主逻辑处理器归一，guest 按四个 vCPU 归一。QEMU 和 guest CPU 平均值不包含最初计数基线。Guest 经 SSH 采样，因此包含少量测量开销。宿主全局内存反映测量机上无关应用的占用；为此 VM 规划资源时，参考 QEMU 工作集和 guest 指标。

## 验证

贡献者测试命令和离线回归清单见 [DEVELOPMENT.md](DEVELOPMENT.md#离线-shell-边界回归)。

## VM 与容器状态面板

插件包含一个用于对话面板的只读 MCP App，见 [OpenAI 插件扩展](https://developers.openai.com/plugins/build/extensions)。在支持的宿主对话标签页打开 **VM & Containers**，或要求显示 QEMU / Docker 状态。`qemu_docker_status` 返回快照及内置 UI 资源。

面板显示：

- VM 名、已核实 QEMU 进程状态和 PID、磁盘是否存在、环境准备标记、可读时的实际进程加速器，以及 profile 配置的 CPU／内存限制。
- QEMU 宿主系统、已核实 QEMU 进程和 Alpine guest 的实时 CPU 与内存。宿主／QEMU CPU 按所有宿主逻辑 CPU 计算，guest 按所有 guest CPU 计算。QEMU 内存为相对宿主 RAM 的 resident memory。外层 Linux 容器内，宿主系统指标来自内核系统视图，而非外层容器 cgroup 配额。
- 本地 SSH banner 可达性和 Docker API ping/version，不测试 SSH 认证或 guest DNS。
- 所有运行和停止的 Docker 容器、镜像、状态（含 Docker health 文本）和发布端口，支持名称和镜像筛选。运行容器含 CPU、内存指标；CPU 每核 100%，可超过 100%。内存尽可能扣除 inactive file cache，并相对 Docker 报告的 limit 显示。
- 观察时间、探测失败，以及本地服务响应但没有已核实 QEMU 进程时的警告。

使用 **Refresh** 获取新快照。可选自动刷新在面板可见期间每十秒运行。刷新失败保留上次快照并标为过时。无法获取容器列表与成功查得空列表明确区分。

资源在刷新时采样，独立于测试 wrapper 的 Windows metrics 报告。Guest 采样通过回环 SSH 和已有 VM key 读取 `/proc/stat` 与 `/proc/meminfo`，不安装工具、创建密钥或写状态。本地宿主和进程采样使用 MCP runtime 固定的 psutil 依赖。普通 Python 执行 `scripts/status.py` 时，这两个范围需要 psutil。权限不足、SSH 失败、进程停止或缺少 CPU 基线都显示不可用，不显示零。容器采样失败不隐藏容器列表。为限定刷新工作，每份快照最多采样 32 个运行容器，并发八次探测，其余标为不可用。

### 本地 MCP 运行时

在 Linux/Windows 宿主，或运行 VM 的 Linux 容器中安装 [uv](https://docs.astral.sh/uv/)。兼容清单注册 `.mcp.json`，宿主启动带固定依赖的 Python stdio server。它必须与 QEMU 在同一进程和网络命名空间，因为探测只访问 `127.0.0.1`，忽略 HTTP 代理设置。打开面板不启停 VM、不准备磁盘、不安装工具、不修改状态文件或容器。没有 settings extension。

默认与 `profiles/dev.profile` 和 `~/.qemu-guests` 一致。自定义已有 VM 时，将 `QEMU_STATUS_PROFILE` 指向其 profile，必要时使用现有 `QEMU_ALPINE_BASE_DIR` 覆盖。路径使用 Python runtime 的原生绝对路径；Windows 通过 `cygpath` 转换 Git Bash/MSYS 路径。Profile 按数据解析，不作为 shell 执行。存在其他活动 VM 锁时，给出 profile 选择警告。

```bash
uv run --script scripts/status-server.py
# Plain JSON snapshot, useful in hosts without MCP Apps rendering:
python scripts/status.py
```

面板使用官方 MCP Apps JavaScript SDK，以及 `openai/ui` 全局侧栏和对话入口。HTML 内含完整打包脚本，无外部 UI 依赖，也不从浏览器直接调用 Docker。原生渲染依赖宿主支持。此包是本地 stdio 集成，不部署或注册远程 ChatGPT 服务。硬件加速取决于宿主，模拟 capability 测试不能证明硬件可用。

### 构建与验证

资源收集器行为和聚焦面板验证见 [DEVELOPMENT.md](DEVELOPMENT.md)。

已检入的 `templates/status-panel.html` 从 `ui/` 生成。MCP server 运行时要求 Python 和 uv；只有重建 UI 才需要 Node。

UI 构建支持原生 Windows 路径。Windows 状态探测在核实 QEMU 身份和读取加速器前，将 Git Bash/MSYS PID 转为原生 Windows PID。进程不存在报告停止，检查工具不可用报告未知。

```bash
npm ci --prefix ui
npm run build --prefix ui
npm test --prefix ui
uv run --script tests/test-status.py
# Browser tests against a simulated MCP Apps host:
uv run --script tests/test-status-panel.py
```

浏览器测试需要已安装 Playwright Chromium（`uv run --with playwright==1.62.0 playwright install chromium`），或用 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指向已有 Chromium。CI 重建 bundle、运行协议／探测／浏览器测试，并验证生成 Codex 包。

## Linux 容器流程

非 root 运行镜像、持久存储和完整命令见 [container/README.md](container/README.md)。普通容器可通过 TCG 运行 QEMU。兼容 Linux 宿主上添加 `--device=/dev/kvm` 和设备组即可启用 KVM；两种模式都不需要 `--privileged`、宿主 Docker socket 或 host-network bridge。

运行镜像规范化 shell、profile 和模板换行，因此 Windows CRLF 检出也可在 Linux 容器构建运行。

测试进程和状态 MCP 服务与 QEMU 在同一外层容器运行，回环转发留在该网络命名空间。Guest Docker daemon 使用自身 Linux 内核创建容器，其权限不要求外层容器具备特权。Guest 架构仍为 x86-64，KVM 要求宿主和 guest 架构兼容。

## Docker 构建参数与共享锁

Docker 构建选项可在上下文目录之前或之后。显式 `-f`、`--file` 路径从宿主工作目录解析，必须位于上下文内。`--iidfile` 在构建成功后将镜像 ID 写回指定宿主路径。相对输出路径从宿主工作目录解析，父目录必须存在。客户机使用私有临时文件，传输后或构建失败后清理。`--metadata-file` 和 `--output`/`-o` 仍不支持并明确拒绝。

所有 `build-docker-proxy.sh` 调用共享用户级锁 `~/.cache/me/locks/build-docker-proxy.lock`，与虚拟机、项目、插件检出和输出目录无关。上传、安装编译器、编译、下载或替换可执行文件前先等待锁。`QEMU_DOCKER_BUILD_LOCK_TIMEOUT` 设置等待秒数，默认 900。正常退出及已处理信号释放自有锁。强制终止后，陈旧锁会报错；确认无编译或传输残留后才能移除报告的锁目录，不删除其他运行中构建的锁。

## 插件打包

`plugin.json` 是可移植元数据的权威来源。客户端清单与完整 skill 资源会生成到 `me.claude` 和 `me.codex`，请从这两个仓库安装。源 skill 使用可移植的 frontmatter。Claude 路由按 skill 目录保存在 `extensions.com.anthropic.claude.skillFrontmatter` 中，仅注入生成的 Claude skill。Codex 的 skill 文件保持源文件原样复制。

## 网络恢复

Setup、启停命令使用更新后的插件或匹配源码检出。发行 workflow 发布更新且新 Codex 对话加载之前，使用匹配源码脚本管理 VM。

`GVPROXY_QEMU_PORT=19200` 和 `GVPROXY_API_PORT=19201` 是回环控制端口，必须互不相同且位于所有转发范围之外。核实进程归属需要 Python 3，`GVPROXY_BINARY` 可指向 `setup.sh` 安装且已核实的 helper。

gvproxy 退出后，停止 VM 再启动。上游 v0.9.0 每进程只接受一个 QEMU 连接，因此恢复会重启两个进程、重新注册全部转发，并等待 SSH 与 Docker 应用响应，不自动重连仍在运行的 QEMU。端口冲突使启动失败，并移除所属进程。不要重启其他会话使用的 VM。API 可暴露端口，必须保持回环监听。

## 改进反馈

插件问题向 [storytellerF/me issues](https://github.com/storytellerF/me/issues) 反馈。报告前，skill 要求检索已打开和已关闭的 issue，使用脱敏或合成示例，并遵循用户已有的发布授权。优先复用已有报告；无法访问时，保留尚未提交的草稿。

## Python 生命周期与状态控制器

使用 Python 3.10+ 运行 `scripts/start-vm.py` 或 `scripts/stop-vm.py`，接受同一可选 profile 参数。`.sh` 选择解释器，通过 `QEMU_BASH_BINARY` 保留启动 Bash runtime；原生调用方可明确设置该变量。`QEMU_STATE_PYTHON` 可指定解释器。Python 启停流程管理就绪、取消和失败清理。进程信号仍通过共享身份实现核实原生可执行文件与创建时间。平台／guest adapter 规划加速和网络、运行 SSH 命令，不管理生命周期锁。Python 在取消和退出期间管理原生 helper controller 子进程。

`BOOT_TIMEOUT`（SSH 就绪，默认 300 秒）、`FORCE`（`true` 跳过正常关闭，默认 `false`）和 `TIMEOUT`（正常关闭，默认 30 秒）只从 profile 读取，不由继承环境变量设置。

环境准备仍由 `create-vm.sh` 进行 shell 编排，使用相同 Python 状态控制器管理操作租约、全局预留、进程注册和状态清理。Guest 模板及简单命令转发仍用 shell。未知进程探测、中断 guard 和清理失败会保留归属供检查。Windows 使用 Ctrl+C 或原生 Ctrl+Break 正常取消；Git Bash `kill -TERM` 会强制终止原生 Python，无法清理。手动恢复前检查剩余操作租约。部分 PID 发布后，所属 stop 还会在处理网络或释放预留前，检查待启动 PID 和原生身份。PID 发布不完整或身份仍未知时，手动恢复前检查保留状态和进程；仅缺少 PID 文件不证明已退出。

QEMU 创建前的失败（如日志不可写或明确进程创建失败）自动清理本次 helper 和预留。初始 guard 元数据失败也回滚该操作创建的 guard，允许重试；已有中断 guard 仍需检查。Shell 客户端请求租约或 guard 期间仍负责清理。取消等待创建者完成，再只释放该请求资源；令牌交付失败可重试，无需手动删锁。取消 helper 创建时，等待所属进程退出再移除预留；无法确认退出则保留恢复证据。就绪前取消在归属可核实时采用同样清理。就绪已提交后，VM 保持后台运行。取消 stop 保留剩余归属，便于后续 stop 完成。

原生 helper controller 无法确认退出时，操作租约也保留；恢复前检查所有剩余插件进程。新 start 绝不接管已有 helper 归属，先明确停止该 VM。阶段转换和恢复证据见[开发者生命周期规则](https://github.com/storytellerF/me/blob/main/DEVELOPMENT.md#虚拟机生命周期与状态控制器)。

## 配置文件隔离

Profile 设置只来自选定的字面量 `KEY=value` 文件。缺少必需设置时验证失败，可选设置使用内置默认值。每次加载都替换上一次文件配置。Profile 设置不导出给子进程；需要时 Testcontainers 设置显式传给测试命令。未知 profile key 会被拒绝，因此 profile 不能修改 PATH、HOME 或 controller/tool 选择。

VM 资源、端口、加速、Alpine 镜像和镜像源、镜像预加载、生命周期超时、`FORCE` 和 `VERIFY_EXISTING` 放在 profile。`QEMU_ALPINE_BASE_DIR`、`QEMU_STATUS_PROFILE`、`QEMU_STATE_PYTHON`、`QEMU_BASH_BINARY`、`GVPROXY_BINARY` 和代理 helper 路径等宿主控制仍通过环境设置，不是 profile key。

普通启动由 Python 直接创建 QEMU，在就绪前记录原生进程身份。启动完成后，将归属转交持久 VM 状态，使 VM 持续运行。发布中断或未经核实会保留预留和网络供检查；旧 shell 启动记录仍可恢复。不要仅因缺少 PID 文件就移除保留状态。

## 客户机安装依赖

Alpine guest 安装 `docker`、`docker-cli-compose` 和 `openssh`，用于 Docker API/CLI、Compose 命令、SSH/SFTP 和代理编译传输。OpenRC 提供 `cgroups` 服务，环境准备通过 `rc-update add cgroups default` 启用，不要添加非 Alpine 的 `cgroupfs-mount` 包。只在构建 Docker CLI 代理时安装 Go。外层 Linux runtime 从 `/proc` 读取进程身份，无需 `procps`。Guest 安装器明确将受监督 Docker wrapper 加入 Alpine `lbu` 归档，确保可执行文件和 OpenRC 配置在系统安装后保留。

真实验收应准备全新隔离 VM，独立使用 `QEMU_ALPINE_BASE_DIR`、profile 端口、磁盘、密钥和代理输出目录。启动并构建代理后，在本插件根目录运行：

```bash
bash scripts/run-test-env.sh --profile /path/to/isolated.profile -- \
  uv run --script tests/validate-guest-testcontainers.py --pool-start 28000 --pool-end 28015
```

使用该隔离 profile 的发布池边界。此显式启用检查拉取 BusyBox、Alpine 和 Ryuk 镜像，测试 HTTP 转发和 CPU／内存 cgroup 限制，在受限容器内触发 OOM，并检查 workload 清理。保持 Ryuk 启用，验证后只停止隔离 VM。

## 实验性 Windows GPU 补丁包

插件包含仅源码形式的 viogpu/VirGL 补丁包，供 Windows guest 使用原生宿主 OpenGL。带补丁 QEMU 可从创建起隐藏 SDL 显示（`-display sdl,gl=on,hidden=on`），同时保留 guest 可交互桌面用于自动化。隐藏模式与全屏不兼容。保持 `graphical: true`；这是隐藏的图形后端，不是 `-display none`。

此 Windows guest 补丁包是可选开发实验，不添加受管理 Windows GPU runtime 或自动 guest GPU 驱动安装器。已有 profile 和 runtime 默认值不变。Ubuntu 受管理 runtime 在上文独立介绍。

使用单独私有 runtime/profile，并保留回滚副本。驱动签名和 guest 配置仍是操作者前提，本补丁包不修改宿主 Secure Boot。测试编译仍在宿主进行。

参阅[构建、资格验证与回滚说明](DEVELOPMENT.md#实验性-viogpu-源码包)。
