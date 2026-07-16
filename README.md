# me

一个本地 Codex Android 插件合集。当前包含 Android SDK/AVD 配置脚本、Appium 设备锁、RecyclerView 最佳实践 skill，以及通用编码实践 skill。

## 包结构

- `.agents/plugins/marketplace.json`：仓库内的 `me` Codex marketplace 条目。
- `plugins/android-profile/.codex-plugin/plugin.json`：插件清单文件。
- `plugins/android-profile/scripts/`：Android SDK、AVD 和模拟器脚本。
- `plugins/android-profile/tests/`：冒烟测试脚本。
- `plugins/android-profile/profiles/android.profile`：默认 Android 模拟器配置。
- `plugins/android-profile/skills/android-profile/SKILL.md`：面向 Codex 的使用说明。
- `plugins/android-appium-device-lock/.codex-plugin/plugin.json`：Appium 设备锁插件清单文件。
- `plugins/android-appium-device-lock/scripts/adb-device-lock.sh`：基于 adb 的设备端文件锁脚本。
- `plugins/android-appium-device-lock/skills/android-appium-device-lock/SKILL.md`：面向 Codex 的 Appium 设备锁使用说明。
- `plugins/recyclerview-best-practice/.codex-plugin/plugin.json`：RecyclerView 最佳实践插件清单文件。
- `plugins/recyclerview-best-practice/skills/`：RecyclerView adapter、diff、paging、sentinel ViewHolder 等实践说明。
- `plugins/general-coding-practices/.codex-plugin/plugin.json`：通用编码实践插件清单文件。
- `plugins/general-coding-practices/skills/`：先找根因再加 fallback 的实践说明。

## 安装

将此 GitHub 仓库添加为 Codex 插件 marketplace：

```bash
codex plugin marketplace add https://github.com/storytellerF/me
```

从该 marketplace 安装插件：

```bash
codex plugin add android-profile@me
codex plugin add android-appium-device-lock@me
codex plugin add recyclerview-best-practice@me
codex plugin add general-coding-practices@me
```

安装后启动一个新的 Codex 线程，以便加载插件 skill。

### Claude Code

在目标项目中创建 `CLAUDE.md`，引用本仓库中需要的 skill 文件：

```markdown
@plugins/recyclerview-best-practice/skills/android-recyclerview-best-practice/SKILL.md
@plugins/android-appium-device-lock/skills/android-appium-device-lock/SKILL.md
@plugins/general-coding-practices/skills/root-cause-before-fallback/SKILL.md
```

或者将本仓库克隆到本地后，在目标项目的 `CLAUDE.md` 中用绝对路径引用：

```markdown
@/path/to/me/plugins/recyclerview-best-practice/skills/android-recyclerview-best-practice/SKILL.md
@/path/to/me/plugins/android-appium-device-lock/skills/android-appium-device-lock/SKILL.md
@/path/to/me/plugins/general-coding-practices/skills/root-cause-before-fallback/SKILL.md
```

Claude Code 会在对话开始时自动加载这些指引。

## 直接使用脚本

也可以在插件根目录下直接运行打包好的脚本：

```bash
cd plugins/android-profile
ANDROID_HOME=$HOME/android-sdk ./scripts/install-sdk.sh
./scripts/create-avd.sh ./profiles/android.profile
./scripts/start-avd.sh ./profiles/android.profile
```

自定义 profile 可以直接定义 Android 标准路径变量 `ANDROID_HOME`、
`ANDROID_AVD_HOME` 和 `ANDROID_USER_HOME`。脚本会先加载 profile，再查找 SDK
工具和 AVD 文件。仓库随附的 `profiles/android.profile` 不预设这些路径。

在仓库根目录下使用假的模拟器命令运行 `start-avd.sh` 冒烟测试：

```bash
plugins/android-profile/tests/test-start-avd-docker.sh
```

## 宿主机模拟器供虚拟机访问

如果 Android 模拟器运行在宿主机上，而需要从虚拟机中访问宿主机的 ADB 端口，还需要在宿主机上添加端口转发和防火墙规则。以下示例假设虚拟机网段为 `192.168.80.0/24`，宿主机在该虚拟网络中的地址为 `192.168.80.1`：

```powershell
netsh interface portproxy add v4tov4 listenaddress=192.168.80.1 listenport=5555 connectaddress=127.0.0.1 connectport=5555
netsh advfirewall firewall add rule name="Android Emulator ADB 5555" dir=in action=allow protocol=TCP localport=5555 remoteip=192.168.80.0/24
```

需要确保配置存在 
```shell
netsh interface portproxy show all
```

确保真的在监听 
```
netstat -ano | findstr "192.168.80.1:5555"
```

如果没有在监听需要重启服务

```shell
net stop iphlpsvc
net start iphlpsvc
```
