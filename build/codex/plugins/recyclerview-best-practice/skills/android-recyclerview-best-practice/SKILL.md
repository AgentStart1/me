---
name: android-recyclerview-best-practice
description: Use when creating, reviewing, or refactoring Android RecyclerView code, especially adapters, ViewHolders, DiffUtil, ListAdapter, PagingDataAdapter, item state, lifecycle collection, and performance.
---

# Android RecyclerView Best Practice

Use this skill whenever the task touches Android `RecyclerView`, `Adapter`, `ViewHolder`, `DiffUtil`, Paging 3, list rendering, or item interactions.

## Core Decision

Always choose an adapter with built-in diffing unless the codebase has a strong existing abstraction that prevents it.

1. Use `PagingDataAdapter<T, VH>` when the data is paged, infinite, remotely loaded page-by-page, or already exposed as `Flow<PagingData<T>>`.
2. Use `ListAdapter<T, VH>` when the UI receives complete immutable list snapshots.
3. Use `RecyclerView.Adapter<VH>` plus `AsyncListDiffer<T>` when a custom adapter base is required but the data is still list-like.
4. Use `DiffUtil.calculateDiff` manually only when the update operation cannot fit `ListAdapter`, `PagingDataAdapter`, or `AsyncListDiffer`.
5. Avoid `notifyDataSetChanged()`. Use precise adapter notifications only for truly imperative, small, non-list state changes, and prefer payloads for partial binds.

## Diff Rules

Every list-like adapter must have a clear diff contract.

```kotlin
object ItemDiff : DiffUtil.ItemCallback<ItemUiModel>() {
    override fun areItemsTheSame(oldItem: ItemUiModel, newItem: ItemUiModel): Boolean {
        return oldItem.id == newItem.id
    }

    override fun areContentsTheSame(oldItem: ItemUiModel, newItem: ItemUiModel): Boolean {
        return oldItem == newItem
    }

    override fun getChangePayload(oldItem: ItemUiModel, newItem: ItemUiModel): Any? {
        return ItemPayload.from(oldItem, newItem).takeIf { it.hasChanges }
    }
}
```

- `areItemsTheSame` checks stable identity, usually a database id, server id, or generated local id.
- `areContentsTheSame` checks rendered content, not only the raw entity when UI fields are derived.
- Use immutable UI models so equality is meaningful.
- Never use adapter position, object reference, or list index as identity unless the list is truly static.
- If stable IDs are enabled with `setHasStableIds(true)`, `getItemId()` must match the same identity used by `areItemsTheSame`.

## Adapter Patterns

For `ListAdapter`:

```kotlin
class ItemAdapter(
    private val onItemClick: (ItemUiModel) -> Unit
) : ListAdapter<ItemUiModel, ItemViewHolder>(ItemDiff) {
    init {
        stateRestorationPolicy = StateRestorationPolicy.PREVENT_WHEN_EMPTY
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ItemViewHolder {
        return ItemViewHolder.create(parent, onItemClick)
    }

    override fun onBindViewHolder(holder: ItemViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    override fun onBindViewHolder(
        holder: ItemViewHolder,
        position: Int,
        payloads: MutableList<Any>
    ) {
        if (payloads.isEmpty()) {
            onBindViewHolder(holder, position)
        } else {
            holder.bindPayload(getItem(position), payloads)
        }
    }
}
```

For Paging 3:

```kotlin
viewLifecycleOwner.lifecycleScope.launch {
    repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.items.collectLatest(adapter::submitData)
    }
}
```

- Use `LoadStateAdapter` for prepend/append headers, footers, retry, and end-of-pagination UI.
- Observe `adapter.loadStateFlow` for screen-level loading, empty, and error states.
- Do not mix Paging snapshots with manual mutable lists inside the adapter.

## ViewHolder Rules

