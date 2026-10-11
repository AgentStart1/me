# RecyclerView Best Practice Plugin

This portable plugin provides Android RecyclerView guidance for creating, reviewing, and refactoring list UI code.

Feature state and effects follow the framework-independent Host contract; Android
ViewModels may adapt that Host to the view lifecycle. A prepend sentinel changes
diff positions but does not guarantee visibility or anchoring when offscreen.
Validate actual layout and state-restoration behavior; Paging headers use
`ConcatAdapter` or `insertHeaderItem`.

## Contents

- `plugin.json` declares the portable plugin and client extensions.
- `skills/android-recyclerview-best-practice/SKILL.md` contains the RecyclerView guidance.
- `skills/recyclerview-sentinel-viewholder/SKILL.md` contains the start-sentinel ViewHolder trick for prepend anchoring.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.
