---
name: recyclerview-sentinel-viewholder
description: Use when RecyclerView needs a stable start anchor so prepended items are treated as visible-area insertions, especially for timelines, chat/history prepend, live feeds, and top-refresh list updates.
---

# RecyclerView Sentinel ViewHolder

## Project independence

Implement the sentinel as project-owned UI data/adapter code using normal AndroidX dependencies. Do not make rendering, tests or project instructions depend on this AI plugin's name, files or installation. Required build/compiler plugins and libraries are ordinary project dependencies and may be declared normally.

## Core Trick

Add a stable sentinel row at the beginning of the adapter data.
Prefer normal diffing first. Add a sentinel only when prepend anchoring is a real UX or correctness problem.

Without sentinel:

```text
old: 1 2
new: 0 1 2
diff: insert item 0 at adapter position 0
```

RecyclerView and `LinearLayoutManager` may interpret this as an insertion before the current anchor. In some prepend flows, the newly inserted row behaves like it appeared outside the visible area.

With sentinel:

```text
old: sentinel 1 2
new: sentinel 0 1 2
diff: insert item 0 at adapter position 1
```

The sentinel remains the stable first row and changes the diff insertion index to 1.
That alone does not guarantee visibility or scroll behavior: an offscreen sentinel
is still before the visible anchor. Verify the intended layout/anchor behavior with
the actual LayoutManager, scroll position, reverse layout and item heights.

## Data Model

Represent the sentinel as a real UI model with stable identity.

```kotlin
sealed interface RowUiModel {
    val stableId: Long

    data object Sentinel : RowUiModel {
        override val stableId: Long = Long.MIN_VALUE
    }

    data class Item(
        val id: Long,
        val title: String
    ) : RowUiModel {
        override val stableId: Long = id
    }
}
```

Build submitted lists with the sentinel first:

```kotlin
fun List<ItemUiModel>.withSentinel(): List<RowUiModel> {
    return listOf(RowUiModel.Sentinel) + map {
        RowUiModel.Item(id = it.id, title = it.title)
    }
}
```

## Diff Contract

The sentinel must always be the same item.

```kotlin
object RowDiff : DiffUtil.ItemCallback<RowUiModel>() {
    override fun areItemsTheSame(oldItem: RowUiModel, newItem: RowUiModel): Boolean {
        return oldItem::class == newItem::class &&
            oldItem.stableId == newItem.stableId
    }

    override fun areContentsTheSame(oldItem: RowUiModel, newItem: RowUiModel): Boolean {
        return oldItem == newItem
    }
}
```

- Do not let a normal row reuse the sentinel id.
- Include row type in identity so `Sentinel` and `Item(Long.MIN_VALUE)` can never collide.
- If `setHasStableIds(true)` is enabled, return `stableId` consistently from `getItemId`.

## ViewHolder Shape

The sentinel ViewHolder should be deterministic, non-interactive, and visually intentional.

```kotlin
private const val VIEW_TYPE_SENTINEL = 0
private const val VIEW_TYPE_ITEM = 1

override fun getItemViewType(position: Int): Int {
    return when (getItem(position)) {
        RowUiModel.Sentinel -> VIEW_TYPE_SENTINEL
        is RowUiModel.Item -> VIEW_TYPE_ITEM
    }
}
```

For the sentinel layout:

- Use a tiny spacer, a header container, or a real top affordance if the product has one.
- Keep height stable across binds.
- Avoid click, focus, accessibility noise, and dynamic content unless it is a real header.
- Be careful with `0dp` height. It can work as a pure diff anchor, but if the UX depends on visibility or animation, test it on the target layouts.
- A sentinel makes `itemCount` nonzero even without content. `PREVENT_WHEN_EMPTY`
  therefore does not defer restoration until real rows arrive; use an explicit
  restoration policy or independently owned header/content adapters when needed.

## Adapter Position Helpers

Because adapter position `0` is now the sentinel, never expose raw adapter positions as business positions.

```kotlin
private const val SENTINEL_COUNT = 1

fun adapterPositionToItemIndex(adapterPosition: Int): Int {
    return adapterPosition - SENTINEL_COUNT
}

fun itemIndexToAdapterPosition(itemIndex: Int): Int {
    return itemIndex + SENTINEL_COUNT
}
```

Guard all scroll, selection, and click code:

- Ignore clicks when the bound row is `Sentinel`.
- Convert item indexes before calling `scrollToPosition`, `smoothScrollToPosition`, or `findViewHolderForAdapterPosition`.
- For tests, assert both raw adapter positions and user-visible item indexes.

## Paging Notes

For `PagingDataAdapter`, prefer built-in Paging behavior first. Use a sentinel only when the adapter owns a top row outside the paged stream.

Options:

- Use `ConcatAdapter` with a one-row sentinel/header adapter before the paged adapter.
- Or use Paging's `insertHeaderItem` after mapping to a shared row-model type,
  if the codebase already owns that pipeline. Mapping items alone adds no header.

Do not inject the sentinel into the database paging source. It is UI structure, not domain data.

## Upstream improvement feedback

- When using this plugin reveals an actionable bug, missing guidance, or reusable improvement, report it to [storytellerF/me](https://github.com/storytellerF/me/issues). Identify the owning plugin and skill; do not report project-specific problems without evidence that the plugin needs a change. Finish the user's primary task before non-blocking feedback work.
- Before any search or submission, reduce the finding to a privacy-safe summary. Never send raw conversations, private source code, logs, screenshots, credentials, personal identifiers, account data, or private paths/URLs. Use synthetic examples and the minimum non-sensitive environment details needed to explain the problem. If safe disclosure is impossible, keep the finding local.
- Search both open and closed upstream issues using the plugin name and sanitized symptom keywords. Read likely matches and their resolution; do not rely only on title matches. Reuse a matching issue link instead of opening a duplicate. Add a comment only when it supplies materially new, safe evidence and posting is authorized. A closed issue warrants a new report only for a distinct regression or uncovered case, with a link explaining the difference.
- Submit a new issue when no duplicate exists and the user has authorized upstream reporting in the current session or standing instructions. This rule alone does not authorize external posting. Honor existing authorization without asking again; otherwise prepare a sanitized draft for approval.
- Include the plugin/skill and version, observed and expected behavior, a minimal synthetic reproduction or concrete improvement proposal, and relevant duplicate-search results. Use a concise title prefixed with the plugin name.
- If search, authentication, or submission fails, retain the sanitized draft and explain the blocker; do not post without completing duplicate checks. After an uncertain submission result, check for the created issue before retrying. Return the existing or created issue URL, or clearly mark the report as an unsubmitted draft.