- Bind from the item passed to `bind`, not from stored adapter positions.
- Register click listeners once in the `ViewHolder` constructor when possible, then read `bindingAdapterPosition` and guard against `NO_POSITION`, or pass the current bound item from `bind`.
- Clear or reset transient view state in every full bind: checkbox state, enabled state, alpha, progress, selected state, image placeholders, and listeners that depend on item identity.
- Cancel or replace asynchronous image or coroutine work when views are rebound. Prefer lifecycle-aware image loaders.
- Keep formatting and expensive computation outside `onBindViewHolder`; precompute in UI models or use cached formatters.
- Do not keep references from a `ViewHolder` to a `Fragment`, `Activity`, `ViewModel`, or long-lived scope.

## Fragment And Lifecycle

- Create the adapter once per view lifecycle, usually in `onViewCreated`.
- Clear binding references in `onDestroyView`.
- Collect flows with `viewLifecycleOwner.repeatOnLifecycle`.
- Submit immutable lists; do not mutate a list after passing it to `submitList`.
- Keep item click effects in the Fragment/ViewModel boundary, not in the adapter.

## Layout And Performance

- Use the right `LayoutManager`: `LinearLayoutManager`, `GridLayoutManager`, `StaggeredGridLayoutManager`, or a tested custom manager.
- For grids with loading footers, configure `SpanSizeLookup` so full-width rows span all columns.
- Use `setHasFixedSize(true)` only when RecyclerView size does not change with item content.
- Disable change animations only when they cause visual glitches and payloads cannot solve the issue.
- For nested RecyclerViews, use a shared `RecycledViewPool`, stable child adapters, and measured prefetch settings.
- Avoid nested scrolling conflicts; prefer a single RecyclerView with multiple view types or `ConcatAdapter` for composite screens.
- Use `ConcatAdapter` for headers, content, empty rows, footers, and independently owned sections instead of one large adapter with unrelated responsibilities.

## UI State

- Represent screen state outside the adapter: loading, empty, content, error, offline, and refreshing.
- Represent row state with stable ids, not positions.
- Selection, expansion, swipe state, and pending operations should live in ViewModel or a dedicated state holder and be projected into UI models.
- Avoid letting recycled views carry old visual state. Every bind should produce the same row for the same item.

## Multiple View Types

- Prefer sealed UI models for heterogeneous rows.
- Keep each ViewHolder small and type-specific.
- Diff by stable id plus row type; two different row types should not be treated as the same item.
- Use `ConcatAdapter` when sections have independent ownership, loading states, or update cadence.

## Code Review Checklist

When reviewing RecyclerView code, flag these issues:

- Uses `RecyclerView.Adapter` with mutable list updates but no `DiffUtil`, `AsyncListDiffer`, `ListAdapter`, or `PagingDataAdapter`.
- Calls `notifyDataSetChanged()` for normal list updates.
- Uses position as item identity or stores positions across binds.
- Mutates submitted lists after `submitList`.
- Performs I/O, heavy formatting, database work, or network calls from binding.
- Leaves recycled visual state uncleared.
- Collects flows outside `viewLifecycleOwner.repeatOnLifecycle`.
- Mixes Paging 3 with manual list mutation.
- Puts Fragment, Activity, ViewModel, or coroutine scope references inside ViewHolder.
- Lacks tests for diff identity/content behavior when the adapter has custom diff logic.

## Testing Guidance

- Unit test custom `DiffUtil.ItemCallback` behavior for identity, content equality, and payloads.
- Test ViewModel list mapping separately from adapter rendering.
- For Paging, test `PagingData` transformations and load-state handling.
- Add UI or screenshot tests only when the change affects row layout, selection, empty/error states, or load-state presentation.

## Implementation Style

- Follow the app's existing architecture, package layout, naming, binding technology, and dependency versions.
- Prefer Kotlin examples unless the target module is Java.
- Keep adapter APIs small: data in via `submitList` or `submitData`, events out via callbacks.
- Do not introduce a new architecture framework just to improve a RecyclerView.
- When refactoring, keep behavior equivalent first, then improve diffing, state, and lifecycle safety.
