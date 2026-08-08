# me

A local Codex Android plugin collection. It currently includes Android SDK/AVD setup scripts, an Appium device lock, RecyclerView best-practice skills, and general coding-practice/Kotlin project skills.

## Package Structure

- `.agents/plugins/marketplace.json`: the in-repo `me` Codex marketplace entry.
- `plugins/android-profile/.codex-plugin/plugin.json`: Android Profile plugin manifest.
- `plugins/android-profile/scripts/`: Android SDK, AVD, and emulator scripts.
- `plugins/android-profile/tests/`: smoke test scripts.
- `plugins/android-profile/profiles/android.profile`: default Android emulator profile.
- `plugins/android-profile/skills/android-profile/SKILL.md`: Codex-facing Android Profile instructions.
- `plugins/android-appium-device-lock/.codex-plugin/plugin.json`: Appium device lock plugin manifest.
- `plugins/android-appium-device-lock/scripts/adb-device-lock.sh`: adb-based device-side file lock script.
- `plugins/android-appium-device-lock/skills/android-appium-device-lock/SKILL.md`: Codex-facing Appium device lock instructions.
- `plugins/recyclerview-best-practice/.codex-plugin/plugin.json`: RecyclerView best-practice plugin manifest.
- `plugins/recyclerview-best-practice/skills/`: RecyclerView adapter, diffing, paging, sentinel ViewHolder, and related practice instructions.
- `plugins/general-coding-practices/.codex-plugin/plugin.json`: General Coding Practices plugin manifest.
- `plugins/general-coding-practices/skills/`: project collaboration, README maintenance, verification, rule-file maintenance, root-cause-first debugging, repository delivery, and Kotlin project practice instructions.
- `plugins/*/skills/*/agents/`: portable agent prompts colocated with the skill that triggers them.
- `agents/`: prompts specific to maintaining this plugin collection.
- `scripts/install-agents.sh`: manually copy prompts into Codex or Claude agent directories.

## Installation

Add this GitHub repository as a Codex plugin marketplace:

```bash
codex plugin marketplace add https://github.com/storytellerF/me
```

Install plugins from the marketplace:

```bash
codex plugin add android-profile@me
codex plugin add android-appium-device-lock@me
codex plugin add recyclerview-best-practice@me
codex plugin add general-coding-practices@me
```

Start a new Codex thread after installation so the plugin skills are loaded.

### Agent prompts

Codex plugin installation does not install subagent prompt files. Install them separately from a
clone of this repository:

```bash
# Install globally for Codex.
./scripts/install-agents.sh --target codex --scope global

# Or install for the current project in both supported layouts.
./scripts/install-agents.sh --target both --scope project --project-dir "$PWD"
```

Use `--dry-run` to inspect the copy list first. The installer copies the same Claude-compatible
Markdown prompts to `.codex/agents` and/or `.claude/agents`; it does not copy conversation history.

### Claude Code

Create a `CLAUDE.md` file in the target project and reference the skills needed from this repository:

```markdown
@plugins/recyclerview-best-practice/skills/android-recyclerview-best-practice/SKILL.md
@plugins/android-appium-device-lock/skills/android-appium-device-lock/SKILL.md
@plugins/general-coding-practices/skills/project-collaboration-rules/SKILL.md
@plugins/general-coding-practices/skills/project-readme-maintenance/SKILL.md
@plugins/general-coding-practices/skills/project-checks-and-tests/SKILL.md
@plugins/general-coding-practices/skills/project-rule-file-maintenance/SKILL.md
@plugins/general-coding-practices/skills/root-cause-before-fallback/SKILL.md
@plugins/general-coding-practices/skills/kotlin-project-rules/SKILL.md
```

Alternatively, clone this repository locally and reference the skill files with absolute paths from the target project's `CLAUDE.md`:

```markdown
@/path/to/me/plugins/recyclerview-best-practice/skills/android-recyclerview-best-practice/SKILL.md
@/path/to/me/plugins/android-appium-device-lock/skills/android-appium-device-lock/SKILL.md
@/path/to/me/plugins/general-coding-practices/skills/project-collaboration-rules/SKILL.md
@/path/to/me/plugins/general-coding-practices/skills/project-readme-maintenance/SKILL.md
@/path/to/me/plugins/general-coding-practices/skills/project-checks-and-tests/SKILL.md
@/path/to/me/plugins/general-coding-practices/skills/project-rule-file-maintenance/SKILL.md
@/path/to/me/plugins/general-coding-practices/skills/root-cause-before-fallback/SKILL.md
@/path/to/me/plugins/general-coding-practices/skills/kotlin-project-rules/SKILL.md
```

Claude Code loads these instructions automatically when a conversation starts.

## Running Scripts Directly

You can also run the bundled scripts directly from the plugin root:

```bash
cd plugins/android-profile
ANDROID_HOME=$HOME/android-sdk ./scripts/install-sdk.sh
./scripts/create-avd.sh ./profiles/android.profile
./scripts/start-avd.sh ./profiles/android.profile
```

Custom profiles may define standard Android path variables directly, including `ANDROID_HOME`, `ANDROID_AVD_HOME`, and `ANDROID_USER_HOME`. The scripts load the profile first, then locate SDK tools and AVD files. The bundled `profiles/android.profile` does not preset these paths.

Run the `start-avd.sh` smoke test with fake emulator commands from the repository root:

```bash
plugins/android-profile/tests/test-start-avd-docker.sh
```

## Host Emulator Access From a VM

If the Android emulator runs on the host machine and a VM needs to access the host ADB port, add port forwarding and firewall rules on the host. This example assumes the VM subnet is `192.168.80.0/24` and the host address on that virtual network is `192.168.80.1`:

```powershell
netsh interface portproxy add v4tov4 listenaddress=192.168.80.1 listenport=5555 connectaddress=127.0.0.1 connectport=5555
netsh advfirewall firewall add rule name="Android Emulator ADB 5555" dir=in action=allow protocol=TCP localport=5555 remoteip=192.168.80.0/24
```

Confirm the port proxy entry exists:

```shell
netsh interface portproxy show all
```

Confirm the host is listening:

```shell
netstat -ano | findstr "192.168.80.1:5555"
```

If it is not listening, restart the service:

```shell
net stop iphlpsvc
net start iphlpsvc
```
