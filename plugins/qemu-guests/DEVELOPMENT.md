# QEMU Guests 开发

## Skill 指引与验证范围

skill 入口负责通用的环境选择、使用项目的独立性、构建位置、归属和状态解释。参考资料分别说明工作虚拟机准备、macOS 专用流程、主机驱动测试、Alpine 后端操作与配置，以及实现维护。平台限定条件和失败约定保留在对应参考中；历史实验依据记录在本文，不在每次调用中重复。

只修改指引时，验证可移植 frontmatter、相对链接和两套生成发行包。维护参考中列出的后端辅助测试使用夹具。`scripts/build-docker-proxy.sh` 是实际后端操作，可能安装 Go 并编译代理，不得列入纯离线验证。原生虚拟机、重启、桌面和 Testcontainers 验收仍是各自限定范围、使用隔离资源的独立测试。

## Windows 工具回退路径

在 Git Bash 中配合单独的 MSYS2 安装运行 `bash ./tests/test-msys2-path.sh`，检查回退路径顺序、重复初始化、已有命令选择，以及代理变量向子 Bash 的传递。测试还会启动可用的 QEMU 和 xorriso 二进制检查版本，不使用虚拟机。

## gvproxy 端口分配审计

Windows 和 Linux 的默认池现为 20000–20127。过去默认 16／256 个端口、上限 512 的限制来自旧网络策略，不是 gvproxy 协议限制。[上游 v0.9.0 转发器](https://github.com/containers/gvisor-tap-vsock/blob/v0.9.0/pkg/services/forwarder/ports.go)维护监听器映射，报告实际绑定失败。它支持 TCP 和 UDP；本插件 profile 格式与注册仍仅支持 TCP。转发器不支持 SCTP。运行时不再包含旧 QEMU user-networking 后端、DNS 代理、迁移变通处理或 QEMU 监听器数量检查。

审查覆盖共享配置、虚拟机模板／OpenRC 分配器初始化、主机生命周期与操作租约、测试／CLI 包装器、容器准备、只读状态／UI、包注册／生成和 CI。变更移除端口数量策略，批量注册，处理出站范围完全重叠，即使主机 API 重映射也拒绝虚拟机 Docker API 冲突，要求包装器就绪，并在主机测试命令前验证运行中的规则和端口池。加速／平台 PID 处理、仅接受一次连接的 QEMU 传输、进程身份检查、单实例／操作锁、Ryuk、磁盘与镜像保留及只读状态预算仍然必要。状态资源采样的 32 个运行容器／八个 worker，以及每个容器的紧凑端口列表，是展示和 I/O 预算，不是发布池上限。没有通过移除 UI 资源限制来暗示更高网络容量。

本地 Windows 使用固定版本辅助程序，在隔离进程中注册并检查 10,000 条规则，耗时 3.25 秒。这证明注册成功，不代表能同时获得 10,000 个应用响应。另一个范围遇到已占用主机端口后中止，并清理全部部分创建的监听器。真实辅助套件覆盖 640 条规则、600 条规则的批量启动、后期冲突清理、无效输入、拒绝 PID 复用和重启。真实裸 QEMU 生命周期夹具覆盖竞争、超时／TERM、健康状态下重复启动、测试租约、退出状态及哨兵磁盘不变。配置／守护进程模拟覆盖默认 128 端口、超过 512 的数量、协议边界、出站回退、包装器缺失和守护进程清理。控制器单元测试覆盖连接复用、拒绝重定向、批次期限和 Unix 软／硬文件描述符行为。状态后端、可移植／客户端包及生成／CLI／工作流检查补齐本地回归范围。

审查期间，共享持久虚拟机被活动测试操作持有租约，因此不声称完成真实虚拟机重启、分配器迁移、全新 ISO 安装或新的应用负载测试。Linux 运行时／描述符测试属于 CI；本地 Windows 运行无法证明实际 KVM 或 Linux arm64 行为。下文早期迁移负载结果仍仅代表当时版本和范围。

## 验证与架构

端口配置测试不需要 QEMU 或虚拟机访问：

```bash
python ./tests/test-port-ranges.py
python3 ./tests/test-gvproxy-control.py
python ./tests/test-vm-utils.py
./tests/test-linux-testcontainers.sh
```

端口套件覆盖共享的默认 128 端口、显式超过 512 端口的池、包含控制与自定义转发的 gvproxy 映射、重复与保留端口、出站范围分离、Docker 缓存初始化及守护进程退出状态。其守护进程生命周期使用模拟，不能证明某个 QEMU 二进制的 socket 容量，也不能替代全新 Alpine／OpenRC 准备验证。

固定端口池有意保留：Docker 将随机端口交给 Testcontainers 前，所有转发监听器都已就绪。异步 Docker 事件观察器会在分配与主机连通之间引入空档。默认范围低于 Alpine 常用出站范围，两平台使用同一策略。范围可配置，没有人为数量上限。虚拟机内核临时端口范围校验和非空、互不重叠的出站范围仍不可缺少，见 [Linux 范围检查](https://github.com/torvalds/linux/blob/v6.12/net/ipv4/sysctl_net_ipv4.c)。Moby 只在分配器初始化时读取范围，不读取 `ip_local_reserved_ports`。包装器必须先建立映射再恢复出站 sysctl；仅 Docker API 就绪不够。缺少包装器的旧虚拟机现在会明确失败。

`gvproxy-control.py start --configure` 从 stdin 接受映射，将注册放在进程归属守卫和启动清理范围内。HTTP 请求复用一个回环连接，绕过环境代理，拒绝包括重定向在内的非 200 响应，且不重试。单次请求超时五秒，批次预算为 30 秒加每条映射 20 ms。Linux 启动会在硬限制内，将继承的软 `RLIMIT_NOFILE` 提升到监听器数加 256，绝不修改硬限制。负载下连接可能需要更多资源。注册失败会终止所管理的辅助进程，通过进程终止移除部分规则。启动包装器通过 `DOCKERD_BINARY` 继续由 Alpine 原生 OpenRC supervisor 管理，每次守护进程执行前，包括重启／重新派生，都会初始化端口池。其就绪检查使用虚拟机 Unix socket，独立于主机转发。缓存行为遵循 [Moby 分配器初始化](https://github.com/moby/moby/blob/v28.5.1/libnetwork/portallocator/portallocator.go)，二进制覆盖方式遵循 [Alpine OpenRC 服务](https://gitlab.alpinelinux.org/alpine/aports/-/blob/master/community/docker/docker.initd)。API 就绪本身不会强制惰性分配器初始化。全新虚拟机从本地文件导入 BusyBox 及其 musl 加载器，短暂发布一个容器，检查自动端口，再移除自己的容器和镜像。恢复已有映射已经能初始化分配器，此时不需要额外池端口。虚拟机就绪标记在恢复出站范围后写入，包装器退出时清除；主机启动／准备和测试命令均要求此标记。测试包装器在启动命令前检查运行中辅助程序规则和已持久化虚拟机端口池，避免新默认值静默沿用旧虚拟机分配池。

gvproxy v0.9.0 已固定，并使用上游 SHA-256 哈希。源码核对依据为[发布版本](https://github.com/containers/gvisor-tap-vsock/releases/tag/v0.9.0)、`cmd/gvproxy/config.go`、`cmd/gvproxy/main.go` 和 `pkg/virtualnetwork/services.go`。QEMU socket 使用虚拟机 `192.168.127.2`、网关／DNS `.1`、主机别名 `.254` 和固定虚拟机 MAC `5a:94:ef:e4:0c:ee`。服务端点为 `/services/forwarder/{expose,unexpose,all}`。启动验证控制／转发冲突，清理前核实原生 PID 的可执行文件和创建时间。不再使用 QEMU `hostfwd`。启动参数含 `-ssh-port -1`，禁用上游隐式 2222 规则；SSH 与 profile 其他转发一起通过 API 注册。

上游 QEMU accept 只执行一次。恢复测试应停止两个进程，再一起启动，确认注册规则及首／中／末应用响应。这也避免静默重连他人管理的虚拟机。就绪轮询仅用于启动；协议探测不重试失败连接。Windows TCP 传输必须在真实 QEMU 验证，上游 README 示例标为 Linux／macOS。

操作租约覆盖生命周期与客户端命令，防止测试、SSH／SFTP、同步或代理编译使用虚拟机期间被停止或重配置。客户端子进程不能复用租约来关闭虚拟机。准备流程在安装和验证之间保留单实例预留。INT／TERM 通过同一个 EXIT 清理退出；关闭清理不完整时保留归属状态。QEMU 归属包括原生可执行文件、启动时间和虚拟机名称；发送信号时，Windows 持有原生进程句柄，Linux 使用 pidfd。辅助记录使用独占预留、原子替换、代次 token 和控制器守卫；就绪检查验证监听器归属。中断的守卫需要检查，不能自动接管。Setup 参与串行化；缺少公钥时从已有私钥派生，不替换凭据。

就绪预算按真实经过时间计入探测执行。回环 HTTP 显式绕过代理，并有单请求期限；共享 SSH 调用启用 server-alive 检查，避免虚拟机连接丢失后无限持有操作租约。

资源收集器独立于测试运行指标。`scripts/status_resources.py` 通过 psutil 采样本机系统和已验证 QEMU 进程，通过 `templates/guest-resource-sample.sh` 和已有 SSH 密钥读取虚拟机计数器，并从 Docker 非流式 stats 端点推导容器用量。每次采样都有显式状态，缺少 CPU 差值时保持 null。容器内存减去 cgroup v1 的 `total_inactive_file` 或 cgroup v2 的 `inactive_file`，与 Docker Linux CLI 约定一致。探测失败仅影响资源采样，不替换有效清单。

`ui/host.mjs` 独立于 DOM 管理不可变快照、过滤、刷新协调和生命周期取消。应用注入串行协调、工具 I/O、计时器和时钟依赖。阻塞资源 I/O 与 CPU 采样在 Python MCP 服务器执行，不占用浏览器事件循环。`ui/panel.mjs` 将 Host 状态适配到视图，`ui/view.mjs` 格式化值。UI 编辑后重新构建 `templates/status-panel.html`。

在插件根目录运行：

```bash
npm run build --prefix ui
npm test --prefix ui
uv run --script tests/test-status.py
uv run --script tests/test-status-panel.py
```

浏览器套件使用模拟 MCP Apps host，覆盖资源渲染、不可用值、过时快照、响应式布局和刷新。Playwright 自带 Chromium 不可用时，将 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指向已安装 Chromium。此测试不能证明硬件加速或真实虚拟机／cgroup 可用性，须另行使用已运行虚拟机验证。

真实辅助程序生命周期／API 验证（不使用虚拟机）：

```bash
GVPROXY_BINARY=/path/to/verified/gvproxy python tests/test-gvproxy-lifecycle.py
GVPROXY_BINARY=/path/to/verified/gvproxy python tests/test-vm-lifecycle.py
```

第二个夹具运行真实裸 QEMU 和 gvproxy，不使用虚拟机磁盘，虚拟机 I/O 由模拟提供。覆盖竞争启动／停止／创建、协调重启、健康幂等性、TERM／超时清理、拒绝客户端子进程关闭、保留命令退出状态和哨兵磁盘不变。非默认安装可设置 `QEMU_TEST_BINARY` 和 `BASH_TEST_BINARY`。CI 安装 QEMU，并在 Linux 运行两个夹具。

对已空闲、运行中的 Windows 虚拟机进行应用验证，需要 Go 和已缓存的 `postgres:11-alpine`：

```bash
uv run --script tests/validate-gvproxy-network.py
```

此按需探测要求默认回环 SSH／API／控制端口。它注册 70 条同端口 HTTP 转发（21000–21069），检查全部响应三轮，并在并发 8／16 下执行 320／640 次 PostgreSQL 连接，不重试连接。重启验证可接受匹配的预注册 profile 规则。只清理自身夹具和额外规则。普通／自定义网络容器 DNS 探测另行执行。Linux 运行时镜像包含已验证辅助程序，无特权、禁网冒烟无需下载。CI 覆盖真实辅助生命周期与端口范围套件。

已验证的迁移依据（Windows x86-64、上游 gvproxy v0.9.0 和已安装 QEMU 11.0.1）：已有磁盘使用 WHPX 启动，DHCP 选择 `.2`／网关 `.1`，虚拟机 DNS 及普通／自定义 Docker 网络 DNS 均成功，未认证 Docker API 可通过回环响应。同时存在 91 条规则时，70 个 HTTP 端口三轮全部响应（210／210），包括首、中、末端口。PostgreSQL 重连探测在并发 8 下通过 320／320，在并发 16 下通过 640／640。协调重启 QEMU／gvproxy 并从 profile 恢复规则后，同样结果再次通过。没有添加连接失败重试。

Windows Docker CLI 代理通过虚拟机 Go 测试与原生构建，并构建 Linux 运行时镜像。其非 root、无 capability、禁网 TCG 冒烟在预装已验证 gvproxy 后通过。真实辅助与 QEMU 生命周期夹具在 Windows、Linux 均通过；Linux 重启检查覆盖 TIME_WAIT 复用，不放宽 Windows 绑定独占性。关闭会拒绝活动生命周期／客户端租约。已有 shell 工具（131 个断言）、状态（16 例）、面板和 UI Host（5 例）套件通过，可移植／客户端包验证及包生成／CLI／工作流测试也通过。PostgreSQL 就绪等待最终容器内 TCP 服务器，排除镜像临时仅 Unix 初始化服务器。此次迁移未执行全新 ISO 准备、实际 KVM 可用性和 Linux arm64 运行；须与已验证的已有磁盘和 x86-64 运行时行为分开。

插件／运行时检查后完成下游服务器验证：三个聚焦用例通过，随后完整套件通过 175 项测试（174 通过、零失败／错误、一个已有跳过），使用 JDK 21，断言和超时不变。完整命令含镜像任务耗时 1247 秒。

## 并发工作虚拟机控制器

`guest_config.py` 独立于 Alpine shell profile 验证 JSON profile。`guest_seed.py` 使用 pycdlib 从 `templates/guests/` 渲染私有无人值守介质。`guest-vm.py` 以状态目录租约监督前台原生 QEMU 进程，信号延迟处理覆盖进程创建与记录发布。停止请求携带会话 token；清理失败保留归属证据。工作虚拟机不获取 Alpine 后端预留。

监听检查绑定受监督的 `Popen` 子进程。Linux 正常退出期间可能在前次 `poll()` 与 `/proc/PID/fd` 扫描之间失去描述符访问权限；只有重新 `poll()` 确认该子进程已结束，才将扫描异常解释为未就绪，让主循环按真实退出码处理。活进程的访问错误仍向上传播，不据此猜测退出或放宽归属核验。`tests/test-work-guests.py` 覆盖退出竞态和活进程权限错误。

安装 `scripts/requirements-guests.txt`，再运行 `python tests/test-work-guests.py`。套件检查 Ubuntu／Windows 介质生成、拒绝校验和不符、转发、不完整磁盘保留及重复会话互斥。安装原生 QEMU 后，可并发运行两个暂停的 QEMU 实例，验证独立停止和清理。该进程冒烟中的受控验收不能证明操作系统安装成功。实际 OS 和 Docker／Testcontainers 验收需要相应镜像、后端、目标代理和适配器配置。

默认验收检查认证后的 SSH 与客户机会话中的 Appium 服务，Ubuntu 还检查 cloud-init 完成；原生应用 UI 另行验收。自定义适配器自行负责安装和验收。状态 MCP App 还读取工作虚拟机注册表，暴露独立的仅应用可用 PNG 捕获工具。所有生成文件必须放在私有状态目录，绝不写入本仓库。后端改名后保留旧存储路径。显式代理 target 写入 OS／架构子目录，保留用户级构建租约。

## 图形虚拟机与 macOS 安装

`guest_registry.py` 为每个规范化状态目录保存一个原子公开描述符。状态检查同时验证 QEMU 与 supervisor 原生身份和匹配 token。`guest_screen.py` 只解析已注册 ID，在有界 PNG 捕获前检查 QMP 监听器归属，成功或失败都删除私有临时文件。`ScreenHost` 独立于渲染管理选择、轮询、可见性和迟到结果拒绝。面板不提供远程 HTTP／VNC 服务器或输入工具。

运行 `python tests/test-guest-panel.py`、`npm test --prefix ui`、`npm run build --prefix ui` 和已有状态协议／浏览器套件。原生测试执行实际暂停 QEMU 的屏幕捕获与清理，浏览器测试检查虚拟机行、无头屏幕入口抑制和帧轮询。`tests/validate-work-guests.py --profile /path/ubuntu.json --profile /path/windows.json --report /private/report.json` 是按需真实验收：要求独立虚拟机已就绪，并发构建虚拟机本地 Docker context，验证回环 API 与已发布 HTTP，捕获图形屏幕，只移除自己标记的容器和镜像。所有虚拟机共享同一守护进程，因此发布端口须不同。

macOS 准备在一台准备用 Mac 上使用 Apple 工具。`macos_install.py` 运行时控制器仅在有界 OCR 后打开 Recovery 终端，发送固定 seed 脚本路径。持久交接标记防止破坏性重试；seed 脚本拒绝已分区目标磁盘。产品包 payload 通过首次启动 LaunchDaemon 配置账户、SSH 和 Appium 用户级 LaunchAgent。测试验证生成脚本与控制事件；实际安装器兼容性须使用匹配固件和介质检查。缺少准备用 Mac 时，准备脚本及安装包尚未在 macOS 执行，不能仅凭渲染测试就声称已安装或验证。

## 工作虚拟机集成依据

Windows 11 build 26200 配合 QEMU 11.0.1／WHPX，并发运行三个独立工作虚拟机：Ubuntu 24.04 XFCE／LightDM、无头 Ubuntu 24.04 和 Windows Server 2025 Desktop Experience。每台都构建私有 Docker context，访问共享 Linux daemon API，获取自己的已发布 HTTP 响应。两个图形虚拟机返回真实 PNG 帧，无头虚拟机没有屏幕端点。停止一个工作虚拟机不影响其余虚拟机和后端。修正原生 SSH 防火墙规则仅 Private profile 的问题后，全新 Windows 安装通过两次受监督冷启动完成无人值守安装。

历史 Windows WHPX 对比：QEMU 11.0.1 忽略 CPU-model 参数，四 vCPU 停滞，一 vCPU 可启动。QEMU 11.1 配合 `Westmere,-vmx,-svm` 能以虚拟机可见四处理器冷启动保留的 Windows 磁盘，default 和 host 模型失败。虚拟机热重置仍在 BIOS 启动时产生 VP exit code 4，禁用中断控制器也不能提供可用替代。新的 Windows 默认值改为使用下述受管理 partition-reset 构建和四 vCPU。显式旧 system-runtime profile 可保留干净退出的冷启动预算。意外退出不重试，也不回退加速器。图形 supervisor 观察 QMP paused 状态，避免仍存活但已暂停的原生进程继续标为 ready；暂停屏幕仍可查看。

### Linux KVM macOS 桌面

`profiles/macos-kvm.json` 使用系统 QEMU 和 KVM，提供独立的 Linux 配置。Haswell 必须显式选择 C0 或更新步进：QEMU 7.2 的默认 `Haswell-noTSX` 声明 stepping 1，Sonoma 的 XNU 在建立内核串口输出前就会拒绝它。只看到 OpenCore 交接后重启时，先保留失败状态，核对 CPU 模型、步进和私有诊断；不能直接归因于 AMD、MSR 策略或磁盘。示例设置 `stepping=3`，显式关闭宿主未提供的 PCID，保留 KVM 加速和原始 EFI，不注入 AMD 裸机内核补丁，也不更改共享宿主 `ignore_msrs`。

实际验收使用 Linux x86-64 AMD/KVM、系统 QEMU 7.2.22、四 vCPU、4096 MiB 和 VMware SVGA。一个已初始化的 Sonoma 14.8.9（23J631）独立副本完成启动、自动登录及 Appium 3.2.2 就绪。复用预构建的 Mac2 4.5.0／Xcode 16.2 环境，通过 Finder 窗口创建、键盘输入读回、640×480 与 800×600 原生窗口几何、1920×1080 截图，并确认只关闭新建窗口、删除会话及释放转发；已有窗口保持不变。正常客户机内关机后，确认原生进程退出，再冷启动并重复同一原生验收；最终正常关机、监督器成功退出和磁盘结构检查也通过。虚拟机内未进行构建，宿主 `ignore_msrs` 始终为关闭状态。系统安装介质、固件、账户、代码身份清单及诊断留在私有目录。

此记录验证的是现有客户机在 Linux/KVM 上的桌面运行路径，不覆盖全新安装、其他 macOS 版本、GPU 加速或透明 JVM 代理。

### WHPX 四 vCPU Windows 重启

`scripts/whpx_runtime.py` 管理集成构建、缓存和打包。源码 SHA-256 与有序补丁均固定；补丁名称／内容和 shell 模板内容决定独立缓存目录。构建取得独占目录预留，控制台取消后保留预留以便检查进程。源码校验和或编译器失败绝不启动虚拟机。全新解压使用 Python data filter，排除符号链接及未用固件源码／CI 目录树。构建编排位于 `templates/build-whpx-qemu.sh`，不生成 shell 字符串。构建器从 UCRT64 和源码固件打包 PE 依赖闭包，写入文件哈希，验证后原子发布完整目录。返回可执行文件前，在最终路径执行加速器探测；若先执行暂存 PE，Windows 镜像／杀毒句柄可能阻止目录重命名。失败工作区保留，不修改系统 QEMU。

`BuildSnapshot` 一次捕获源码版本、URL、校验和、构建模板字节和有序补丁名称／字节，且不可变。构建在选缓存前只捕获一次；位置、编译输入、打包的模板／补丁、清单和两次验证边界都显式接收同一快照。后续步骤不重新读取操作者可修改的模板／补丁路径。已验证源码归档先复制到唯一工作区，再校验与解压，因此外部归档替换不能改变验证后解压的字节。失败工作区及私有输入副本保留供检查。

捕获输入不变时，保留已有 recipe 算法和缓存身份，让之前验证的运行时仍可用。后续调用重新捕获当前输入并选择自己的 recipe。不要以新快照重新标记旧二进制，也不要用不同 recipe 重试失败构建。变异夹具仅使用临时目录和模拟编译／加速器探测，覆盖编译前修改、编译中删除、外部归档替换、变更后失败、缓存副作用前输入缺失、每次构建一次捕获及冻结字段。没有夹具启动 QEMU 或修改操作者缓存／虚拟机。

每次受管理启动验证完整文件清单，检查 `-accel help` 仅报告 WHPX。Windows 主机上的 Windows 虚拟机未指定自定义可执行文件时，`guest_config.py` 默认选受管理运行时。`guest-vm.py` 在取得虚拟机租约前准备它；只读 plan 仅解析未来可执行文件和固件路径，不构建。状态和停止仅使用持久化归属，无需编译器或运行时缓存。受管理 profile 拒绝可执行文件覆盖、未测试 CPU／加速器参数和冷安装预算。Linux 明确使用系统运行时／KVM。安全解压需要 Python 3.12+；MSYS2 UCRT64 提供原生构建依赖。`qemu-img` 仍是普通主机前提。

运行 `python tests/test-whpx-runtime.py`，覆盖缓存损坏、禁用 TCG 二进制、缓存复用、失败传播、只读计划和四 vCPU 默认约定。`python scripts/whpx_runtime.py --archive C:/private/qemu-11.1.2.tar.xz --msys2-root C:/msys64 --jobs 8` 使用已下载归档执行相同构建路径，仍验证固定哈希。重复成功调用会验证并返回缓存，不再编译。

原版 QEMU 11.1.2 在 Windows 11 build 26200、Windows Server 2025 BIOS／MBR 虚拟机上复现四 vCPU 重置失败。Q35／SeaBIOS、更小 BIOS 和屏蔽 x2APIC 仍失败。一次性 overlay 转 GPT 后可在 Q35／EDK2 启动，但重置挂起；基础磁盘未转换。禁用 WHPX 中断控制器未能完成 Windows 启动。这些结果不能证明存在通用 Windows 虚拟机配置问题。

`patches/qemu-11.1.2-whpx-partition-reset.patch` 将 [Mohamed Mediouni 提议的 reset hook](https://patchew.org/QEMU/20260421205749.55060-1-mohamed@unpredictable.fr/) 适配到 11.1.2，检查并记录 reset HRESULT。停止全部 vCPU 后，加速器在 QEMU 恢复 CPU 寄存器前重置 partition。[Microsoft API 契约](https://learn.microsoft.com/en-us/virtualization/api/hypervisor-platform/funcs/whvresetpartition)说明，这会清除每个 VP 的待处理状态，同时保留 GPA 映射和后备内存。x64 上要求 Windows 11。API 不可用时回调警告，该情况不算修复成功。HRESULT 不成功时应调查，不能当作重置通过。

`patches/qemu-11.1.2-whpx-cet-xsave.patch` 修复 WHPX leaf-7 handler 在 QEMU 过滤所选 CPU 模型后重新启用 host CET 位的问题。结果取模型与 WHPX 支持的交集，并要求虚拟机 XSAVE／XSAVES 保存恢复路径；无关位和动态 OSPKE 处理不变。两个补丁都进入带哈希的运行时包与缓存 recipe。只有固定上游源码实现同一约定，且原生／运行时验收通过后，才移除本地补丁。

保留的 Ubuntu 24.04 虚拟机在没有 `xsave`／`xsaves` 时暴露 `user_shstk` 和 `ibt`，随后 init 因用户影子栈页错误 panic。另一个旧运行时 overlay 在 2,394 秒后复现 init panic。Linux 以十六进制打印页错误：`44`／`46` 包含影子栈位，并非十进制错误 44／46。[Linux CPUID 依赖](https://github.com/torvalds/linux/blob/v6.8/arch/x86/kernel/cpu/cpuid-deps.c)要求 SHSTK 依赖 XSAVES；另见[影子栈文档](https://www.kernel.org/doc/html/next/x86/shstk.html)。故障虚拟机状态保留私有，不发布 RAM dump、磁盘或原始日志。该证据支持补丁，但未捕获直接 SSP 上下文历史。

全新独立、使用修复运行时的 Ubuntu 完成主机计时 7,222.22 秒压力测试、1,195,225 次运行时循环和 240 次健康采样，无 panic 或 worker 错误。Westmere 下虚拟机 CPUID 不含 SHSTK／IBT／XSAVE／XSAVES，启用影子栈返回 EOPNOTSUPP；systemd、认证 SSH 和 Appium 保持健康，原生 QEMU 身份不变。这是有界验收窗口，不证明无限期稳定。同一未中断实例随后通过完整使用方桌面套件（15 个应用、3 个面板用例，无失败／错误／跳过），断言和超时不变，主机构建与远程运行仍分离。另一个全新 Windows Server 2025 安装使用同一修复运行时，通过三次四核热重启，分别耗时 50.73、53.09、70.98 秒，每次均在不变的 180 秒期限内恢复认证 Appium，原生 QEMU 身份保持不变。主机构建的原生 Windows CPUID 探针确认 SHSTK／IBT／XSAVE／XSAVES 均缺失。

在主机有原生 C 编译器时运行 `python tests/test-whpx-runtime.py`。矩阵编译从随包补丁提取的辅助程序，检查两种 CET 掩码的全部模型／主机／XSAVE／XSAVES 组合，包括无关位保留。缓存与发布测试确保补丁变化选择新 recipe，暂存文件检查不执行 PE。硬件验收必须使用独立 profile／磁盘／端口，确认实际虚拟机标志及影子栈拒绝，完成至少两小时运行压力与使用方套件，再复查四核 Windows 热重启。保留现有虚拟机进程与崩溃现场；不允许在虚拟机编译或回退 TCG。

使用上述集成 CLI，不另行维护手动构建参数。固定哈希记录验证时使用的官方源码归档，不是独立发布者签名。固件来自 release 的预构建 `pc-bios` 文件；依赖的非系统 DLL 放在可执行文件旁，因此受管理启动不需要 PATH 中有 MSYS2 目录。测试构建使用 GCC 16.2、Meson 1.12 和 Ninja 1.13。

对空闲、已就绪的四 vCPU Windows 虚拟机，以下按需命令请求真实虚拟机重启；绝不启动 QEMU 或改变加速方式：

```powershell
python tests/validate-whpx-reboots.py --profile C:/private/windows.json --report C:/private/reboots.json
```

它检查受监督原生身份和 QMP 监听器，比较三次 `shutdown /r` 请求前后的 Windows 启动时间，拒绝暂停或替换的 QEMU，每次重启后确认四逻辑处理器，并在同一轮期限内等待虚拟机 Appium 验收。仅 SSH 可用不能证明交互式 Appium 已启动；失败轮次不重启。报告放在仓库外。并发构建和发布端口验收另行运行 `validate-work-guests.py`。

真实状态面板验证要求至少两个图形和一个无头虚拟机就绪，再运行：

```powershell
uv run --script tests/validate-live-panel.py --profile C:/private/windows.json --profile C:/private/ubuntu-desktop.json --profile C:/private/ubuntu-headless.json --output-dir C:/private/panel --chromium "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

它通过临时回环 MCP Apps host 桥接提供实际生成面板，后端使用源码状态／屏幕函数，不使用模拟快照。验证 ready 卡片和资源、无头屏幕按钮缺失，以及反复图形选择时 PNG 数据与请求虚拟机匹配。报告和面板截图保留在私有输出目录。这验证源码 UI 集成；发行发布并由新对话加载更新插件后，已安装 Codex 面板才获得新代码。

最初修补运行时探测在同一原生 QEMU 进程连续通过三次热重启，首次成功 SSH 启动时间探测分别为 18.50、18.55、18.52 秒，随后通过虚拟机 Docker CLI／API 验收。可复用探测又在同进程通过三次重启、四处理器检查和 Docker CLI／API 验收。未构建 TCG 代码。这只证明测试过的 BIOS／MBR、CPU 模型和主机／虚拟机组合的重置修复；原版二进制、Windows 10 和补丁 UEFI 仍是独立情况。

随后从全新源码工作区运行集成构建器，打包仅包含 WHPX 加速器的独立运行时。新的四 vCPU Windows Server 2025 图形安装无人值守完成，supervisor 冷重启次数为零，从初始安装到最终 Docker 验收始终同一原生 QEMU 身份。两个全新 Ubuntu 24.04 工作虚拟机（XFCE 和无头）也在显式 WHPX 下无人值守准备完成。三者同时构建虚拟机本地 Docker context、访问共享 API 并获取自己的已发布 HTTP 响应。停止／重启无头虚拟机不影响两个图形进程。新 Windows 安装再通过三次热重启，含处理器检查分别 43.05、27.59、20.64 秒，随后三虚拟机 Docker 验收再次通过。真实源码状态面板通过 Windows→Ubuntu→Windows 切换，QMP PNG 匹配，ready／资源卡正确，无头没有屏幕按钮。这是源码面板／浏览器桥接检查；已安装客户端须等发行发布后加载。

通过虚拟机 SSH 登录调用 Docker 代理时，Windows 系统 OpenSSH 子进程在 stdin／output 停滞。Windows 代理命令 I/O 现直接使用 `golang.org/x/crypto/ssh`，保留已有私有后端 host-key 策略和远程退出码。Linux／macOS 继续使用系统客户端。传输测试覆盖二进制数据、EOF、多会话、远程失败状态和 stdin 仍打开但未使用时命令完成，在原生 Windows 及 Alpine race detector 下通过。固定依赖要求 Go 1.26。变更后真实跨系统验收通过。密钥、介质、生成凭据、详细报告和截图留在仓库外。

### WHPX 上的实验性 macOS Recovery

OpenCore、固件和 SATA 布局参考 [OSX-KVM](https://github.com/kholia/OSX-KVM/tree/4c378a4b5e0b219783683012bec680325eb40719)，不复制其 Linux KVM 加速器／CPU 参数。测试源码为该提交。其手动 Disk Utility 安装不属于无人值守准备。

测试的 Intel Windows 11 主机中，QEMU 11.1.2 加 reset 补丁已进入 XNU，但 Sonoma Recovery（Darwin 23.6.0）在 `cpu_threads.c:198` panic：`Zero divisor: topoParms.nCoresSharingLLC`。启用 OpenCore 启动参数 `-v keepsyms=1 debug=0x108 serial=3`，捕获 QEMU 串口输出，以区分 panic 和固件挂起。独立的[缓存拓扑补丁](patches/qemu-11.1.2-whpx-cache-topology.patch)将 CPUID leaf 4 加入 WHPX exit 列表，让已有 QEMU CPUID handler 提供所选 CPU 模型的确定性缓存拓扑。应用到同一 reset 补丁源码并重建后，越过该 panic，以四 vCPU 到达英文 Sonoma Recovery。未变化的受管理 Windows 二进制保持独立；集成构建器尚未应用此实验补丁。

成功探测显式使用 `whpx,hyperv=off,kernel-irqchip=off`、`Skylake-Client,-hle,-rtm,vendor=GenuineIntel,-vmx,-svm,-hypervisor,+invtsc,vmware-cpuid-freq=on`、Q35、4 GiB RAM、单 socket 四核、qemu-xhci USB 键盘／平板、Apple SMC、上游 OVMF 与私有可写 variables 副本、AHCI SATA 2／3 端口的快照 OpenCore 和 Recovery 磁盘、端口 4 的独立空目标、无 option ROM 的 vmxnet3，以及 vmware-svga。这些参数只描述一次探测，不是通用兼容承诺或最小必要集合。未编译或使用 TCG。判断调试选项是否必要之前，须在不禁用 Hyper-V 特性的情况下重复。

Shift-Command-T 打开 Recovery Terminal。批量按下／释放会丢失释放并重复字符；分离 down／up 事件、使用 150 ms 轮询间隔后可正确执行命令。控制器使用此间隔，中断时释放修饰键，交接前要求 shell 提示符。

后续仅安装探测在 Windows 下载官方 Sonoma 14.8.9（23J631）InstallAssistant 包，解出安装器 app，将 shared-support 包传到 Recovery，在专用空白 64 GiB 工作盘运行 `startosinstall --volume --installpackage --agreetolicense --nointeraction`。安装完成，虚拟机可见四逻辑处理器、4 GiB 内存，具备图形登录与 Finder／Dock、公钥 SSH、首次启动标记和已注册只读 QMP 捕获。安装器重启期间原生 QEMU 身份不变。之后还需一次 QMP 硬件重置和 Recovery 修复才完成初始 bootstrap；这不能证明完整无人值守源适配器运行，也不能证明干净的虚拟机请求重启。其他 Windows／Ubuntu 工作虚拟机保持 ready。明确未验证 macOS Docker 代理。

目录包的 `Digest` 匹配压缩 XAR 目录表的 SHA-1，不是整个包。全部 1,303 个 SHA-256 块匹配从 Apple HTTPS 端点获取的完整性数据。签名方法 2 提供自身哈希，不是数字签名；不能称为已签名 chunklist。Recovery 的 `hdiutil verify` 通过，`pkgutil --check-signature` 报告 Apple Software 签名。这与此前经过签名验证的 Recovery chunklist 不同。介质哈希和原生报告保留在仓库外。

探测揭示两个 bootstrap 边界。开机时包安装在 launchd 扫描启动目录后才写入 LaunchDaemon，仅写 plist 不会启动。产品包现含 postinstall hook，只在目标为 `/` 时 bootstrap 服务，保护准备用机与 Recovery 主机。已在安装后的 Mac 用无实际作用夹具执行原生 `pkgbuild`／`productbuild` 和包展开；记录式 launchctl 替身验证备用目标隔离及 bootstrap／kickstart 处理，不加载真实服务。该检查没有安装更新后的完整 Docker payload。

原生 SSH 接受密钥后，以 `Access denied ... by PAM account configuration` 关闭。将工作用户加入已有 `com.apple.access_ssh` 组后解决。首次启动现会执行此操作；组不存在时不创建新限制。每用户 Setup Assistant 偏好还避免账户创建后显示无障碍／云页面。确认键盘输入有效后关闭 QEMU 键盘识别提示；加速图形和任意发行版不在此次验证范围。随包适配器仍要求准备好的完整安装介质和 bootstrap 包；缓存拓扑补丁仍属实验，并非默认受管理 Windows 构建的一部分。镜像、固件 variables、账户凭据和详细日志保持私有。

## 独立 Appium 工作虚拟机

工作虚拟机 profile 现要求 `appium`（运行时归档、SHA-256 和独立主机隧道端口），拒绝已移除的 `backend`／`proxy_binary` 字段。seed 不含 Docker 代理或 Alpine 密钥。Alpine 主机 Docker 流程仍独立。虚拟机验收检查认证 SSH 和回环 Appium 就绪响应，Ubuntu 另检查 cloud-init。Windows 保留专用测试账户登录，并以交互式计划任务启动 Appium；SSH Session 0 绝不启动桌面应用。macOS 安装用户 LaunchAgent，Appium 验收前要求用户已登录。Linux 服务就绪不能证明 X11／AT-SPI 驱动兼容；这些前提由使用项目负责。

运行时构建器固定 Appium，接受显式 npm 驱动／插件版本，创建可重定位私有元数据；虚拟机重定位通过 YAML 解析重写扩展安装路径。服务在独立 Node 进程启动 Appium，避免停止计划服务后留下包装器子进程。Windows 直接捕获 stdout／stderr，避免 Windows PowerShell 将原生诊断 stderr 当作终止错误。项目插件、JDK、应用路径、后端服务转发和测试选择不属于本插件。

验证：Windows 运行时构建器与虚拟机升级已使用 Appium 3.2.2／DesktopDriver 2.8.0 执行。主机运行的桌面端到端注册用例在四 vCPU WHPX 虚拟机通过，未使用虚拟机 Docker。独立虚拟机窗口检查覆盖外进程过滤、DPI 感知的 800x600 缩放、通过标准远程切换进入无标题模态对话框及返回主窗口。此依据不声称完成全新无人值守 Appium 准备或 Linux／macOS Appium UI 验证。前面 Docker 虚拟机验证描述的是已被取代的工作虚拟机模式。

工作虚拟机资源策略：编译默认在主机或既有指定构建环境执行，仅向工作虚拟机传输预构建产物和依赖。虚拟机编译，包括构建原生代码的依赖安装 hook，都需要用户明确要求。安装虚拟机／Appium 或请求测试不属于该授权；不得添加虚拟机构建回退，也不得为容纳编译而增加虚拟机资源。

## 项目自身的运行时要求

`test_requirements.py` 验证可移植平台要求和预构建运行时清单。`project_setup_hooks.py` 管理有界主机准备作用域；`run-setup-hooks.cjs.tpl` 执行已暂存的虚拟机初始化脚本，使用私有日志，不进行 shell 参数求值。虚拟机 hook 仅用于运行时，编译仍需要用户明确例外授权。`guest_desktop.py` 从项目要求推导桌面初始化数据，不把依赖列表存入虚拟机硬件 profile。新虚拟机私下记录要求／脚本指纹；普通测试执行拒绝过时初始化。

运行 `tests/test-desktop-provisioning.py` 和 `tests/test-project-setup-hooks.py`，覆盖声明边界、seed 设置、预构建清单、hook 失败／参数处理和指纹失效。`tests/test-work-guests.py` 覆盖小型无二进制 cloud-init 文档和有界就绪探测。可选 Windows 显示辅助程序由主机准备工具编译，只在虚拟机加载；绝不替换为虚拟机中的 `Add-Type -TypeDefinition`。

## 配置驱动的测试代理

`run-test-env.sh` 是统一主机入口。`--profile` 分支保留原后端环境／租约／指标实现；`--config` 委派给 Python 环境管理者，只启用已声明适配器。旧脚本仅是 exec 别名。Windows／Linux JVM Appium relay 镜像配置的文件角色。Linux 将启动 capability 和带引号的 JVM 参数文件重写为目标 JDK 与 POSIX 产物路径，其他 WebDriver 流量不变。测试方法不执行 SSH 或暂存。创建会话时上传当前 classpath／JDK／agent 产物和每例输入。输出收集先于会话响应与诊断。驱动重启期间保留虚拟机私有状态，仅在运行退出时于配置的后代根目录下删除。每虚拟机测试租约串行化桌面使用。主机命令使用共享作用域进程组／Windows Job Object 运行时，由 scripts/sync-process-runtime.py 打包；不支持虚拟机构建命令。

运行 tests/test-test-environment-ownership.py，覆盖无 shell 转发确认、会话交接失败回滚和诊断／删除归属边界。转发使用 `ssh -N -T`，stdin 为空，并通过私有 OpenSSH 启动诊断等待本地监听器／远程转发确认。绝不能让虚拟机 PowerShell 阻塞在 `Console.In.ReadToEnd`：Windows OpenSSH 断开后可能留下它，重复运行耗尽虚拟机提交内存。Appium delete 获确认后释放会话归属，即使后续诊断失败；回滚未确认时保留归属供清理。

运行 tests/test-linux-transport.py，覆盖 POSIX classpath／文件映射、预构建归档内容、凭据拒绝、清理边界和变换后的 WebDriver 交接。Linux 操作者按 README.md 提供 TEST_ENV_LINUX_RUNTIME；主机负责全部 Gradle／测试执行和构建，已准备的虚拟机 Appium 桌面只运行应用。

运行 tests/test-test-environment.py，覆盖环境验证、argv／退出状态、租约竞争、服务转发角色、重启状态保留和协议透传。Docker shell／生命周期测试改用新入口。已有包／准备和状态检查仍独立。真实验收使用项目自身环境配置和主机构建；应用夹具不应进入本插件。

进程树／会话清理未获确认时，保留每虚拟机 test-environment.lock，阶段为 cleanup-uncertain。操作者恢复前检查记录的原生管理者和虚拟机 Appium 状态；绝不抢占或自动丢弃租约。

项目集成将提供方设置留在使用仓库之外。操作者管理的 `TEST_ENV_DOCKER_PROFILE` 和 `TEST_ENV_GUEST_PROFILE` 补全省略的连接；`launch.artifacts` 指定包含额外预构建文件的 JVM 属性名。Appium 诊断扩展与应用并行执行，通过 WebDriver 返回文本，不要求提供方专用客户端参数。

macOS 首次启动通过认证后的原子 root 专用 kcpassword 文件和 loginwindow 偏好，启用专用账户自动登录；拒绝已启用 FileVault 的配置，并在发布就绪和重启前核实 loginwindow 账户。Appium 启动器可由该账户读取，LaunchAgent 在图形用户会话运行。验收要求对应 console 用户和已加载 gui-domain 服务，仅 SSH 端口打开不够。准备使用稀疏镜像；源码和输出同文件系统时为 ISO 建硬链接，避免无谓完整复制。不涉及工作虚拟机编译器。

完整 createinstallmedia 输出必须使用 GPTSPUD，不能使用旧 Apple Partition Map。安装器作为只读 USB 磁盘连接，OpenCore 保留为启动器。按文档使用 `.contentVisibility` 隐藏 OpenCore 自身条目，否则选择器可能反复启动自己。Recovery 可能在 `/Volumes/Image Volume` 暴露安装器，应根据真实启动布局验证配置的应用路径和空目标盘。主机 OCR 在严格匹配 shell 提示符前放大帧（requirements-guests.txt 固定 Pillow）。生成 seed 脚本始终使用 LF，包括 Windows。交接前被中断的 UI 状态在新 QEMU 进程重置，破坏性交接标记则持久保留。live-panel 验证器接受一个图形虚拟机；只有提供相应虚拟机才报告切换／无头覆盖。禁止 TCG 时，其原生 Windows 屏幕回归使用 QEMU_TEST_ACCEL=whpx。

测试的首次启动 daemon 中，sysadminctl -autologin 返回零，却报告 SACSetAutoLoginPassword error:22，且未生成 /etc/kcpassword。它要求 console SessionAgent，不能作为无人值守凭据发布者。Node 辅助程序认证生成账户，以 0600 权限原子写入兼容 loginwindow、NUL 结尾并填充的凭据，清除安装器 oneTimeAutoLogin 标志，设置账户／解锁偏好，删除临时明文文件。保留该安装器标志会让 loginwindow 在首次登录后删除 autoLoginUser 和 kcpassword，因此仅首次启动成功不够，必须验证 bootstrap 重启后仍能自动登录。Microsoft 的 [macOS 用户资源](https://github.com/microsoft/macos-cookbook/blob/master/resources/macos_user.rb)使用同一 root 专用 loginwindow 凭据约定。实际 GUI 会话／Appium 验收仍是必需步骤。

无人值守 Recovery 选盘优先使用 macos.target_disk=serial:work-target，并在 QEMU 目标设备设置同一 serial。有界 IORegistry 解析器按该 serial 恰好选出一个完整 BSD 磁盘；零个或多个匹配都在擦除前失败。已有整盘与非空分区检查继续适用。旧 /dev/diskN 选择器仍为显式选项，但要求枚举稳定。解析器测试覆盖重排／外来磁盘、ATA serial 填充和目标缺失／歧义。

默认 QEMU USB 键盘标识为 product 1／vendor 1575／country 0。首次启动仅向 com.apple.keyboardtype 添加其 ANSI 条目（1-1575-0 = 40），保留其他设备条目。这样可避免无人值守测试桌面的 Keyboard Setup Assistant，不会全局禁用键盘识别或改变实体主机键盘。

Appium 启动会探测 Git 的可选修订元数据。原生 macOS 的 /usr/bin/git 是按需安装开发工具的 shim。启动器不调用 Git，而先检查 xcode-select --print-path；未选工具链且 DEVELOPER_DIR 未设置时，使用常规 CommandLineTools 路径，让 shim 返回工具缺失错误而非打开安装器。保留操作者显式工具链。此处理不安装或编译开发工具。

真实验收：Intel macOS Sonoma 14.8.9（23J631）使用实验 WHPX CPUID-cache 运行时、四 vCPU 和 4096 MiB RAM，完成空白盘无人值守安装。bootstrap 重启自动进入测试账户，SSH 与 GUI 会话 Appium 3.2.2 服务器通过。额外热重启保留同一原生 QEMU 进程，恢复自动登录／Appium。安装后还执行了键盘类型和缺失 Git shim 初始化。Alpine 后端保持停止时，真实浏览器验证源码状态卡并捕获虚拟机桌面帧，无浏览器错误。本次仅覆盖一个图形虚拟机，不覆盖多虚拟机切换；仅证明 Appium 服务器就绪，不是 macOS 应用 UI 测试或驱动会话。没有在工作虚拟机编译。

Windows 虚拟机传输通过 OpenSSH stdin command mode 发送 PowerShell 脚本，以 ASCII／base64 封装 UTF-8 内容。即使完整套件暂存／清理路径增长，远程命令仍保持有界；cmd.exe 参数限制不能截断脚本。包装器保留 PowerShell 终止错误与原生命令退出码。真实虚拟机探测覆盖 20,000 字符 Unicode 脚本；传输回归覆盖有界参数和私有失败诊断。

后续 macOS 工具链检查安装 Apple 签名的 Xcode 16.2（16C5032a），选择 developer 目录、接受许可并完成首次启动安装。在明确允许虚拟机构建的例外下，Mac2 4.5.0 的 WebDriverAgentMac 在四 vCPU WHPX 虚拟机成功构建，没有扩容。通过虚拟机 UI 为 runner 与 Xcode Helper 授予 Accessibility 权限，并用 Apple 工具启用自动化模式。主机连接 Appium 创建 Finder 会话，取得原生 XML 与 PNG 截图，点击 File／New Finder Window，验证新窗口后删除会话。这证明原生 Mac2 UI 冒烟通过；使用项目端到端验收另行处理。一般禁止虚拟机编译的规则不变。

测试的 macOS VMware SVGA 帧缓冲最初仅提供 1280×800。在独立私有 OpenCore `UEFI/Output/Resolution` 配置选择 `1920x1080`，重启后取得 1920×1080 虚拟机模式和 QMP 帧，四 vCPU、4096 MiB RAM 和 WHPX 不变。保留原固件，核实实际模式，不要假定窗口缩放请求会扩大桌面。macOS 完成关机前 SSH 可能先关闭；此时强制停止 QEMU，可能在下次登录产生异常关机警告。

Ubuntu console 验收要求配置的测试用户有真实 XFCE 会话。隔离 Xvfb 测试会话保持 display :99：自动分配可能在 LightDM 启动前占用 :0，阻止 console 登录。LightDM 的 user-session 和 autologin-session 均配置为 xfce；仅安装 XFCE 不会替换不可用的默认 ubuntu 会话。

## 运行时与会话失败边界

relay 用 IDLE、REQUESTING 和 UNKNOWN 建模创建。只有可解析的成功响应且 session ID 为非空字符串时，才发布会话归属。分发后的传输／解析失败进入 UNKNOWN；分发中断保持 REQUESTING。关闭这两种未解决状态时，先于本地输入清理抛出 CleanupUncertain，因此即使 HTTP handler 已将原错误转换为 502，环境管理者仍保留租约。不要从客户端断开推断远端已回滚，也不要枚举／删除任意上游会话。

运行时预检在创建磁盘前，将 platform 和 arch 与所选虚拟机 OS 及支持的 x64 target 比较。没有项目要求时也适用；准备流程在主机 hook 前检查基础配置。新安装／准备拒绝缺少 arch 的旧运行时归档。已有 run 路径保留已记录配置，不重新验证旧归档；用模拟 supervisor 和不变的磁盘／记录／归档字节测试，绝不能为此重启真实虚拟机。夹具必须是带 target 元数据的真实运行时 ZIP，不是任意字节。

虚拟机 hook 的 fingerprint v2 追加结构化、有序的原脚本标识和逐文件 SHA-256 列表，排除解析后的主机检出路径。没有虚拟机 hook 时，指纹继续是 requirements 文件 SHA-256，以保留兼容。绝不重写已有虚拟机存储指纹来绕过重新初始化。

归属套件覆盖模拟远端创建后的真实回环 HTTP 断开、畸形成功正文、缺失／无效 ID、中断请求、租约保留、分发前失败和已确认清理。hook 测试覆盖内容重新分配及独立于检出路径的指纹。准备测试覆盖 OS／架构不匹配，并断言预检失败时不执行磁盘命令或主机 hook。这些测试使用临时目录和本地模拟服务器，不要为运行它们启动或修复操作者虚拟机。

test-work-guests.py 的原生多 QEMU 冒烟须显式启用：只有原生进程启动已获授权时，才设置 QEMU_TEST_ACCEL（Windows 为 WHPX，Linux 为 KVM）。未设置时直接跳过，不启动 QEMU。没有默认 TCG 选项。可选冒烟当前使用固定转发端口，应串行运行；默认源码／客户端失败路径检查无需启动虚拟机。

## 结构化归属与初始化快照

TestEnvironmentOwner 通过私有 ExitStack 管理每种已配置执行模式：主机进程树，以及可能存在的临时工作区、SSH 传输和 Appium relay。本地／仅 Docker 模式不带 home 构造；acquire_lease(home) 在获取虚拟机资源前附加可选虚拟机预留。带 home 构造仍是直接作用域虚拟机使用的便捷方式。OwnerState 独立于是否存在虚拟机租约建模执行生命周期。租约获取失败不认领外部预留，第二次获取不能替换已持有预留。虚拟机资源通过 owner.callback／owner.enter_context 注册。主机 CommandTree.stop 回调在启动前注册，使管理者能在进程树清理替换原取消前观察到它。每次清理失败，包括中断，都会在下次清理前设置内存 RETAINED 并持久化 cleanup-uncertain。保留状态不可逆：后续异常或上下文管理器抑制都不能使其可释放。发布保留状态失败时预留不变，仍尝试剩余清理。普通测试失败后清理成功会释放活动租约；已变化或外部归属绝不覆盖／删除。CleanupUncertain 属于此管理模块；代理通过共享契约报告不确定，不管理租约。不要仅凭最终异常推断保留，也不要扫描异常链重建已丢失的归属状态。

配置式测试执行由 CliSignalScope、TestEnvironmentOwner 和传输共享一个 CancellationRequest。只有主线程能提交冻结 CancellationState、接受取消、消费 worker 事件、发布终态结果或修改租约状态。信号仅通过 CPython 可重入 SimpleQueue 排入不可变请求事件，不获取 worker 锁，也不抛异常。worker 排入观察和清理失败，再在 checkpoint 读取一次状态快照，绝不创建或替换共享取消。上下文本地清理屏蔽保护主清理上下文，不禁用已有 HTTP worker 的 checkpoint。

主线程消费由 fence 限定的有限队列前缀。begin_cleanup 插入接收 fence、关闭接收并进入 DRAINING：fence 前请求仍可接受，后续信号请求不能改变结果。先保留已接受取消；否则新到的主要执行中断优先于排队但未提交的 worker 观察。按队列顺序消费 worker 观察，若仍未接受中断，再接受首个合格信号请求。优先级由主线程决定，不是 worker 赋值竞态。DRAINING 期间已有 worker 仍响应已接受取消。FINISHED 冻结取消，迟到观察不能替换。

使用资源的 HTTP 分发在 relay 锁下注册 worker 作用域，嵌套 SSH／SCP／forward／stop 操作共享该作用域。每个作用域先发布观察和失败，再递减完成计数并释放 relay 锁；HTTP 错误转换发生在发布之后。分发控制中断返回固定 HTTP 错误，不泄出原始 worker traceback。关闭 relay 在 shutdown 前拒绝新工作，排空使用资源的分发。接收关闭后，迟到的请求体读取器不能进入资源工作。最终边界 seal_workers 关闭接收，确认资源 worker 数为零，并在释放租约前收集最终事件前缀。worker 排空未经确认则保留租约并报告不确定，不能据此允许成功或释放锁。

清理失败记录在独立于异常传播和 HTTP 响应的持续事件账本中。每次尝试停止传输子进程，都在资源边界报告失败；后续重试成功不会抹除。主线程管理者 checkpoint、callback-finally 边界和最终封口将报告收集到 cleanup_failures，持久化保留状态并继续排空所有回调。发布保留失败时预留不变，记录发布错误并保留原取消。只有 TestEnvironmentOwner 可创建、保留或释放虚拟机租约；worker 修改 owner／CLI 状态在 I/O 前即被拒绝。上下文抑制不能吞掉取消，也不能批准释放归属不确定的资源。释放是全部回调完成、worker 完成获确认、最终事件收集结束后的明确提交。EnvironmentCleanupError.failures 保留原失败和嵌套传输聚合，作为取消原因。

配置式执行中，defer_cancellation 和 TestCommandTree 适配器屏蔽 checkpoint，不安装或重放信号处理器。注册在下一 checkpoint 前完成。适配器复用权威 Windows／POSIX 进程树后端，不改变共享运行时。此执行上下文外，已有虚拟机管理命令保留旧信号延迟契约；此重构不改虚拟机生命周期命令。直接调用旧 owner／transport 的路径仍受已有等待期限约束。需要记录系统信号时，不要在没有 CLI 信号上下文的情况下使用协作式 owner。

test_environment.run 在本地、仅 Docker 和虚拟机模式使用同一 owner。main 将配置加载纳入一次 CliSignalScope.execute。checkpoint 位于获取虚拟机前、传输／转发／就绪注册后及进程启动前。CommandTree.stop 先注册后 start。主机命令在 checkpoint 间使用 wait(timeout=.1)，不进行第二次启动。就绪 HTTP 保留十秒超时，在调用前后检查。Appium relay 在线程启动前注册；close 可处理未启动服务器，不调用 shutdown／join，并在等待活动 worker 前拒绝新工作。清理绝不新增可能放弃已持有资源的 checkpoint。

GuestTransport 为 HTTP worker 和主线程捕获同一请求。配置式 SSH／SCP 使用一个明确管理的 Popen，以最多 .1 秒片段 communicate，同时保留原总操作超时。输入只在第一次 communicate 发送。转发就绪在 .1 秒等待间检查取消。短命子进程先注册再检查取消，返回前停止，构造器预检调用也如此。成功停止移除句柄；不确定停止保留句柄管理并抛 TransportCleanupError（CleanupUncertain 聚合）。先捕获原中断，避免 stop 错误将其替换。close 逆序尝试所有剩余子进程，报告全部失败。是否可释放虚拟机租约仅由环境管理者决定。配置式执行之外的旧调用保留 subprocess.run 行为。

CliSignalScope 只捕获一次冻结 CliSuccess／CliFailure，拒绝第二次调用。没有执行帧扫描、发布掩码、信号重放或交接重试。main 在最终化前离开执行异常处理器。CliResult 一次性快照退出状态与冻结 CleanupReport；后续输出只读该结果，不读可变归属或异常链。报告仅含固定类别／计数和已提交的 acquired-lease 状态，绝不含异常消息、自定义类型名、路径、命令参数或凭据。确认干净执行保留主机退出码；已接受取消即使清理失败仍保留原退出码；普通清理失败返回 1。已取得但未确认的租约打印保留锁恢复提示；本地／仅 Docker 不虚构虚拟机租约。stderr 已关闭或损坏不能改变状态。安装前先保存原信号处理器用于回滚；逆序恢复，SIGINT 最后，并完成中断的恢复。上下文本地取消在正常退出和失败时均恢复。

保持 QEMU_TEST_ACCEL 未设置，运行隔离回归：

```bash
python3 tests/test-cancellation.py
python3 tests/test-worker-protocol.py
python3 tests/test-environment-cli.py
python3 tests/test-environment-owner.py
python3 tests/test-transport-cleanup.py
python3 tests/test-test-environment-ownership.py
```

保留已有回归断言。套件覆盖仅记录处理器、不替换处理器的嵌套交接、启动前请求与等待中请求、全部执行模式、捕获／字节码边界重复信号、原取消身份与退出码、不可变终态快照、清理抑制、部分启动、子进程聚合、外部／保留锁、私有诊断、关闭输出和处理器恢复。worker-protocol 另覆盖确定性 checkpoint／commit 竞态、仅主线程修改状态和租约、取消优先级、并发失败生产者、请求接收 fence、嵌套 worker 完成、拒绝迟到工作、worker 未确认时保留、保留发布失败，以及固定 HTTP 中断响应。真实回环 HTTP 测试将 worker stop 失败转换为 502，最终 stop 重试再成功；无论普通失败还是取消，即使清理期间反复收到信号，都必须保留租约、原状态和已脱敏 io 计数。断言该路径所有元数据写入均在主线程。适配器使用模拟或本地假 HTTP 服务器。两个测试仅使用自行管理的主机 Python 夹具进程，验证进程树取消和 stdin 传递。不联系虚拟机、SSH 服务器或虚拟机服务。

InitializationSnapshot 捕获原 requirements 字节、独立 record JSON、暂存 hook manifest JSON，以及不可变的脚本名／字节元组。capture 只读取一次 requirements，同时用于解析和哈希；每个选定脚本也只读一次。apply 将快照附到安装配置；record_for 选择独立元数据用于预检和持久化。seed payload、cloud-init 包和尺寸都由同一快照推导，打包不重新读取脚本路径。load 保留为已有调用方的独立记录视图 API。持久记录仅含元数据／指纹，不含内存快照对象或脚本正文。带虚拟机 hook 的旧记录，没有捕获快照就不能生成新 seed。普通已有虚拟机 run 路径保留存储记录，不重建 seed。

快照保留 fingerprint v2 字节布局，包括无 hook 兼容规则。捕获后源码文件变化只影响后续捕获与未来新鲜度检查，不影响已在组装的 seed。不要修补已存虚拟机指纹或重置磁盘来适应源码变化。

运行 tests/test-environment-owner.py，覆盖通过真实 environment.run 接线的复合代理／传输失败、上下文清理错误、中断拆除、保留发布失败、外部归属及成功释放。运行 tests/test-initialization-snapshot.py，覆盖源码变更／删除、单次读取捕获、独立视图修改、Ubuntu／Windows payload、cloud-init 配置，以及实际持久记录与 seed 一致。这些套件仅用临时目录和模拟／本地夹具。普通回归不设置 QEMU_TEST_ACCEL，原生冒烟仍是单独显式启用项。

relay 在服务器 shutdown 或等待会话锁之前切换为 CLOSED，再于该锁下排空活动 worker，最后清理启动资源。先前已接受但关闭后才读完正文的 HTTP worker，必须在暂存文件或联系上游前拒绝请求。归属套件通过在请求体边界暂停的真实回环连接验证，不启动虚拟机或应用。

## 随包 Windows macOS GPU 依赖

`patches/reims-windows/sources.json` 固定三个公开源码修订及补丁哈希。补丁保留已测试的本地 Windows 移植：Reims 平台内存和 C API、metal2vulkan 运行时主机内存支持，以及 QEMU 的 WHPX／section 后备 RAM 集成。`reims_sources.py` 在检出前捕获 lock、补丁和构建模板，仅在全新缓存工作区应用。绝不能指向贡献者已有检出目录。Reims QEMU gitlink 有意不包含在补丁中；QEMU 根据同一 lock 单独获取和修补。插件 `.gitattributes` 将带校验和的补丁／驱动文件及 GPU 构建模板保持 LF，将 kext 二进制标为非文本。临时仓库在 `core.autocrlf=true` 下检出，16 个发布输入均逐字节不变；更新或分发时保留这些属性。三个补丁文件的空白例外用于保留 Makefile tab 前的 unified-diff 上下文前缀，以及末尾空白上下文行；普通源码仍执行正常空白检查。不要规范化补丁字节。

跟踪：[Windows 支持 #17](https://github.com/steelbrain/reims-vgpu/issues/17)和[已合并早期移植 #57](https://github.com/steelbrain/reims-vgpu/pull/57)针对早期架构，不是本补丁集。[内存问题 #71](https://github.com/steelbrain/reims-vgpu/issues/71)描述相关别名／导入失败。[QEMU #12](https://github.com/steelbrain/qemu-reims-vgpu/pull/12)包含相关 section 后备实现，但关闭时未合并；[QEMU #4](https://github.com/steelbrain/qemu-reims-vgpu/pull/4)跟踪其他 WHPX 修复。审查未找到匹配的 metal2vulkan Windows 运行时或详细时序问题。只有经审查的固定上游已具备相同行为，且干净构建与原生 GPU 验收通过后，才淘汰补丁。

`reims_runtime.py` 构建静态库和 EFI ROM，取得 Rust 原生链接依赖，渲染 pkg-config 元数据，并以仅 WHPX 构建 QEMU。复用已有 PE DLL 打包器和运行时文件／加速器验证。发布包含不可变 recipe 和上游许可证文本。失败或中断构建保留源码／输出证据；取消保留构建预留。独立运行时选择不能改变 Windows 虚拟机默认值，也不能静默回退 TCG。

`drivers/pvg-timing-fix` 包含独立 timing hook、已验收预构建 x86-64 kext、校验和清单与依赖许可证。重建时，按 `artifact.json` 的修订准备 [Lilu](https://github.com/acidanthera/Lilu) 和 [MacKernelSDK](https://github.com/acidanthera/MacKernelSDK) 干净检出，再于指定准备机运行其 `build.py --lilu-source ... --kernel-sdk ...
--output ... --clang <LLVM-23-clang++>`。Windows 生成 Mach-O 对象并保留 LLVM IR；最终在指定 macOS 构建机用 `xcrun ld -arch x86_64 -kext -undefined dynamic_lookup` 链接两个对象（macOS 上 `--link` 本地执行）。这不授予工作虚拟机构建权限。替换随包二进制前，审查 kext 导入和类型，有意识地更新产物清单并重新验收。每个新虚拟机内核构建都必须审查精确字节守卫，不得放宽以接受未测试 release。

EFI 准备将每个已验证驱动文件只捕获一次，放入不可变 `DriverSnapshot`；Lilu 校验和验证与 ZIP 解压消费同一捕获归档缓冲。镜像写入和 receipt 哈希使用这些字节，完成前回读驱动。输出镜像和 sidecar receipt 独占创建，任何输出创建前先拒绝 receipt／源码别名。失败尝试保留新建部分输出。

安装 `scripts/requirements-guests.txt` 后运行 `python tests/test-reims-runtime.py`，覆盖补丁校验和与捕获、合成仓库中实际 Git 补丁应用、运行时选择和环境隔离、不支持的构建以及真实 FAT 镜像保留。原生验证还要求干净公开源码构建、已验证产物／DLL 清单、使用生成固件的独立虚拟机、正常 CoreVideo 时序、可见 Metal present，以及不变的应用验收。不能把打包源码或加速器列表当作真实 GPU 测试。

2026-10-26，仅使用这些公开固定修订和随包补丁的全新检出／构建通过运行时／DLL 验证。先前空白盘安装的 24H32 系统隔离副本使用该运行时及随包准备器生成的 EFI 镜像，配置四 vCPU 和 4096 MiB RAM。两次正常虚拟机内关机／冷启动、原生桌面协调及后续只读验证通过。八个即时／定时 Metal 帧与帧缓冲颜色匹配；1800 个 CoreVideo 样本无超过 100 ms 的 target／clock 偏差。未改动的外部业务套件通过操作者管理的 Mac2 适配器，18 项测试全部通过，零失败／错误／跳过，会话／转发清理已确认。生成 Codex 包回归、运行时验证及随后原生桌面检查也通过。这验收的是可选 `reims-whpx` 路径，不代表任意主机 GPU、macOS release 或默认 Windows 虚拟机运行时。

另一副本在 ACPI 电源按钮请求与 SSH shutdown 竞争后停滞。已暂停并保留内存、磁盘及归属证据，根因尚未确认。成功冷启动验收使用单次正常虚拟机内关机请求，确认原生退出后才重启。不要声称 ACPI 关机或睡眠／恢复已验收。

## 已准备 Intel macOS 桌面恢复

Sequoia loginwindow 在普通安装完成前单独检查 `/var/db/.AppleSetupTermsOfService` cookie。一次诊断 macOS 15.8.1 启动在 `startosinstall --agreetolicense` 后仍保留该 cookie；即使账户、`.AppleSetupDone` 和自动登录配置有效，日志仍报告 `Setup launch
reason: terms and conditions`。清除 cookie 并重启后，桌面和认证 SSH 恢复。bootstrap 现会在最终重启前清除，与 [Setup Manager 部署发现](https://github.com/jamf/Setup-Manager/discussions/96)一致。该诊断修复本身不能证明干净无人值守安装。包 postinstall 仅在明确安装到当前运行目标时重新启用 first boot，允许升级包刷新已审查现有账户的配置，不改变密码。

`macos_desktop_plan.py` 在修改虚拟机前捕获私有 manifest、凭据和 setup 脚本字节。固定校验和的归档通过 SCP 流式传输；执行提供的 setup 脚本前检查虚拟机校验和。要求已有固定 SSH host key，以及已验证的 supervisor／QEMU／监听器身份。`macos_native.py` 管理具体 W3C 会话和新建 Finder 窗口；`macos_permissions.py` 选择无歧义、可见的 System Settings 控件，验证每次转换。`macos_console.py` 提供物理 QMP 输入，仅识别显式系统授权对话框以输入凭据。布局、OS build、签名身份未知或按键字符不支持时失败。

首次启动与桌面准备将测试账户 ByHost 屏保 idle time 设为零。仅 `pmset displaysleep 0` 无法阻止克隆测试桌面进入锁屏，即使 SSH 和 Appium 仍 ready。验收在创建任何原生客户端前检查 `IOConsoleLocked` 和匹配的 on-console 会话。克隆 lock cookie 使 loginwindow 在自动登录后仍恢复锁屏（`kLWLockFromCookieFile`）；只配置 idle time 无法清除已有状态。协调流程验证匹配 on-console 账户，以及 secure-input PID 的精确系统 loginwindow 可执行文件，找到已知账户标签旁唯一可见 `Enter Password` 字段，聚焦后重新检查目标，再通过 QMP 仅提交一次凭据。冷登录转换最多等两分钟；已验收四 vCPU 虚拟机超过旧 30 秒等待，随后无需再次提交密码便报告已解锁。原生验收前必须有真实 IORegistry 解锁状态。状态未知／歧义或 secure-input 进程未审查时，在输入前失败。验证绝不执行认证，不改变密码策略或系统管理的 lock cookie。保留早先失败测试的不确定归属。

已验收登录布局为 1920x1080 英文 Sequoia。分别在窄裁剪中识别账户标签和低对比占位文字，绝不用裁剪假定位置盲点密码框。Tesseract TSV 解析必须禁用 CSV 引号处理，因为识别出的引号是原始文本，否则会吞掉后续行。输入前立即复查目标，避免变化或已解锁的 console 收到凭据。System Settings 授权另行识别唯一密码标题和完整授权消息。低对比占位文字／按钮在同一捕获的 1920x1080 帧中分别裁剪；裁剪位置只约束 OCR，输入使用识别出的字段边界。聚焦后，要求匹配已解锁 console 的 secure-input PID 属于测试账户下经审查的 System Settings 或 SecurityAgent 可执行文件；输入一次前重新核实完整提示、PID、可执行文件及进程启动时间。缺少 AX 字段不允许盲输，该路径同样必须做 OCR 字段和 secure-input 检查。

新窗口改变快照层次时，Finder 元素 UUID 可能变化。`macos_windows.py` 通过内置 JavaScript／Objective-C 桥接和 CoreGraphics 读取稳定 WindowServer 窗口编号，不使用 Apple Events；排除桌面层和窗口标题。验收只将自己新建窗口与原生几何匹配，验证实际系统几何及窗口消失，要求所有既有窗口和矩形不变。

准备好的 WDA 必须独立于 Appium 驱动所管理的进程生命周期。LaunchAgent 运行 test-without-building，每个新 Mac2 会话明确使用 webDriverAgentMacUrl。TestEnvironmentOwner 管理预留和隧道。创建响应缺失／畸形或具体删除失败时保留租约。只有资源清理和虚拟机身份重验证完成后才发布就绪；竞争租约不能覆盖已有桌面 receipt。

WDA 缓存 Accessibility 信任，因此协调从全新 runner 和实际原生验收开始。只有 Accessibility 失败才移除并重新注册已审查授权；已启用且有效的授权不动。runner 缓存可信访问时撤销有效授权，可能使原生快照失效；修复后验收也需新 runner。`launchctl kickstart -k` 只替换 xcodebuild 包装器，可能留下 testmanagerd runner app 监听同端口。`macos_wda.py` 先卸载指定 job，将剩余监听器匹配到经审查 bundle 可执行文件、账户和启动时间，立即重新核实身份后才发 TERM，确认退出，再重新加载 job。不向未审查监听器发信号。关闭／重启未经确认则保留归属；不用宽泛进程名扫描或 kill。就绪等待拒绝旧监听器 PID。受保护 TERM 失败时，只有新一次确认原 runner 已不存在才允许重启；替代进程或未知进程探测仍失败。

`TestEnvironmentOwner.on_drained` 在全部注册资源和 worker 完成后、释放虚拟机租约前，运行一次终态元数据回调。`DRAINED` 禁止新资源归属。桌面成功与失败 receipt 使用此边界，均不在离开 owner 后写状态。发布前复查租约身份，发布失败保留归属。即使写 receipt 后释放失败，保留租约仍是权威状态。

审查修复通过确定性输入替换、输出路径冲突、租约发布和凭据目标回归检查。原生 24H32 授权探测强制走 OCR 路径，两次确认 secure-input 身份，仅提交一次凭据，到达文件选择器且不改已有授权。公开协调命令和真实 EFI 副本准备也通过。上文完整 18 例业务结果早于这些管理修复，未为其重跑。

运行 `python tests/test-macos-desktop.py`，覆盖合成 manifest、输入、目标选择和会话归属约定。原生安装／冷启动／UI 与使用项目验收分开，记录所选 release 和准备资产哈希。此套件不启动虚拟机。

运行 `node --test tests/test-prepare-runtime.cjs`，覆盖首个扩展缓存创建，以及已有注册保留／重定位。server-only 归档在首次启动前没有 Appium 扩展缓存是合法情况；离线准备器添加首个扩展时创建 schema revision 4。

一次干净 Intel macOS 15.8.1（24H32）运行以四 vCPU 和 4096 MiB RAM 完成安装、自动登录、已准备运行时部署、原生 Accessibility 修复和两次冷启动，全程无需手动交互。准备资产含 Xcode 16.2（16C5032a）和 Mac2 4.5.0；虚拟机未运行 WDA 或应用构建。配合另行提供的实验显示运行时，八个即时／定时 Metal 帧匹配实际帧缓冲颜色，1800 个 CoreVideo 样本无超过 100 ms 的 target／clock 偏差。这些 GPU 结果不能证明插件默认受管理运行时具备 GPU 支持。未改动外部桌面业务套件随后通过操作者管理的 Mac2 启动适配器，18 项全部通过，零失败／错误／跳过；此适配器独立于插件 Windows／Ubuntu 透明 JVM relay。完整生命周期发布验收前，已清理虚拟机会话、应用包和 SSH 转发；虚拟机保持运行，测试租约释放。

## Ubuntu VirGL／WHPX 运行时

`scripts/virgl_runtime.py` 构建可选 Ubuntu 运行时，不使用私有实验二进制。不可变快照捕获 `patches/viogpu-windows/sources.json` 中公开 QEMU 和 VirGLrenderer 固定版本、已检查补丁字节、两个 WHPX 补丁，以及 `templates/build-virgl-whpx.sh`。不会为 Ubuntu 构建或安装 Mesa Windows 虚拟机驱动。缓存身份包含这些捕获输入；归档在私有位置复制，解压前验证 SHA-256。recipe 变化使用独立缓存目录。忙碌／中断构建保留预留，直到检查完成。完整运行时包含递归 DLL 依赖、固件、源码许可证和捕获的 recipe。

显式主机准备使用 Windows 11 x64 和 Python 3.12+：

```sh
python scripts/virgl_runtime.py --msys2-root C:/msys64 --jobs 8
```

可选 `--cache-dir`、`--qemu-archive` 和 `--virgl-archive` 选择私有存储和已下载固定归档。profile 启动需要其他缓存（包括含空格的 home 路径）时设置 `QEMU_VIRGL_CACHE`；显式构建与虚拟机命令须用同一缓存。MSYS2 安装所需 UCRT64 编译器、Meson、Ninja、SDL2 和 libepoxy。不替换系统 QEMU。验证要求仅 WHPX、VirGL 设备、隐藏 SDL 选项，以及每个随包文件哈希匹配。枚举加速器或设备不能证明真实 GPU 渲染。

`guest_seed.py` 在共享桌面会话模板中选择显示配置片段。GPU 片段继承 LightDM 的 DISPLAY／XAUTHORITY，默认片段仍管理 Xvfb／Openbox。GPU 自启动使用私有 D-Bus 会话和已有临时解锁 keyring。`guest_gpu.py` 拒绝软件渲染器和尺寸不符，再发布 boot ID 与会话 PID／启动时间 receipt。验收检查当前 receipt，以及已有 Java、桌面和 Appium 要求。安装记录包含 GPU 后端，防止仅改 profile 就采用软件渲染磁盘。首次验收仍要求 cloud-init 完成；已记录安装成功后，冷启动保留桌面检查，不再要求一次性 NoCloud seed 持续连接。

不启动任何虚拟机，运行隔离回归：

```sh
python tests/test-virgl-runtime.py
python tests/test-desktop-provisioning.py
python tests/test-whpx-runtime.py
python tests/test-guest-panel.py
python tests/test-work-guests.py
```

原生验收必须使用全新状态目录、构建出的受管理运行时，以及未改动使用项目的运行时要求。要求硬件 renderer 输出、实际渲染颜色回读、原生 Appium source／input 与截图，之后正常关机／冷启动，再运行未改动业务套件。日志、介质、profile 和账户数据保持私有。原生 Appium 截图支持仍由项目正常驱动负责。

`patches/qemu-11.1.2-sdl-gl-snapshot.patch` 为没有 CPU surface 的 console，在 QMP screendump 添加可选 SDL GL 快照回调。PNG 编码可能 yield 前，在主线程将当前 scanout 读入自行管理的 pixman 镜像。回读按需执行，完成裁剪／方向转换，并恢复 SDL context、读取 framebuffer／buffer 和 pixel-pack 状态。读取失败绝不发布图像。已有 CPU-surface 捕获保留原路径。补丁进入 recipe，旧运行时不能复用于面板捕获。

在已登录 Windows 桌面，从实际修补后的 QEMU 源码树验证辅助程序，不启动虚拟机：

```sh
python scripts/test-qmp-snapshot-native.py --qemu-source /private/build/qemu-11.1.2 --output /private/native-snapshot
```

原生回归检查 40 例，覆盖方向、裁剪、尺寸、填充行、已绑定 pixel-pack buffer，以及 GL 失败和恢复。还将 pack-state 规范化做变异负对照，要求回归检测出错误。虚拟机验收须将实际 QMP PNG 与原生截图比较，执行暂停／恢复与显示缩放，并在未改动业务测试期间持续通过注册的屏幕工具捕获。释放测试租约前，在清理中恢复显示模式并恢复虚拟机运行。

## 实验性 viogpu 源码包

`patches/viogpu-windows/sources.json` 锁定源码修订／归档哈希、补丁字节，以及每个修改文件的前后哈希。源码包括 QEMU 11.1.2、VirGLrenderer 1.3.0 和固定的 `arehnman/virtio-win-mesa` 修订。VirGL 补丁先包含两个 MSYS2 1.3.0 构建兼容变更（`void` 原型和条件 `sys/ioccom.h` include），再包含功能性回读修复。分发构建时保留上游许可证声明；不随包提供第三方二进制、私有 profile、原始应用日志或凭据。

### 准备与验证

下载 lock 指定归档，解压前验证 SHA-256。使用全新 LF 源码检出，绝不修补操作者工作目录。验证器在临时目录检查捕获字节，不修改提供的源码路径：

```sh
python plugins/qemu-guests/scripts/verify-viogpu-bundle.py \
  --qemu-source /private/src/qemu-11.1.2 \
  --virglrenderer-source /private/src/virglrenderer-1.3.0 \
  --mesa-source /private/src/virtio-win-mesa
```

没有源码参数时，仅验证包完整性，不验证适用性。验证后，在各全新源码树中用 `git apply` 应用相应随包补丁。QEMU 还需要已有插件管理的 WHPX partition reset 和 CET／XSAVE 补丁；GPU 补丁修改其他文件。隐藏开关必须在创建窗口前设置 SDL_WINDOW_HIDDEN。设备 reset 仅在 vCPU 线程标记待处理工作；scanout／GL 清理由主循环负责。

在装有 GCC、Meson、Ninja、pkgconf、Python／PyYAML、libepoxy 和 SDL2 的 MSYS2 UCRT64 主机 shell 构建修补后的 renderer：

```sh
meson setup /private/build/virgl /private/src/virglrenderer-1.3.0 --buildtype=release --wrap-mode=nodownload
meson compile -C /private/build/virgl
```

按已有 WHPX 主机 recipe 构建 QEMU，增加 `--enable-sdl`、`--enable-opengl` 和 `--enable-virglrenderer`，链接修补后的 renderer。保持 `--disable-tcg`。将可执行文件、DLL 依赖和固件打包到独立私有运行时，绝不覆盖系统 QEMU。虚拟机 Mesa DLL 在主机使用 MSVC、Windows SDK／WDK 和 Meson 构建：
`-Dgallium-drivers=virgl -Dgallium-d3d10umd=true -Dgallium-wgl-dll-name=viogpu_wgl
-Dgallium-d3d10-dll-name=viogpu_d3d10 -Db_vscrt=mt -Dllvm=disabled
-Dvulkan-drivers=[] -Dvideo-codecs=[] --buildtype=debugoptimized`。
这些是主机构建前提，不是测试虚拟机中要安装的包。

### 归属与回归约定

虚拟机 clear 操作独立于 framebuffer 绑定管理自己的 view：借用匹配的已绑定 handle，否则创建／清除／删除临时 surface。回读适配器管理 layer 遍历和虚拟机偏移。每个 layer worker 管理紧密排列的临时 buffer，只转换有效像素，再按虚拟机 row／layer stride 分散写入。D24S8 和 Z24X8 使用整数位变换。这增加逐 layer 分配／复制，吞吐尚未基准测试。GL read 失败必须在转换／发布前返回错误。恢复 read 和 draw framebuffer 绑定。根据 capability 选择备用 texture 路径，不能在失败后将其当作重试。多重采样资源要求显式 resolve。后续 layer 失败不会回滚先前成功发布的 layer。

不启动虚拟机，运行静态完整性／失败测试：

```sh
python plugins/qemu-guests/tests/test-viogpu-bundle.py
```

原生图形回归在已登录 Windows 主机执行，PATH 包含 UCRT64 DLL 和编译器，输出目录必须全新：

```sh
python plugins/qemu-guests/scripts/test-viogpu-native.py \
  --virgl-source /private/src/virglrenderer-1.3.0 \
  --virgl-build /private/build/virgl --output /private/results/viogpu
```

它在主机构建测试并创建隐藏 SDL 窗口，执行 24 项精确回读（D24S8／Z24X8／RGBA8、mip、多 layer、拆分 iovec、偏移、row／layer padding 和上传源不变）、五项 read-error／恢复检查，以及 WARP 上的 D3D clear 隔离。Z24X8 包含零、一、255、256 和最大的两个深度值。clear 隔离在十一轮 clear 后逐次检查八个子资源，包括部分 array 和独立 depth／stencil clear。负对照扩大 clear 范围，必须报告 144 个不匹配并退出 1。`results.json` 标识测试 DLL；失败保留构建和用例日志。

虚拟机硬件验收只暂存预构建的 `clear-isolation.exe`，在专用交互测试会话中用私有日志路径运行，再以 `warp` 重复。保留退出码和新日志。虚拟机驱动注册表条目保持 multi-string，保留原条目数和绝对路径。选择不同的修补 DLL 名前，备份原注册表值和 DLL。不要替换已加载主机 DLL：只平稳停止自己管理的虚拟机，替换私有运行时文件、记录哈希再冷启动。回滚使用同样 stop／restore／start 顺序和原虚拟机注册表快照。

Java 测试应用若加载系统 EGL／GLES 而非随包 ANGLE，使用仅限测试启动作用域的空 `java.library.path`，确认实际加载模块。不要将此变通处理强加到全部 Java 进程或全部使用项目。使用正常运行器管理的临时 Appium 连接；本包不包含持久隧道服务。

### 验收限制

干净随包 VirGL 源码已重建并通过原生回归。等效实验运行时通过虚拟机硬件／WARP clear，以及两个带截图的代表性使用项目桌面 E2E 用例。更早 renderer 通过过完整 18 例套件和热重启恢复，但那些结果不能验收最新 DLL。实验已验证隐藏启动和主线程 reset。本次验证干净源码上的 QEMU／Mesa 补丁应用；它们曾在实验中构建，本次打包检查未重新构建。

这是 Windows x64 原生 OpenGL，虚拟机 D3D feature level 10.0／ANGLE ES2。不代表 GLES、全部格式、主机注销／session 0、主机开机自启、全新镜像无人值守 GPU 安装或长期可靠性已验收。另一个先前存在的默认窗口 OpenGL 回读问题不在本包范围。使用项目验收产物保持私有；验收新构建的完整运行时时，重跑完整套件、截图和热恢复。

## 离线 Shell 边界回归

从 `me` 源码检出目录运行 Python 套件，其中可用共享夹具与命令归属运行时。前提、约定清单和保留的平台测试见[仓库开发文档](../../DEVELOPMENT.md#shell-边界回归测试)。
