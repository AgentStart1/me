# 宿主机驱动测试

阅读[统一入口](../../../README.md#统一测试环境入口)，以及下方符合项目运行时和传输需求的章节。复用项目已有命令，遵循 SKILL.md 的构建位置与项目独立性规则。

## 运行需求与初始化

可移植依赖需求留在项目中：Java 和 Appium 版本、正常驱动或插件依赖、系统运行库、预构建原生 classpath 坐标及桌面尺寸。虚拟机硬件、介质、SSH、加速器设置、预构建包位置和操作者启动命令留在项目外。通过 `scripts/prepare-appium-runtime.py` 打包已准备的本地扩展、预构建产物及 Windows 宿主机编译的显示辅助工具。`--requirements` 配合 `--platform` 还会执行项目声明的宿主机准备钩子。使用 `scripts/guest-vm.py install <private-profile> --requirements <project-requirements>` 自动配置桌面。新初始化 Linux 客户机提供已准备的 JDK 和原生元数据，无需私有 Linux 传输覆盖。

项目 `hooks.host_prepare` 可在宿主机构建、下载或暂存。`hooks.guest_setup` 可在离线运行时解包后执行自包含初始化脚本，使用显式参数和有限超时。运行前审查脚本。客户机钩子遵循共同构建位置规则，配置运行状态和安装预构建依赖。不得将项目脚本或命令编码到本插件。钩子失败或超时时终止并保留私有日志，不跳过失败初始化。运行 E2E 前准备完全部共享宿主机产物，UI 测试运行期间保持不可变。

大型归档不放进 cloud-init YAML，改为从只读介质解包 seed 载荷。轮询 cloud-init 状态，不创建长期等待进程。通过受监督、归 QEMU 管理的监听器验证 SSH 主机密钥固定值，保留每台虚拟机的指纹供后续连接。隔离 Linux 测试显示与面板中的控制台帧缓冲不同。

## 执行与收集结果

已配置的宿主机测试使用 `bash scripts/run-test-env.sh --config <project-environment.json> -- <host test command>`，连接 Docker 和／或客户机 Appium 传输。连接通过操作者管理的 `TEST_ENV_DOCKER_PROFILE`、`TEST_ENV_GUEST_PROFILE` 提供；项目 JSON 声明可移植工作区、属性、文件或目录、清理与启动角色，包括可选预构建 `artifacts`。旧 `run-testcontainers.sh` 为兼容性转发到此入口。

代理适配器支持带引号的 JVM 参数文件，覆盖 Windows 宿主机到 Windows 客户机，以及 Windows、Linux 宿主机到 Linux 客户机。宿主机编译后暂存 classpath、JDK 和 agent 产物，镜像私有输入和输出，转发声明的回环服务端口，保留应用重启之间的客户机状态，并将输出收回原宿主机路径。绝不将宿主机 Windows JDK 发到 Linux。不支持的适配器应失败，不猜测。透明 `java-argfile` 中继不支持 macOS；该目标使用操作者管理的预备 Appium 启动适配器。

已准备或自定义 Linux 环境可使用操作者管理的 `TEST_ENV_LINUX_RUNTIME` 覆盖，包含专用 POSIX 镜像根目录、已有客户机 Java 可执行文件、预构建宿主机原生 classpath 补充项，以及可选 Appium 端口。在项目外准备隔离的图形 Appium 会话、D-Bus、AT-SPI 和已解锁测试密钥环。映射声明角色和 classpath，将启动 capabilities 发给客户机 Java 运行时。原生诊断通过应用机器上的 Appium 执行，不让客户端在本地附加客户机 PID。

## 失败与清理

使用不启动远程 Shell 的 SSH 转发通道，确认每项转发应答；不要让远程 Shell 持续等待 stdin。Windows SSH 脚本保留在有界 stdin 传输上，不把越来越长的产物列表内联到编码命令行参数。输出交接失败时回滚新建 Appium 会话，删除结果不确定时保留管理责任。

Appium 创建响应丢失、损坏或中断时，保留清理不确定的租约和私有输入，直到操作者确认远程清理。不得批量删除会话或自动清除租约。保留私有失败日志，分别报告原测试结果和未确认清理。

修改代理、传输、初始化快照或取消代码前，阅读[维护与验证](implementation-maintenance.md)。
