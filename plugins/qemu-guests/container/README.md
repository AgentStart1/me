# 普通 Linux 容器中的 QEMU Docker

镜像还包含 pycdlib，用于创建并发工作客户机的无人值守介质，以及 Tesseract，用于 macOS Recovery 交接。使用插件 README 的工作客户机 JSON 配置和监督器。各工作客户机 `state_dir` 放在持久存储上，在同一容器内分配不同宿主 SSH 端口。已有 Alpine 卷和存储覆盖值不变，让后端磁盘在插件重命名后继续保留。

从插件根目录构建：

镜像将 Shell 脚本、配置和模板统一为 LF，使 Windows CRLF 检出也能在 Linux 容器工作。

```bash
docker build -f container/Dockerfile -t qemu-alpine-dev .
```

以持久虚拟机存储启动非 root 容器。KVM 不可用时使用 TCG。无需宿主 Docker socket 或特权模式。

```bash
docker run -d --init --name qemu-dev \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --mount source=qemu-alpine-state,target=/var/lib/qemu-alpine \
  qemu-alpine-dev
```

x86-64 Linux 宿主机使用 KVM 时，改用下方命令。宿主机必须支持虚拟化并暴露 `/dev/kvm`。Docker 宿主自身也是虚拟机时，还需启用嵌套虚拟化。

```bash
docker run -d --init --name qemu-dev \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --device=/dev/kvm --group-add="$(stat -c '%g' /dev/kvm)" \
  --mount source=qemu-alpine-state,target=/var/lib/qemu-alpine \
  qemu-alpine-dev
```

`VM_ACCELERATOR=auto` 探测 QEMU 是否能实际初始化 KVM，再回退 TCG。强制 KVM 时复制开发配置，设置 `VM_ACCELERATOR=kvm` 并传给脚本。显式 KVM 不可用时给出可操作错误，不悄悄仿真。客户机为 x86-64；其他宿主架构可用 TCG，不能用 x86-64 KVM。

首次安装后启动虚拟机：

```bash
docker exec qemu-dev bash /opt/qemu-guests/scripts/setup.sh
docker exec qemu-dev bash /opt/qemu-guests/scripts/create-vm.sh
docker exec qemu-dev bash /opt/qemu-guests/scripts/start-vm.sh
docker exec qemu-dev bash /opt/qemu-guests/scripts/run-docker.sh -- ps -a
docker exec qemu-dev python3 /opt/qemu-guests/scripts/status.py
```

开发工具、测试进程和 MCP 服务在同一外层容器及网络命名空间运行。`setup.sh` 安装已校验的上游 gvproxy v0.9.0。QEMU、gvproxy 共享命名空间；Alpine 和 Docker 使用 gvproxy DNS。其中 Docker 回环 API 为 `127.0.0.1:2375`，自动发布客户机 TCP 端口转发到其中的 `127.0.0.1:20000–20127`。宿主侧 `docker -p` 不会让绑定容器回环的服务变得可访问。默认设计将无认证 API 留在本地，不扩大到 `0.0.0.0`。

默认端口池要求 gvproxy 至少 389 个文件描述符（133 个配置转发加 256 个连接余量）。运行时硬限制更低时，在启动命令添加 `--ulimit nofile=1024:1024`，或选择更小的显式池。启动只提高辅助进程继承的软限制。更大池没有数量上限，但需要可用端口、足够内存和描述符；负载可能需要更多余量。插件脚本不暴露 UDP、SCTP 发布。

可将此镜像作为自己的 JDK、构建工具或 Codex 环境基础，并在其中安装 uv 供 MCP 状态面板使用。首次测试前，在虚拟机启动后，从外层容器编译 Linux Docker CLI 代理：

```bash
docker exec qemu-dev bash /opt/qemu-guests/scripts/build-docker-proxy.sh
docker exec qemu-dev bash /opt/qemu-guests/scripts/run-test-env.sh -- <test command>
```

将 `<test command>` 替换为外层容器可用、且项目在其中可访问的命令。构建脚本使用 Alpine 客户机中的 Go，为外层容器架构下载 Linux amd64 或 arm64 `docker` 可执行文件；外层容器无需安装 Go。代理源码更新后重建。默认工具路径为容器用户家目录下 `~/.local/share/me/docker-proxy/docker`；持久化此目录，或替换外层容器后重建。它独立于虚拟机状态卷。编译与测试使用相同 `QEMU_DOCKER_PROXY_DIR` 覆盖。

`run-testcontainers.sh` 将代理加入 PATH 并提供客户机 SSH 设置。Docker 构建按 Docker 忽略规则过滤本地上下文，经 SSH 流式传给客户机。Linux 源权限保留，脚本本身须具备所需执行位。宿主路径 bind mount 和 `docker cp` 不转换；客户机容器使用构建上下文或具名卷。

包装器使用客户机 Docker，并保持 Ryuk 启用。默认指标模式为 `auto`：Linux 不运行 Windows PowerShell 收集器，不生成其摘要或更新报告。虚拟机磁盘缓存、Testcontainers 网络和状态面板独立于该收集器工作。

停止外层容器前先停止虚拟机：

```bash
docker exec qemu-dev bash /opt/qemu-guests/scripts/stop-vm.sh
docker stop qemu-dev
```

保留具名卷以复用 qcow2 磁盘和镜像缓存。卷必须允许 UID 1000 写入；已有 bind mount 单独初始化归属。并发容器不能共享运行中虚拟机的状态目录。

受代理管理的环境通过 `--secret id=proxy_ca,src=<CA bundle>` 传递构建 CA，必要时为 curl 只读挂载运行时 CA。客户机包安装和 Docker 拉取也需要各自可用的出站及 CA、代理配置；外层 Docker 代理变量不会自动成为客户机配置。不禁用 TLS 验证。
