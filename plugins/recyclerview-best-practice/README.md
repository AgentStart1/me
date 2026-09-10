# RecyclerView Best Practice Plugin

This Codex plugin provides an Android RecyclerView skill for creating, reviewing, and refactoring list UI code.

## Contents

- `.codex-plugin/plugin.json` declares the plugin.
- `skills/android-recyclerview-best-practice/SKILL.md` contains the RecyclerView guidance.
- `skills/recyclerview-sentinel-viewholder/SKILL.md` contains the start-sentinel ViewHolder trick for prepend anchoring.

## Codex Marketplace Entry

Contributors may generate the `me.codex` marketplace locally to review and validate source changes, but should not commit, push, or open a pull request from the local generated checkout. After source changes merge to `main`, the repository synchronization workflow generates and publishes the entry:

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
