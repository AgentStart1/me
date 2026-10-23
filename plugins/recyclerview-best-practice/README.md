# RecyclerView Best Practice Plugin

This portable plugin provides Android RecyclerView guidance for creating, reviewing, and refactoring list UI code.

Feature state and effects follow the framework-independent Host contract; Android
ViewModels may adapt that Host to the view lifecycle. A prepend sentinel changes
diff positions but does not guarantee visibility or anchoring when offscreen.
Validate actual layout and state-restoration behavior; Paging headers use
`ConcatAdapter` or `insertHeaderItem`.

## Project independence

Adapter and sentinel implementations belong to the consuming project and use normal AndroidX dependencies. Neither skill makes the project depend on this AI plugin's installation; required Android/Gradle/compiler plugins remain ordinary dependencies.

## Contents

- `plugin.json` declares the portable plugin and client extensions.
- `skills/android-recyclerview-best-practice/SKILL.md` contains the RecyclerView guidance.
- `skills/recyclerview-sentinel-viewholder/SKILL.md` contains the start-sentinel ViewHolder trick for prepend anchoring.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.

## Improvement feedback

Plugin findings go to [storytellerF/me issues](https://github.com/storytellerF/me/issues). Skills require checking open and closed issues before reporting, using sanitized or synthetic examples, and honoring the user's authorization before posting. Existing reports are reused; unavailable access leaves an unsubmitted draft.
