---
name: recyclerview-sentinel-viewholder
description: 诊断或修复聊天、时间线、信息流及顶部刷新列表中 RecyclerView 前插可见性、滚动锚定或插入动画问题，或用户明确要求哨兵行时使用。先判断是否适合，不为每个 RecyclerView 都添加哨兵。
---

# RecyclerView 哨兵 ViewHolder

## 使用项目的独立性

哨兵作为项目自身的 UI 数据和 adapter 代码实现，使用正常 AndroidX 依赖。不要让渲染、测试或项目指引依赖本 AI 插件的名称、文件或安装。必需构建插件、编译器插件和库仍为普通项目依赖，可正常声明。

## 核心方法

先检查已有差异计算与滚动锚定行为。只有稳定起始行能解决已证实的前插问题时，才在 adapter 数据开头添加哨兵；否则保留正常差异计算。

没有哨兵时：

```text
old: 1 2
new: 0 1 2
diff: insert item 0 at adapter position 0
```

RecyclerView 和 `LinearLayoutManager` 可能将其解释为在当前锚点之前插入。某些前插流程中，新行的表现像是出现在可见区域之外。

有哨兵时：

```text
old: sentinel 1 2
new: sentinel 0 1 2
diff: insert item 0 at adapter position 1
```

哨兵始终作为稳定首行，将差异插入下标变为 1。但这本身不保证可见性或滚动行为：屏幕外的哨兵仍在可见锚点之前。应结合实际 LayoutManager、滚动位置、反向布局和条目高度，验证预期布局与锚定行为。

## 数据模型

将哨兵表示为具有稳定标识的真实 UI 模型。

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

构造提交列表时将哨兵放在首位：

```kotlin
fun List<ItemUiModel>.withSentinel(): List<RowUiModel> {
    return listOf(RowUiModel.Sentinel) + map {
        RowUiModel.Item(id = it.id, title = it.title)
    }
}
```

## 差异计算约定

哨兵必须始终被识别为同一条目。

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

- 普通行不得复用哨兵 ID。
- 标识中包含行类型，让 `Sentinel` 和 `Item(Long.MIN_VALUE)` 永不冲突。
- 启用 `setHasStableIds(true)` 时，`getItemId` 一致返回 `stableId`。

## ViewHolder 结构

哨兵 ViewHolder 应行为确定、不可交互，并有明确的视觉设计意图。

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

哨兵布局要求：

- 使用小型间隔、页眉容器，或产品确有的顶部操作入口。
- 多次绑定之间高度保持稳定。
- 除非是真实页眉，否则避免点击、焦点、无障碍噪声和动态内容。
- 谨慎使用 `0dp` 高度。它可作为纯差异锚点，但若体验依赖可见性或动画，需要在目标布局中测试。
- 哨兵使无内容时的 `itemCount` 也非零，因此 `PREVENT_WHEN_EMPTY` 不会等真实行到达才恢复状态。必要时采用显式恢复策略，或分别管理页眉和内容 adapter。

## Adapter 位置辅助方法

adapter 位置 `0` 已是哨兵，不能将原始 adapter 位置直接作为业务位置。

```kotlin
private const val SENTINEL_COUNT = 1

fun adapterPositionToItemIndex(adapterPosition: Int): Int {
    return adapterPosition - SENTINEL_COUNT
}

fun itemIndexToAdapterPosition(itemIndex: Int): Int {
    return itemIndex + SENTINEL_COUNT
}
```

所有滚动、选中和点击代码都应检查：

- 绑定的行是 `Sentinel` 时忽略点击。
- 调用 `scrollToPosition`、`smoothScrollToPosition` 或 `findViewHolderForAdapterPosition` 前，转换条目下标。
- 测试同时断言原始 adapter 位置和用户可见条目下标。

## Paging 说明

`PagingDataAdapter` 优先使用 Paging 内置行为。只有 adapter 在分页流之外管理顶部行时，才使用哨兵。

可选方式：

- 用 `ConcatAdapter`，在分页 adapter 前放置只有一行的哨兵或页眉 adapter。
- 若代码库已经管理该管线，也可先映射为共享行模型类型，再使用 Paging 的 `insertHeaderItem`。仅映射条目不会添加页眉。

不要向数据库分页源注入哨兵。它属于 UI 结构，不是领域数据。

## 上游改进反馈

- 发现有明确改进方向的插件缺陷或可复用的改进建议时，向 [storytellerF/me](https://github.com/storytellerF/me/issues) 反馈，并注明插件和 skill。若问题仅属于当前项目，且没有插件缺陷的证据，则不在此范围内。先完成主要任务，再处理不影响当前工作的反馈。
- 搜索或发布之前，将证据整理为不含隐私的最小摘要或合成复现案例。不得泄露原始对话、私有代码、日志、截图、凭据、个人或账户信息，以及私有路径和 URL。如果无法安全披露，就只在本地保留发现。
- 搜索已打开和已关闭的 issue，阅读可能匹配的报告及其解决方案。优先复用已有报告；如果是不同的回归问题或尚未覆盖的场景，可另建 issue 并关联原报告。发布新 issue 或有实质帮助的评论必须已经获得用户授权；本规则本身不授予发布权限。未获授权时，准备一份尚未提交的草稿。
- 反馈应包含插件和 skill 版本、实际与预期行为、复现步骤或建议，以及重复报告的检索结果。新 issue 的标题应以插件名开头。访问或提交失败时，保留草稿并说明阻碍。提交结果不确定时，先确认是否已成功，再考虑重试。返回报告链接，或明确标注草稿尚未提交。
