# 独立 Alpine Docker 后端

只有测试需要此后端时才选择本流程。复用合适的已有 Docker 端点；普通 Linux 宿主机直接使用 Docker。工作客户机不要求 Alpine，仅 Docker 测试也不要求工作客户机。配置前阅读插件[前提要求](../../../README.md#前提条件)。

## 安装与运行

以下命令仅用于请求范围内的新后端：

```bash
scripts/setup.sh
scripts/create-vm.sh /absolute/path/to/backend.profile
```

已有后端优先复用，或通过 `scripts/start-vm.sh /absolute/path/to/backend.profile` 启动。原生 Docker CLI 代理缺失或源码更新后，运行 `scripts/build-docker-proxy.sh --profile /absolute/path/to/backend.profile` 准备，再通过 `scripts/run-test-env.sh --profile /absolute/path/to/backend.profile -- <test command>` 执行宿主机测试。还需协调客户机 Appium 时，使用[测试执行](test-execution.md)中的配置式流程。只有用户要求且归属允许时才停止后端，不能仅因测试结束就停止复用服务。

代理构建器是真实操作，不是离线检查：连接已有 Alpine 后端、传输源码、必要时在其中安装 Go、运行 Go 测试、为所选宿主目标交叉编译原生代理，再通过 SSH 下载。Windows 或与 QEMU 相同的外层 Linux 容器内调用构建器和宿主机测试。Go 及其缓存保留在持久 Alpine 磁盘；成功或失败后清理临时源码和二进制。此后端工具构建与 Windows、Ubuntu、macOS 工作客户机内编译不同。

所有 `build-docker-proxy.sh` 调用共享用户级锁 `~/.cache/me/locks/build-docker-proxy.lock`，与虚拟机、项目、插件检出目录及输出目录无关。上传、安装编译器、编译、下载和替换可执行文件前先等待锁。`QEMU_DOCKER_BUILD_LOCK_TIMEOUT` 设置等待秒数，默认 900。正常退出和已处理信号释放自有锁。强制终止后，陈旧锁会报错；确认没有编译或传输残留后，才能删除报告的锁目录。不删除其他运行中构建的锁。

默认代理目录为用户级 `~/.local/share/me/docker-proxy`。Windows 使用 `docker.exe`，Linux 容器使用 `docker`。同一环境同一用户的所有项目共用可执行文件；包装器提供本次虚拟机 SSH 设置。Linux 容器中该目录归容器用户所有，替换外层容器后需持久化此目录或重建工具；仅保留虚拟机磁盘不会保留该文件。

覆盖目录时，构建器和测试包装器一致设置 `QEMU_DOCKER_PROXY_DIR`。包装器将代理加入 PATH 并提供 SSH 设置；只有已有 Gradle daemon 保留过时可执行文件查找结果时才重启它。代理使用 Go SSH 传输，避免嵌套系统 SSH 的 stdin 和输出停滞。

## 后端配置

修改配置、加速、端口范围、指标、镜像源、预加载镜像或恢复设置前，阅读[配置与恢复](configuration-and-recovery.md)。后端 `.profile` 不同于工作客户机 JSON 配置。同一时间最多运行一个 Alpine 后端，多个工作客户机仍独立。

以下规则适用于 Alpine，尤其是它的 `auto` 加速器回退不适用于显式选择或受管的工作客户机运行时。

- 两种加速方式均通过回环 TCP QEMU socket 使用 gvproxy v0.9.0，保留 MAC `5a:94:ef:e4:0c:ee`。
- 复用持久 qcow2 磁盘，让 Docker 镜像跨测试保留。
- Alpine 和 Docker 上游 DNS 通过 `192.168.127.1` 的 gvproxy 解析。
- 保持 Testcontainers Ryuk 启用。
- 将配置中延长的 Testcontainers 拉取静默与总超时传给宿主测试进程，因为 TCG 回退下大镜像解包可能长时间无输出。
- Docker 自动发布端口范围与 gvproxy 同端口转发范围一致。
- Docker 在 daemon 初始化时缓存发布端口池。新客户机通过受监督启动包装器预设端口池，再恢复不重叠的宽范围内核出站端口。不要只改 QEMU 转发就应用新默认值，也不要重启其他会话的持久客户机；先查看 README 的发布端口池兼容性。
- 不悄悄删除未完成磁盘，不使用 `docker image prune -a`。
- TCP 2375 是等同 root 权限且未经认证的 API，不暴露到回环地址以外。

## Docker 文件与构建上下文

代理通过 Docker 上游 `moby/patternmatcher` 过滤本地 `docker build` 上下文，包括有序例外和 Dockerfile 专属忽略文件。生成的 tar 经 SSH 流式传入客户机 `docker buildx build --load`。非构建命令通过 SSH 执行，不复制上下文；宿主路径 bind mount 和 `docker cp` 不转换。构建 secret、SSH mount 和具名宿主上下文需要明确传输支持，当前拒绝。通过 Docker 忽略规则排除机密。Windows 归档权限增加执行位并移除组和全局写位；Linux 容器保留源权限，因此脚本本身需有执行位。skill 不选择项目服务名称或 Docker 目标。

Docker 构建选项可位于上下文目录前或后。显式 `-f`、`--file` 从宿主工作目录解析，必须位于上下文内。`--iidfile` 在构建成功后将镜像 ID 写回指定宿主路径。相对输出路径以宿主工作目录解析，父目录必须存在。客户机使用私有临时文件，传输后或构建失败后清理。`--metadata-file` 和 `--output`/`-o` 仍不支持并明确拒绝。

项目文件必须存在于 Alpine 时，使用 `scripts/sync-workspace.sh --remote-dir <guest-directory> <host-workspace>` 复制，默认排除生成及私有文件，可重复传 `--exclude`。它绝不运行项目命令。复制工作区不授权在工作客户机编译应用，构建与测试位置保持明确。

启动脚本在 SSH 和 Docker API 就绪后返回。测试包装器设置：

- `DOCKER_HOST=tcp://127.0.0.1:<DOCKER_DAEMON_PORT>`
- `TESTCONTAINERS_HOST_OVERRIDE=127.0.0.1`
- `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`

它取消 TLS 变量和 `TESTCONTAINERS_RYUK_DISABLED`，保留测试命令退出码。`auto` 指标模式下，Windows 收集并报告资源均值和峰值；Linux 不运行 PowerShell 收集器，也不更新指标报告。

## Linux 容器宿主环境

普通非 root 容器流程见插件根目录 `container/README.md`。映射 `/dev/kvm` 并添加匹配附加组即可启用 KVM，不要求 `--privileged`。本 Alpine 后端在 KVM 不可用时可按自动策略选择 TCG；显式加速器必须失败，不回退。测试进程、QEMU 和 MCP 状态服务留在同一外层容器的进程、网络命名空间。Docker、Testcontainers 转发只监听回环。客户机为 x86-64，KVM 要求兼容的 Linux 宿主 CPU。

## 生命周期与恢复

使用 Python 3.10+ 运行 `scripts/start-vm.py` 或 `scripts/stop-vm.py`，接受相同可选配置参数。`.sh` 命令选择解释器，通过 `QEMU_BASH_BINARY` 保留启动 Bash 运行时；原生调用者可显式设置此变量。明确解释器通过 `QEMU_STATE_PYTHON` 指定。Python 启动和停止控制器负责就绪、取消和失败清理。发送信号仍通过共享进程身份实现核对原生可执行文件与创建时间。平台和客户机适配器规划加速与网络并执行 SSH，不管理生命周期锁。Python 在取消和退出过程中管理原生辅助控制器子进程。

安装仍由 `create-vm.sh` 的 Shell 编排，使用同一 Python 状态控制器管理操作租约、全局预留、进程注册及状态清理。客户机模板和简单命令转发仍使用 Shell。进程探测未知、guard 中断或清理失败时，保留归属供检查。遵循共同取消规则，手动恢复前检查遗留操作租约。

网络恢复先确认虚拟机不属于其他用户，再协调 `stop-vm.sh` 和 `start-vm.sh`。上游只接受一个 QEMU 连接，同时重启二者以恢复规则并建立新传输。不用连接重试或 SSH 网络桥接掩盖应用失败。

## 真实后端验收

使用 Alpine 的 OpenRC `cgroups` 服务，不使用 `cgroupfs-mount` 包。保留 Docker、Compose、SSH 和 SFTP 依赖；Go 仅代理编译需要。真实安装验证使用新的隔离基目录、磁盘、密钥、端口和代理目录。完成安装、启动和代理编译后，通过 `run-testcontainers.sh` 运行 `tests/validate-guest-testcontainers.py`，提供该配置发布端口池边界并保持 Ryuk 启用。准确命令见 README。检查覆盖转发、cgroup 限制、OOM 强制执行和容器删除，不授权修改其他会话虚拟机。
