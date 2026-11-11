# 手动锁生命周期

设备操作跨越多个命令时，从 agent 管理的 Shell 会话手动获取锁。按 `SKILL.md` 将 `DEVICE_LOCK_PLUGIN_ROOT` 解析为已安装插件的绝对根路径；项目测试运行器和 CI 保持不变。从项目目录运行现有测试命令，令牌文件放在系统临时目录。

```bash
token_file="$(mktemp)"
"$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" acquire \
  --serial "$ANDROID_SERIAL" \
  --project-dir "$PWD" \
  --test-name "android-device-suite" \
  --token-file "$token_file"

trap '"$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" release --serial "$ANDROID_SERIAL" --token-file "$token_file"' EXIT
./gradlew connectedAndroidTest
```

长时间运行的套件应定期续租：

```bash
"$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" renew \
  --serial "$ANDROID_SERIAL" \
  --token-file "$token_file" \
  --max-timeout-seconds 1800
```

租约释放后删除临时令牌文件。只能使用获取时返回的令牌释放。续租或释放报告归属令牌不匹配时，保留锁，因为它属于其他运行任务。

整个操作期间应在到期前续租。自动续租器的生命周期必须与测试命令一致，续租失败时停止设备工作；只退出后台续租循环却让测试继续，会失去独占保证。`run` 模式不自动延长租约。获取、续租和释放始终使用相同设备序列号和锁路径；连接多个设备时，获取和释放示例都应包含 `--serial`。
