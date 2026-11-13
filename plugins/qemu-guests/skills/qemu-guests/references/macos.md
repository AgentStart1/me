# Intel macOS 准备与恢复

安装前阅读 [macOS 安装要求](../../../README.md#intel-macos-无人值守安装)。遵循 SKILL.md 的共同构建位置与资源归属规则；只选择安装、Appium、GPU 或桌面恢复所需章节。

## 安装与介质

Intel macOS 使用已准备的 Apple 安装介质和 bootstrap product package：通过有限 OCR 等待 Recovery，键盘自动化打开 Terminal，挂载脚本对显式配置的空客户机磁盘调用 `startosinstall`（选择序列号时按序列号匹配）。包的 postinstall 钩子只在运行中的目标上显式加载首次启动任务。首次启动配置用户、已有 SSH 访问组成员关系、用户设置偏好及 Appium 用户级 LaunchAgent，将标准仿真 USB 键盘预设为 ANSI，在启用持久自动登录前清除安装器一次性自动登录标记，然后重启。使用 macOS 准备脚本构建私有 product package 和 ISO。不声称支持 Apple Silicon IPSW 或任意版本。自定义系统仍需明确自动化与验收。不以点击安装器替代无人值守安装，准确报告缺失前提。

Windows 可通过 OpenCore macrecovery 工具下载 Apple Recovery 镜像，并对照 Apple 签名 chunklist 验证；下载 Recovery 不要求已有 Mac。须区分 Recovery 下载与当前适配器所需的完整安装应用、ISO 及私有 product package。Windows 示例显式选择 WHPX；Linux 使用 `profiles/macos-kvm.json` 的系统运行时和 KVM。CPU 参数和私有 OpenCore、固件仍依具体版本而定。

Linux/KVM 的准备边界见 README 的 [Linux KVM 上的 Intel macOS](../../../README.md#linux-kvm-上的-intel-macos)。Intel 在此描述客户机平台，不能据此排除 AMD KVM 宿主，也不能直接套用 AMD 裸机内核补丁。先验证选定虚拟 CPU，依据串口和宿主 KVM 诊断定位实际失败；不自动修改共享宿主 MSR 策略。保留原始固件与系统盘，使用独立副本验证桌面及预构建 WDA 的原生输入。

历史 Sonoma、CPUID 缓存和 Mac2 探测记录在[开发证据](../../../DEVELOPMENT.md#whpx-上的实验性-macos-recovery)中。它们不能证明其他版本兼容，也不能证明源码适配器完整无人值守运行。不用实验二进制替换受管运行时，不悄悄回退 TCG，不将 Recovery 下载报告为安装完成。

使用 GPT 安装磁盘（准备工具中的 GPTSPUD），以只读 USB 挂载；不能把分区 Apple 镜像当作 ISO9660 光盘。配置 OpenCore 自动引导安装器或目标，并隐藏自身 EFI 条目。解析 startosinstall 的实际 Recovery 挂载路径及明确为空的目标盘；优先使用配置的 QEMU 磁盘序列号，因为 BSD 磁盘号可能随启动改变。宿主机 OCR 使用固定版本 Pillow 放大帧，再严格匹配提示。Windows 生成的 Shell seed 必须保留 LF。

首次启动要求 FileVault 关闭，以仅 root 可读权限发布专用账户 loginwindow 凭据，安装 Appium LaunchAgent 后重启。不得为满足配置而关闭加密。验收必须确认认证后的 SSH、预期控制台用户、其已加载 Appium 服务及就绪回环端点。交接标记不等于安装成功；保留并调查失败，不重复破坏性命令。

Sequoia 中，即使存在 `.AppleSetupDone` 和持久自动登录，遗留的 `/var/db/.AppleSetupTermsOfService` cookie 仍可能强制打开条款页。首次启动模板对已使用 `--agreetolicense` 的安装清除此独立 cookie。不以点击条款页替代在独立空磁盘上验证修正后的 bootstrap。

## Appium 与显示前提

Mac2 UI 会话需要兼容的完整 Xcode、已准备的 WebDriverAgentMac 构建，以及为构建出的 runner 和 Xcode Helper 授予的辅助功能权限。只有 Command Line Tools 不够。允许 Mac2 调用 xcodebuild 前，必须获得明确的客户机内构建授权；否则使用指定构建环境及预构建 WDA 端点。真实原生会话、source、截图和点击须与服务就绪分别验证。macOS 未选择开发工具链时，保留启动器的缺失工具处理，避免可选 Git 修订探测打开开发工具安装器。不能仅为此探测安装构建工具。

基础 macOS 帧缓冲可能只暴露启动时选定模式；必要时修改私有 OpenCore UEFI Output Resolution，保留原配置，重启并验证实际模式。macOS 可能在内核关闭前断开 SSH；不能仅凭断开证明关机完成，应等待客户机结束后再强制退出自己管理的 QEMU 进程。

## 受管 GPU 运行时

对于已验证的 Windows 11 x64、Intel macOS 15.8.1 GPU 路径，使用随包 `qemu_runtime: "reims-whpx"` 配置和 `scripts/reims_runtime.py`，不用缓存私有实验二进制或相邻源码检出目录。此运行时与 Windows 客户机 `whpx-reset` 分开。依赖版本和补丁位于 `patches/reims-windows`；首次使用通过 GNU Rust 和 MSYS2 UCRT64 构建公开源码，并验证完整运行时。通过 `uv run scripts/prepare-macos-gpu-boot.py` 创建新的操作者自有 EFI 副本，使用随包、带保护的时序修正和固定版本 Lilu；要求系统构建 24H32。不修改运行中启动镜像、不覆盖固件、不绕过失败的驱动哈希或构建保护，也不声称支持新的 macOS 版本。指定准备机器要求见 [GPU 前提](../../../README.md#windows-上的-macos-gpu-运行时)及[驱动构建说明](../../../DEVELOPMENT.md#随包-windows-macos-gpu-依赖)。要求实际时钟、帧缓冲和未经修改的业务验收；原生 SDL 呈现和视频解码未验证。

冷启动验证只发出一次正常客户机内关机请求，确认原生进程退出后再启动；不要让 ACPI 和 SSH 关机请求竞争。应用测试使用[宿主机驱动测试](test-execution.md)中的 macOS 传输边界；GPU 运行时不提供透明 `java-argfile` 中继。

## 已准备桌面的恢复

Intel macOS 新装或明确升级后的桌面恢复，阅读 README.md 的已准备桌面章节，使用 `scripts/macos-desktop.py prepare|reconcile|verify <guest.json> --plan <private-desktop.json>`。计划冷启动前使用 prepare；它不发布桌面就绪。要求已审查的准确 OS 构建、bundle 标识和 CDHash、固定版本产物及独立预构建 WDA LaunchAgent。使用 `webDriverAgentMacUrl`，绝不使用 Appium 管理的 WDA 进程或 build-for-testing 回退。脚本、凭据 ZIP 和特定 GPU、业务检查留在使用插件的项目外。源码 WDA 模板只执行 test-without-building。

修复权限前，用新审查的 runner 探测实际访问，保留可用授权。缺失辅助功能权限通过原生 System Settings 控件及严格识别的认证流程重新授予；不编辑 TCC，不关闭系统安全机制。桌面就绪前要求实际输入读回、原生窗口几何、截图和确认清理。冷启动验证及未经修改的业务套件，与 SSH、Appium 就绪分别判断。

冷启动前准备专用账户，避免空闲锁屏。原生输入前要求已验证解锁、且匹配的控制台；不绕过已有锁，不把 SSH、Appium 就绪视为 UI 已解锁。协调恢复只可在确认匹配的锁定控制台、系统 loginwindow 安全输入进程和可见密码框后，进行一次正常账户登录。不得删除锁定 cookie 或削弱认证策略；验证模式不得认证，必须要求实际解锁状态。

权限授权要求恰好一个已识别密码字段，以及测试账户内经审查的 System Settings 或 SecurityAgent 进程持有安全输入；输入一次前重新核实提示和进程身份。不得用仅 OCR 文字或向当前焦点盲目输入替代这些检查。资源和 worker 清理后、仍持有客户机租约时，发布终态桌面回执；即使旧回执阶段显示完成，保留租约也始终需要检查。

保留归属不确定的会话租约；操作者恢复前检查具名资源，不批量删除会话或抢占预留。

除 WDA 外，还要求与 CPU 匹配的完整 Mac2 运行时；只有服务的 Appium 归档可以显示就绪，但不包含任何驱动。桌面控制器在创建会话前导入已准备的 Mac2 入口。将验证迁往新的独立客户机时，保留诊断失败和保留归属记录。
