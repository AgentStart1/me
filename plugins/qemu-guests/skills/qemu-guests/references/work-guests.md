# 工作客户机准备

遵循 SKILL.md 中共同的项目独立性、构建位置和资源归属规则。下方路径相对于已安装插件根目录，从使用插件的项目调用前先解析绝对路径。

## 安装与连接

使用 `scripts/guest-vm.py install|run|stop|status|plan <guest.json>`。客户机 JSON 配置与 Alpine `.profile` 不同。多个工作虚拟机可以同时运行，各自使用独立状态目录、磁盘、租约及宿主机 SSH 端口。不在工作客户机安装 Docker 代理或后端凭据；宿主机 Docker、Testcontainers 保持独立。

Ubuntu 使用经过验证的 cloud-init 镜像。Windows 使用适合兼容介质的 BIOS/MBR amd64 无人值守应答文件。介质、运行时归档及准确配置字段见[安装说明](../../../README.md#安装与运行)；不支持的安装器使用[自定义适配器](../../../README.md#自定义无人值守适配器)。Intel macOS 在规划或安装前先阅读 [macOS 准备](macos.md)。

在与目标操作系统和 CPU 架构匹配的指定准备环境中，通过 `scripts/build-appium-runtime.py` 准备 Appium。显式固定项目所需驱动版本（Windows 桌面示例：`--driver appium-desktop-driver@2.8.0`）。在配置 `appium` 对象中提供归档、校验和和唯一宿主机端口。通过 `scripts/connect-appium.py` 连接，首次核对 SSH 主机密钥指纹。Windows 使用持久自动登录测试账户及交互登录任务，让应用只在客户机桌面打开。应用产物暂存和后端连通性由项目自身测试工具安排。不得将项目路径、应用包、测试命令、凭据或特定项目 SDK 固化到本插件中。

准备时通过 JSON `graphical` 布尔值选择桌面组件（Ubuntu XFCE/LightDM，或 Windows Server Desktop Experience，相对于 Core）。图形客户机设置不同且仅监听回环的 `qmp_port`，供面板只读捕获。无显示的 macOS 也需要私有 QMP 执行 Recovery 自动化。捕获支持缺失时先调查，不要仅为填充面板就修改运行中客户机。

新安装前验证运行时平台和 x64 架构，不根据宿主机系统推断，也不接受缺失元数据。保留已有记录：客户机钩子指纹 v2 要求旧钩子环境独立重新初始化；不含客户机钩子的指纹仍兼容。不通过重置磁盘或修补指纹来迁就变化的要求。

## Windows 受管运行时

Windows 11 x64 上默认使用四个 vCPU 和 `qemu_runtime: "whpx-reset"`。`install`、`run` 构建或验证受管 QEMU 11.1.2 运行时，包括私有 DLL 和固件；只编译 WHPX。使用 Python 3.12+ 和 MSYS2 UCRT64（非标准宿主机位置通过 `QEMU_MSYS2_ROOT` 指定）。可提前用 `scripts/whpx_runtime.py` 准备。`plan`、`status`、`stop` 从不构建。受管运行时保留已测试的 `Westmere,-vmx,-svm` CPU 参数，不显式覆盖 `qemu`，也不配置 `install_reboots` 冷启动预算。Linux 宿主机配置必须显式选择系统运行时和 KVM。

受管运行时来源、构建恢复和验证见 DEVELOPMENT.md。随包本地分区重置补丁改编自上游提案；原版 11.1.2 在已测试宿主机上仍失败。CET/XSAVE 补丁还按所选模型及客户机 XSAVE/XSAVES 支持限制 WHPX CET 位；不得在 Westmere 重新启用宿主机 CET。除启动就绪外，也验证客户机实际标志；调查 init panic 时私下保留崩溃磁盘和 RAM。不隐式替换系统 QEMU。缓存运行时执行前检查哈希，构建配方变化使用独立缓存。

修改运行时实现或重启验证时，另读[维护与验证](implementation-maintenance.md)。运行时就绪与所请求的应用测试结果分别判断。

## Windows 上的 Ubuntu GPU

Windows 11 x64 上的 Ubuntu OpenGL 使用可选受管 `virgl-whpx` 运行时和 `profiles/ubuntu-virgl-whpx.json`。阅读所属 README 的 Ubuntu GPU 章节。通过 `scripts/virgl_runtime.py` 构建固定版本公开源码；不得用缓存的私有实验二进制替代或覆盖系统 QEMU。使用项目可移植 `--requirements` 在全新状态目录安装；不通过改配置把已有软件渲染磁盘转换为 GPU 环境，也不伪造初始化回执。

生成的 GPU 会话继承专用 Xorg 控制台，保留隔离的 D-Bus、AT-SPI 及临时解锁的原生密钥环。要求当前启动和会话回执、硬件 VirGL、实际渲染、原生 Appium 输入和截图，再验证未经修改的业务验收。即使 SDL 隐藏，也要求宿主机桌面已登录；会话 0、注销和宿主机开机自启动尚未验证。受管运行时通过按需扫描输出快照支持面板 QMP 捕获；对照原生 Appium 截图验证方向、颜色和当前尺寸。CUDA、Vulkan 和视频解码未验证。源码重建、失败回归和冷启动验证见 DEVELOPMENT.md。

## 实验性 Windows viogpu

仅提供源码的隐藏 SDL/VirGL 实验见 DEVELOPMENT.md 的 viogpu 实验章节。在准备隔离源码和运行时目录树前，通过 `scripts/verify-viogpu-bundle.py` 验证固定版本包。不提供新受管运行时名称或无人值守客户机驱动安装。

客户机 GPU 配置、签名选择、修补二进制和回滚状态留在使用插件的项目外。不改变宿主机 Secure Boot。使用现有测试运行器管理的临时 Appium 传输；隐藏显示仍要求客户机桌面已登录。SSH 就绪、旧 DLL 的热重启或早先全套测试结果，都不等于当前 GPU 验收通过。
