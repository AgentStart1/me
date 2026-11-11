# Alpine 后端配置与恢复

本参考适用于 Alpine `.profile`，不适用于工作客户机 JSON 配置。遵循 SKILL.md 中共同资源归属规则。

## 配置与端口

配置为字面 `KEY=value` 文件，不得含 Shell 展开。必需网络设置：

- `SSH_PORT`
- `DOCKER_DAEMON_PORT`
- `TESTCONTAINERS_PORT_START`
- `TESTCONTAINERS_PORT_END`

生命周期选项只从选定配置文件读取，不继承进程环境。缺失可选值使用下列默认值。`BOOT_TIMEOUT` 为 SSH 就绪超时秒数，默认 300。`FORCE=true` 跳过平滑关机，默认 `false`；`TIMEOUT` 限制平滑关机等待秒数，默认 30。

结束值 `auto` 在两个平台都从所配起始端口选择 128 个端口，默认 20000–20127。自动端口池超过 65535 会被拒绝；显式数字范围不设数量上限。客户机内核要求端口池位于 1024–65535，插件还要求保留出站端口空间。即使宿主映射端口不同，端口池也必须排除客户机 Docker API 2375。gvproxy 后端通过服务 API 注册 SSH、Docker API、完整 TCP 范围及自定义 `PORT_FORWARD=host:guest,...` 映射。映射必须唯一且不能与保留端口重叠。

注册在 QEMU 启动前完成，使用单连接且不重试。任何失败均清理自有辅助进程和部分规则。Linux 辅助进程文件描述符限制必须容纳所有监听器及连接余量；硬限制不足会在启动时报错。不转发 UDP、SCTP 发布。资源限制及已有较小显式端口池的维护见 README。

新客户机用同一数字范围初始化 Docker 缓存的发布端口池，就绪后恢复宽范围、不重叠的内核出站端口。已有磁盘保留所配发布池；兼容性和重启要求见插件根 README。不重启其他会话管理的虚拟机。

控制端口 `GVPROXY_QEMU_PORT`（19200）、`GVPROXY_API_PORT`（19201）仅监听回环，不与转发重叠。恢复需要协调停止、启动 QEMU 与 gvproxy，规则从配置重新生成。

## 加速与安装

`VM_ACCELERATOR=auto` 在 Linux 探测 KVM、Windows 探测 WHPX，否则选择 TCG。设置 `kvm` 或 `whpx` 强制使用对应加速器；不可用时失败，不回退。KVM 和 WHPX 使用 `host`，TCG 使用 `max`。KVM 需要兼容 x86-64 宿主机及 `/dev/kvm` 访问权限；Linux 容器映射该设备并将其组授予容器用户，无需特权模式。命令见插件根 `container/README.md`。

`ALPINE_MIRROR_BASE=auto` 在首次安装从官方列表选择最快镜像，要求自动选择的镜像支持 HTTPS，失败时回退官方 HTTPS CDN。显式 HTTP(S) 基 URL 会关闭自动选择。

`PRELOAD_IMAGES` 可在安装期间拉取逗号分隔镜像列表。支持 registry 路径、tag、digest、点、短横线和下划线。否则 Testcontainers 首次拉取，后续由 Docker 从持久磁盘复用镜像层。

## 指标

`TESTCONTAINERS_RESOURCE_METRICS=auto` 默认在 Windows 每秒采样，在 Linux 跳过 Windows 收集器。显式 `true` 要求 Windows PowerShell。通过 `TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1` 调整间隔（1–60 秒），PowerShell 不可用时可禁用。最新 JSON 报告位于虚拟机基目录下 `metrics/latest.json`，记录耗时及聚合资源值，不记录测试命令或工作目录路径。

## 限制与恢复

安装、生命周期和客户端脚本共享操作租约。竞争调用在修改虚拟机前失败。确认自有控制器退出后，正常退出和已处理信号释放租约；无法等待结束的原生控制器保留租约，阻止迟到发布。强制终止或控制器取消失败后，检查全部插件进程，再移除中断的 `run/vm-operation.lock`、`vm-state.guard` 或辅助工具 `.control.lock` 目录。只要自有 QEMU、gvproxy 任一进程仍活着，就不能丢弃其身份记录。

即使单虚拟机 PID 文件缺失，有归属的停止操作也能通过待发布 PID 或原生身份恢复部分发布的 QEMU 启动。身份检查失败、活进程无法识别、PID 指针冲突或启动 PID 从未完成发布时，保留网络与虚拟机预留供检查。不因缺少 PID 文件就移除预留。

QEMU 创建前的明确失败（包括日志访问和进程创建错误）自动清理本次启动。启动在就绪前被取消时，停止已验证进程及辅助进程；已提交就绪的虚拟机保持运行。停止被取消时，保留剩余归属供下一次停止完成。已有辅助进程归属要求显式停止，启动不接管。恢复时，将原子 `run/active-vm.lock/lifecycle.json` 阶段、进程证据和原生身份一起检查；不编辑阶段或删除记录来绕过未知启动。开发转换规则见 DEVELOPMENT.md。

Docker 运行在远程客户机，宿主机或外层容器路径不能作为普通 bind mount。优先用 Docker 构建上下文、具名卷或通过 Docker API 复制的测试夹具。

安装留下磁盘却没有就绪标记时，检查安装和验证控制台日志。已确认安装完成、仅验证失败时，在恢复配置中设置 `VERIFY_EXISTING=true`，运行 `./scripts/create-vm.sh <recovery-profile>` 继续验证。除非用户明确选择重建，否则不删除虚拟机目录。

## 配置文件与宿主机控制项

虚拟机设置直接从所选配置文件读取。不通过环境变量设置虚拟机配置、生命周期超时、`FORCE`、`VERIFY_EXISTING`、端口或安装选项；继承值会被忽略。文件缺失必需值时失败，可选值使用内置默认。配置值是不导出的 Shell 配置；只有明确的工具或测试约定才接收派生设置。未知键被拒绝。`QEMU_ALPINE_BASE_DIR`、配置文件和解释器选择、`GVPROXY_BINARY` 及代理工具路径等宿主机控制项保留在宿主环境。配置边界见插件 README。
