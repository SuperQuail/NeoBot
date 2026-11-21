## 复核结论：**仍需修改**（1 处一行逻辑 + 1 条测试；上一轮 3 个阻断项已确认修好）

复核对象：`4fdd2206`（含 `b906d4bd` 合入 `origin/main`）。三个阻断项我按原复现路径逐条重跑，都对；下面只剩一处新引入的逻辑问题，以及几条不阻断的遗留。

### 一、三个阻断项的复核（实测）

**1) 本体新增行清空可选时间字段不再 500、键也不落盘 —— 已修好**

真链路（`_coerce_payload` → `_validate_payload` → `_diff_document` → `_merge_into_document`，前端回传的是 `""`）：

```
coerced: {'rows': [{'name':'a','at': datetime(...)}, {'name':'b','at': None}]} | errors: []
dumps : '[[rows]]\nname = "a"\nat = 2026-11-16T23:39:55\n[[rows]]\nname = "b"\n'
read  : {'rows': [{'name':'a','at': datetime(...)}, {'name':'b'}]}   # at 键不存在 = 未设置
```

表数组在文件里还不存在时的第一行（`other = 1\n` + 新增 `rows`）也正确写成 `[[rows]]`，`None` 被剔掉。

**2) 前端新行时间字段初值改为 `null` —— 已修好（但见第二节）**

`TemporalField.test.tsx` 19 passed（新增 2 条）；新行未填 / 清空后提交的都是 `null`，不再传 `''`。

**3) 插件读出 ISO 8601、保存后仍是原生 datetime —— 已修好**

```
_jsonable(datetime)   -> '2026-11-16T23:39:55'      （读给面板：ISO，T 分隔）
_jsonable(for_toml)   -> datetime.datetime(...)     （写盘：原生对象）
read config value     -> '2026-11-16T23:39:55'
schema value          -> '2026-11-16T23:39:55'
save 后文件           -> 'run_at = 2026-11-16T23:39:55\n'   （不再降级成带引号字符串）
save 后再 read        -> '2026-11-16T23:39:55'
```

### 二、仍需修改：时间类字段声明的 `default` 被忽略

**`frontend/src/components/schema/fieldTypes.ts:81`** —— `else if (TEMPORAL_KINDS.includes(field.kind)) initial = null;` 排在读取 `field.default` 的分支**之前**，于是时间类字段的声明默认值被无条件丢掉。

实测（临时用例，跑完已删）：descriptor `{kind:'datetime', default:'2026-01-01T00:00:00', required:true}` →
`defaultsFromFields` 返回 `{run_at: null}`，断言 `expected null to be '2026-01-01T00:00:00'` 失败。

后果不只是「初值不好看」：

- 插件 `list[Model]` 里 `run_at: datetime = Field(default_factory=...)`（`is_required()==False`）的新行会被塞 `null`，而 Pydantic 对**非 Optional** 的 `null` 直接拒绝（实测 `{'rows': [{'run_at': None}]}` → REJECTED；`{'rows': [{}]}` → 用默认值成功）—— 正是这次修复想消掉的「新行存不进去」，只是换了个触发条件；
- 本体侧同样：`run_at: datetime = datetime(...)` 的新行初值变空，必填语义下还会直接报「该字段必填，不能清空」。

建议：

```ts
// 尊重声明默认值；只有后端给空（未设置）时才用 null
else if (TEMPORAL_KINDS.includes(field.kind)) initial = field.default === '' ? null : (field.default ?? null);
```

并补一条**带 default 的 temporal descriptor** 用例（现有新增用例的 descriptor 都是 `default: null`，覆盖不到这条路径）。

### 三、变异验证（撤回修复后新用例确实会红，跑完已 `git checkout --` 恢复）

| 撤回的修复 | 结果 |
|---|---|
| `toml.py` 去掉 `_merge_sequence` / `_merge_into_document` 里的 `_without_none` | **2 failed**（两个新增行用例，`ConvertError: Unable to convert ... NoneType`） |
| `plugin_config.py` 的 `_jsonable` 回 `str()`、`prepare_values` 回非 `for_toml` | **3 failed**（`test_plugin_jsonable_uses_isoformat[datetime]`、`test_plugin_save_roundtrip_keeps_native_datetime`、`test_source_validates_native_toml_defaults[datetime]`） |
| `fieldTypes.ts:81` 整行删掉 | **2 failed**（新增的 `defaultsFromFields` 两条） |

恢复后：`test_temporal_fields.py` 30 passed；`TemporalField.test.tsx` 19 passed；工作树 `git status` 干净（只有我未提交的 `.review/`）。

### 四、按你点名要查的副作用（均无阻断）

- **`_without_none` 的递归范围**：会把**任何** `None` 当「不设置」丢掉，包括数组元素。有类型的列表不会被误伤（`list[str]` 里 `None` 先被 `_validate_payload` 拦成 `tags[1] 类型应为 str，实际为 NoneType`）；只有无类型 `list[Any]` 会静默丢元素（实测 `['a', None, 'b']` → `['a','b']`）。当前仓库没有裸 `list` 配置字段，属理论边界，可以不修。
- **`_jsonable` 改 isoformat 的其它消费方**：只在 `plugin_config.py` 内部（`read` / `describe_mapping` / `_defaults` / `_stored` / `prepare_values`），对外就是面板 API 与 schema，正是要改成 ISO 的两处；`observability/debug.py` 的 `DebugRecorder` 用的是自己的 `_to_jsonable`，不受影响。
- **`prepare_values` 改 `for_toml=True`**：只有 2 个调用点（API 校验前、`save` 内）。API 侧拿到的是表单 JSON（字符串），本来就不会命中时间分支；`save` 侧拿到的是已类型化的值，正是要保留原生 datetime 的地方。`app/tests/modules/builtin_plugins` 全量 **771 passed**，无回归。
- **所有时间类初值改 null 对已有字段**：仓库现有配置没有时间类字段，无现存影响；唯一代价就是第二节那一条。

### 五、跑过的命令（真实输出）

- `uv run ruff check . --exclude .review` → `All checks passed!`
- `uv run python scripts/flow/check_flow_diagrams.py --strict-drift` → `结论：阻断 0 项，警告 1 项 -> 通过`（既有 `00-overview` 节点 43 > 40）
- `uv run python scripts/check_pr_size.py --base $(git merge-base origin/main HEAD) --head HEAD` → `体积门禁通过：15 个代码文件参与检查，无文件新增超过 800 行`
- `uv run python scripts/check_pr_title.py --title "feat(dashboard): 支持配置表单的日期与时间控件" --strict` → `标题校验通过`
- `uv run pytest app/tests/modules/builtin_plugins -m "not browser and not network and not slow and not llm"` → `771 passed, 5 deselected`
- `pnpm exec vitest run src/test/TemporalField.test.tsx` → `19 passed`（这次有 node_modules，前端用例已实跑）
- 产物核验：`web/assets` 33 个 chunk 互引 0 缺失，`index.html` 引用的 `assets/index-DK-sK4QN.js` / `index-*.css` 均存在

### 六、上一轮遗留（不阻断，维护者自行取舍）

- `.gitignore:181-183` 仍夹带与本功能无关的 `tmp/`（3 行，且文件末尾无换行）。
- `config_parts/schema.py:55-67` 注释仍写「保证单个坏字段不拖垮整张表单」，实际是整类回退。
- `config_parts/toml.py:48` `_managed_tree` 仍用 `field_obj.type`（同一 future-annotations 前提，本 PR 未覆盖，当前无影响）。
- `TemporalField.tsx:99` 的 `step=1` 仍没有断言。
