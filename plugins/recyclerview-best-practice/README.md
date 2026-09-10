# RecyclerView Best Practice Plugin

This Codex plugin provides an Android RecyclerView skill for creating, reviewing, and refactoring list UI code.

## Contents

- `.codex-plugin/plugin.json` declares the plugin.
- `skills/android-recyclerview-best-practice/SKILL.md` contains the RecyclerView guidance.
- `skills/recyclerview-sentinel-viewholder/SKILL.md` contains the start-sentinel ViewHolder trick for prepend anchoring.

## Codex Marketplace Entry

The repository synchronization workflow generates the `me.codex` marketplace entry after source changes merge to `main`. Contributors should not generate or publish this package from a local `me.codex` checkout. The generated entry is:

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
