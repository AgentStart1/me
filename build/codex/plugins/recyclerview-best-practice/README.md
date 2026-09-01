# RecyclerView Best Practice Plugin

This Codex plugin provides an Android RecyclerView skill for creating, reviewing, and refactoring list UI code.

## Contents

- `.codex-plugin/plugin.json` declares the plugin.
- `skills/android-recyclerview-best-practice/SKILL.md` contains the RecyclerView guidance.
- `skills/recyclerview-sentinel-viewholder/SKILL.md` contains the start-sentinel ViewHolder trick for prepend anchoring.

## Local Marketplace Entry

Run `scripts/build-codex-plugin-package.sh --all` to generate `build/.agents/plugins/marketplace.json`, which contains the local plugin entry:

```json
{
  "name": "recyclerview-best-practice",
  "source": {
    "source": "local",
    "path": "./plugins/recyclerview-best-practice"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Developer Tools"
}
```
