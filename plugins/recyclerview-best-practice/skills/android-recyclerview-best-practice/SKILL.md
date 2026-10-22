---
name: android-recyclerview-best-practice
description: Use when creating, reviewing, or refactoring Android RecyclerView code, especially adapters, ViewHolders, DiffUtil, ListAdapter, PagingDataAdapter, item state, lifecycle collection, and performance.
---

# Android RecyclerView Best Practice

## Project independence

Use the project's own adapter/state code and normal AndroidX RecyclerView/Paging dependencies. Do not add this AI plugin as a build/runtime prerequisite, copy its installation paths into the project, or require its skill invocation in project documentation. Android Gradle/compiler plugins and other required libraries remain legitimate project dependencies.

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
        host.items.collectLatest(adapter::submitData)
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
- Route item callbacks through the UI adapter into the framework-independent Host.
  Keep navigation and other effects in the Host's effect channel; the view renders them.

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
- Selection, expansion, swipe state, and pending operations live in the framework-independent Host and are projected into immutable UI models. A ViewModel may adapt Host lifetime/state to Android.
- Avoid letting recycled views carry old visual state. Every bind should produce the same row for the same item.

## Multiple View Types

- Prefer sealed UI models for heterogeneous rows.
- Keep each ViewHolder small and type-specific.
- Diff by stable id plus row type; two different row types should not be treated as the same item.
- Use `ConcatAdapter` when sections have independent ownership, loading states, or update cadence.

## Testing Guidance

- Unit test custom `DiffUtil.ItemCallback` behavior for identity, content equality, and payloads.
- Test Host list mapping separately from adapter rendering.
- For Paging, test `PagingData` transformations and load-state handling.
- Add UI or screenshot tests only when the change affects row layout, selection, empty/error states, or load-state presentation.

## Implementation Style

- Follow the app's existing architecture, package layout, naming, binding technology, and dependency versions.
- Prefer Kotlin examples unless the target module is Java.
- Keep adapter APIs small: data in via `submitList` or `submitData`, events out via callbacks.
- Do not introduce a new architecture framework just to improve a RecyclerView.
- When refactoring, keep behavior equivalent first, then improve diffing, state, and lifecycle safety.

## Upstream improvement feedback

- When using this plugin reveals an actionable bug, missing guidance, or reusable improvement, report it to [storytellerF/me](https://github.com/storytellerF/me/issues). Identify the owning plugin and skill; do not report project-specific problems without evidence that the plugin needs a change. Finish the user's primary task before non-blocking feedback work.
- Before any search or submission, reduce the finding to a privacy-safe summary. Never send raw conversations, private source code, logs, screenshots, credentials, personal identifiers, account data, or private paths/URLs. Use synthetic examples and the minimum non-sensitive environment details needed to explain the problem. If safe disclosure is impossible, keep the finding local.
- Search both open and closed upstream issues using the plugin name and sanitized symptom keywords. Read likely matches and their resolution; do not rely only on title matches. Reuse a matching issue link instead of opening a duplicate. Add a comment only when it supplies materially new, safe evidence and posting is authorized. A closed issue warrants a new report only for a distinct regression or uncovered case, with a link explaining the difference.
- Submit a new issue when no duplicate exists and the user has authorized upstream reporting in the current session or standing instructions. This rule alone does not authorize external posting. Honor existing authorization without asking again; otherwise prepare a sanitized draft for approval.
- Include the plugin/skill and version, observed and expected behavior, a minimal synthetic reproduction or concrete improvement proposal, and relevant duplicate-search results. Use a concise title prefixed with the plugin name.
- If search, authentication, or submission fails, retain the sanitized draft and explain the blocker; do not post without completing duplicate checks. After an uncertain submission result, check for the created issue before retrying. Return the existing or created issue URL, or clearly mark the report as an unsubmitted draft.
