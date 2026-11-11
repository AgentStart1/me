---
name: android-recyclerview-best-practice
description: 实现、调试、审查或重构 Android RecyclerView 列表时使用，涵盖 adapter 更新、行状态、回收、分页、生命周期和性能。
---

# Android RecyclerView 最佳实践

## 使用项目的独立性

使用项目自身的 adapter、状态代码及正常 AndroidX RecyclerView、Paging 依赖。不要将本 AI 插件作为构建或运行前提，不向项目复制其安装路径，也不在项目文档中要求调用其 skill。Android Gradle、编译器插件和其他必需库仍是合法项目依赖。

## 核心选择

除非代码库已有难以兼容的成熟抽象，否则始终选择内置差异计算的 adapter。

1. 数据分页、无限加载、从远端逐页加载，或已经以 `Flow<PagingData<T>>` 暴露时，使用 `PagingDataAdapter<T, VH>`。
2. UI 接收完整不可变列表快照时，使用 `ListAdapter<T, VH>`。
3. 需要自定义 adapter 基类，但数据仍是列表时，使用 `RecyclerView.Adapter<VH>` 配合 `AsyncListDiffer<T>`。
4. 只有更新操作无法适配 `ListAdapter`、`PagingDataAdapter` 或 `AsyncListDiffer` 时，才手动使用 `DiffUtil.calculateDiff`。
5. 避免 `notifyDataSetChanged()`。只有确属命令式、规模很小且不涉及列表的数据状态变更，才使用精确 adapter 通知；局部绑定优先使用 payload。

## 差异计算规则

每个列表型 adapter 都必须有清楚的差异计算约定。

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

- `areItemsTheSame` 检查稳定标识，通常为数据库 ID、服务端 ID 或生成的本地 ID。
- `areContentsTheSame` 检查渲染内容；UI 字段有派生值时，不能只比较原始实体。
- 使用不可变 UI 模型，让相等判断有意义。
- 除非列表确实静态，否则绝不使用 adapter 位置、对象引用或列表下标作为标识。
- 通过 `setHasStableIds(true)` 启用稳定 ID 时，`getItemId()` 必须与 `areItemsTheSame` 使用的标识一致。

## Adapter 模式

`ListAdapter` 示例：

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

Paging 3 示例：

```kotlin
viewLifecycleOwner.lifecycleScope.launch {
    repeatOnLifecycle(Lifecycle.State.STARTED) {
        host.items.collectLatest(adapter::submitData)
    }
}
```

- 前置和后置加载的页眉、页脚、重试及分页结束 UI 使用 `LoadStateAdapter`。
- 页面级加载、空状态和错误状态观察 `adapter.loadStateFlow`。
- 不在 adapter 内混用 Paging 快照与手动可变列表。

## ViewHolder 规则

- 使用传给 `bind` 的条目绑定，不依赖保存的 adapter 位置。
- 尽可能在 `ViewHolder` 构造函数中一次注册点击监听器，点击时读取 `bindingAdapterPosition` 并检查 `NO_POSITION`，或从 `bind` 传递当前绑定条目。
- 每次完整绑定都清除或重置临时视图状态：复选框、启用状态、透明度、进度、选中状态、图片占位，以及依赖条目标识的监听器。
- 视图重新绑定时，取消或替换异步图片或协程工作。优先使用感知生命周期的图片加载器。
- 格式化和昂贵计算放在 `onBindViewHolder` 外；在 UI 模型中预计算或使用缓存格式化器。
- `ViewHolder` 不持有 `Fragment`、`Activity`、`ViewModel` 或长生命周期作用域的引用。

## Fragment 与生命周期

- 每个视图生命周期只创建一次 adapter，通常在 `onViewCreated`。
- 在 `onDestroyView` 清除 binding 引用。
- 通过 `viewLifecycleOwner.repeatOnLifecycle` 收集 flow。
- 提交不可变列表；传给 `submitList` 后不再修改。
- 条目回调经 UI 适配层进入独立于框架的 Host。导航和其他副作用留在 Host 副作用通道，由视图呈现。

## 布局与性能

- 选择合适的 `LayoutManager`：`LinearLayoutManager`、`GridLayoutManager`、`StaggeredGridLayoutManager` 或经过测试的自定义管理器。
- 网格有加载页脚时，配置 `SpanSizeLookup`，让全宽行跨越全部列。
- 只有 RecyclerView 尺寸不随条目内容变化时，才使用 `setHasFixedSize(true)`。
- 只有变化动画导致视觉异常且 payload 无法解决时，才禁用变化动画。
- 嵌套 RecyclerView 使用共享 `RecycledViewPool`、稳定的子 adapter，以及经测量确定的预取设置。
- 避免嵌套滚动冲突；复合页面优先用单个多视图类型 RecyclerView 或 `ConcatAdapter`。

## UI 状态

- 页面状态放在 adapter 外：加载、空、内容、错误、离线和刷新。
- 用稳定 ID 表示行状态，不用位置。
- 选中、展开、滑动状态和待执行操作由独立于框架的 Host 管理，再映射到不可变 UI 模型。ViewModel 可将 Host 生命周期和状态适配到 Android。
- 不让回收视图携带旧视觉状态。同一条目每次绑定都应得到相同行表现。

## 多视图类型

- 异构行优先使用密封 UI 模型。
- 每种 ViewHolder 保持小型、专一。
- 通过稳定 ID 加行类型判断差异；不把不同类型的行视为同一条目。
- 各区段的管理责任、加载状态或更新节奏独立时，页眉、内容、空行和页脚使用 `ConcatAdapter`。

## 测试指引

- 单元测试自定义 `DiffUtil.ItemCallback` 的标识、内容相等和 payload 行为。
- Host 列表映射与 adapter 渲染分别测试。
- Paging 测试 `PagingData` 转换和加载状态处理。
- 只有变更影响行布局、选中、空或错误状态、加载状态呈现时，才添加 UI 或截图测试。

## 实现风格

- 遵循应用已有架构、包结构、命名、绑定技术和依赖版本。
- 除非目标模块使用 Java，否则优先使用 Kotlin 示例。
- adapter API 保持小型：通过 `submitList` 或 `submitData` 输入数据，通过回调输出事件。
- 不要仅为改进 RecyclerView 就引入新架构框架。
- 重构先保持行为等价，再改进差异计算、状态和生命周期安全。

## 上游改进反馈

- 发现有明确改进方向的插件缺陷或可复用的改进建议时，向 [storytellerF/me](https://github.com/storytellerF/me/issues) 反馈，并注明插件和 skill。若问题仅属于当前项目，且没有插件缺陷的证据，则不在此范围内。先完成主要任务，再处理不影响当前工作的反馈。
- 搜索或发布之前，将证据整理为不含隐私的最小摘要或合成复现案例。不得泄露原始对话、私有代码、日志、截图、凭据、个人或账户信息，以及私有路径和 URL。如果无法安全披露，就只在本地保留发现。
- 搜索已打开和已关闭的 issue，阅读可能匹配的报告及其解决方案。优先复用已有报告；如果是不同的回归问题或尚未覆盖的场景，可另建 issue 并关联原报告。发布新 issue 或有实质帮助的评论必须已经获得用户授权；本规则本身不授予发布权限。未获授权时，准备一份尚未提交的草稿。
- 反馈应包含插件和 skill 版本、实际与预期行为、复现步骤或建议，以及重复报告的检索结果。新 issue 的标题应以插件名开头。访问或提交失败时，保留草稿并说明阻碍。提交结果不确定时，先确认是否已成功，再考虑重试。返回报告链接，或明确标注草稿尚未提交。
