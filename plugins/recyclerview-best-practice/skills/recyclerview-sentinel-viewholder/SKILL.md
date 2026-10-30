---
name: recyclerview-sentinel-viewholder
description: Use when diagnosing or fixing RecyclerView prepend visibility, scroll anchoring, or insertion-animation problems in chats, timelines, feeds, or top-refresh lists, or when explicitly asked for a sentinel row. Evaluate whether a sentinel is appropriate; do not add one for every RecyclerView list.
---

# RecyclerView Sentinel ViewHolder

## Project independence

Implement the sentinel as project-owned UI data/adapter code using normal AndroidX dependencies. Do not make rendering, tests or project instructions depend on this AI plugin's name, files or installation. Required build/compiler plugins and libraries are ordinary project dependencies and may be declared normally.

## Core Trick

Inspect the existing diff and scroll-anchor behavior first. When a stable start row addresses a demonstrated prepend problem, add a sentinel at the beginning of the adapter data; otherwise retain normal diffing.

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

- Report actionable plugin bugs or reusable improvements to [storytellerF/me](https://github.com/storytellerF/me/issues), identifying the plugin and skill. Exclude project-only problems without evidence of a plugin defect. Finish the primary task before non-blocking feedback work.
- Before searching or posting, reduce evidence to a minimal privacy-safe summary or synthetic reproduction. Never disclose raw conversations, private code, logs, screenshots, credentials, personal/account data, or private paths/URLs. Keep findings local if safe disclosure is impossible.
- Search open and closed issues and read likely matches and resolutions. Reuse matching reports; a distinct regression or uncovered case may need a linked new issue. Posting a new issue or a materially useful comment requires existing user authorization; this rule grants none. Without authorization, prepare an unsubmitted draft.
- Include the plugin/skill version, observed and expected behavior, reproduction or proposal, and duplicate-search results; prefix new issue titles with the plugin name. On access or submission failure, retain the draft and explain the blocker. After an uncertain submission, check whether it succeeded before retrying. Return the report link or clearly label the draft as unsubmitted.
