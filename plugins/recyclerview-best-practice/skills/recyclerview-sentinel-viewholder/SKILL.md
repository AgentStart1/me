---
name: recyclerview-sentinel-viewholder
description: Use when RecyclerView needs a stable start anchor so prepended items are treated as visible-area insertions, especially for timelines, chat/history prepend, live feeds, and top-refresh list updates.
---

# RecyclerView Sentinel ViewHolder

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

The sentinel remains the stable first row. The new item is inserted after the sentinel, so the update is modeled as a visible-area insertion below a known anchor.

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
- Or map paging items into row models only if the codebase already has a row-model pipeline.

Do not inject the sentinel into the database paging source. It is UI structure, not domain data.
