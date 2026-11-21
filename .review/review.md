## 评审结论：**需修改**（3 个阻断、4 条建议；无安全问题）

独立评审，基于 `git diff origin/main...HEAD`（HEAD `7f58067`）与周边代码，命令都是真跑的。

先说好的一面：类型映射 / ISO 下发（本体侧）、「已有键清空 = 删键」、插件侧嵌套与对象列表的 `_without_none`、`Annotated` 外壳剥离、`isScalarKind` 收敛都做对了；`_resolved_field_types` 有 `lru_cache`，`_validate_payload` 每字段调用是缓存命中，没有性能顾虑；时间值不经过任何掩码/密钥路径，没有凭据泄露面；文档、流程图戳、`.changes` 都跟上了。

阻断项都集中在**「对象列表新增行」**和**插件侧取值契约**这两处 —— PR 描述里「三条路径一致」「插件…值统一用 `isoformat()` 下发」这两句不成立。

---

### 阻断 1：本体配置**新增行**里清空可选时间字段 → 保存抛 `ConvertError`（HTTP 500）

链路（实测复现）：

1. `builtin_plugins/dashboard/config_parts/schema.py:178-180`：控件清空回 `""`，`_coerce_leaf` 把它变成 `None`；
2. `config_parts/toml.py:258-282` `_diff_sequence`：**新增元素**（`index >= len(current)`）整行原样透传，`None` 留在行里；
3. `config_parts/toml.py:318-330` `_merge_sequence`：新元素直接 `document.append(tomlkit.item(item))`，tomlkit 不接受 `None`；
4. `api_parts/config.py:247-257` 最后兜成 500「保存配置失败: Unable to convert an object of <class 'NoneType'> to a TOML item」。

复现（`Root.rows: list[Row]`、`Row.at: Optional[datetime] = None`，文件已有 1 行，提交 2 行且第 2 行 `at` 为空）：

```
coerced: {'rows': [{'at': datetime(2026,11,16,23,39,55), 'note': 'a'}, {'at': None, 'note': 'b'}]}
errors : []                # _validate_payload 认为合法
diff   : {'rows': [{'at': datetime(...), 'note': 'a'}, {'at': None, 'note': 'b'}]}
!! SAVE WOULD RAISE: ConvertError Unable to convert an object of <class 'NoneType'> to a TOML item
```

对照组（**已有行**内清空是好的）：diff 为 `{'at': None}`，`_merge_into_document` 删键，落盘 `[[rows]]\nnote = "a"`。

插件侧同一问题本 PR 已经用 `plugin_config.py:295-305` `_without_none` + `:478` 修掉并补了 `test_plugin_save_drops_null_inside_object_list`；dataclass 侧没有等价处理，这就是「三条路径一致」不成立的地方。当前仓库还没有 temporal 的本体字段，所以今天不会炸；但这正是本 PR 启用的能力，第一个给本体 `list[...]` 的行加 `Optional[datetime]` 的人就会拿到 500。建议在 `_merge_sequence` 写入新元素前做一次与插件侧等价的清洗（dict 删键、数组丢元素），或在 `_diff_sequence` 生成新元素时就清洗。

### 阻断 2：新行的空时间字段初始值是 `''` 而不是 `null` → 「新增一行、不填时间」两条路都存不进去

`frontend/src/components/schema/fieldTypes.ts:78-83`：`initial = field.default === '' ? fallback : (field.default ?? fallback)`；可选时间字段的 `default` 是 `null`，于是 `null ?? ''` 得到 `''`。`schema/ModelList.tsx:23` 的「新增」正是 `defaultsFromFields(item_fields, …)`，新行一出生就带 `''`：

- 本体：`''` → `None` → 就是阻断 1 的 500；
- 插件：`''` 过不了 Pydantic（实测 `Optional[datetime]` 拒绝 `""`、接受 `None`），`api_parts/config.py:80-85` 只回通用文案「字段值不符合配置要求」+ 路径 `rows.0.at`，用户看到的是「刚加一行、什么都没填就报错」。

建议 temporal kind 的空默认值统一给 `null`（= 不设置），与「清空 = 删除该键」的语义对齐。

### 阻断 3：插件侧取到的值和落盘的都不是 ISO 8601（与 PR/文档契约不符）

PR 描述写「Pydantic 字段值统一用 `isoformat()` 下发」，`docs/04-功能文档/插件设置界面.md` 写「取值为 ISO 8601（`YYYY-MM-DDTHH:MM:SS`）」。实测插件路径走的是 `plugin_config.py:82-95` 自己的 `_jsonable`，非 `for_toml` 分支对时间类型落到 `str(value)`，于是：

```
文件内容        : run_at = 2026-11-16T23:39:55        （原生 TOML datetime）
editor.read()   : '2026-11-16 23:39:55'               ← 空格分隔，不是 ISO
schema value    : {'kind': 'datetime', 'value': '2026-11-16 23:39:55'}
面板保存后文件  : run_at = "2026-11-16 23:39:55"      ← 变成带引号字符串，且丢 T
```

（提交 ISO 字符串 `"2026-11-16T23:39:55"` 时，`normalize_config_values` 会把它换成 `datetime` 对象，再经 `prepare_values` 的 `_jsonable` 变成空格形态。）

影响：前端 `toInputValue` 的宽松解析能兜住空格分隔，所以 UI 看不出来；但（a）插件作者拿到的字符串不是 ISO，按 ISO 做字符串比较/拼外部 API 会踩坑；（b）一次面板保存就把原生 TOML datetime 改成带引号的空格字符串，`date` / `time` 同样从原生类型退化成字符串；（c）PR 描述与文档的契约是错的。``_jsonable`` 是既有代码，所以这不是新引入的回归，但**本 PR 声称插件侧也是 ISO，实际不是**，要么改 `_jsonable`（非 `for_toml` 分支用 `isoformat()`，保存时走 `for_toml=True` 保留原生类型），要么把文档与描述改成如实描述。

---

### 建议（不阻断）

1. **注释与实现不符**：`config_parts/schema.py:55-67` 注释说「解析失败…**保证单个坏字段不拖垮整张表单**」，但 `get_type_hints(schema)` 是按类整体解析，任一标注不可解析（例如只在 `TYPE_CHECKING` 里导入的类型）就返回 `{}`，该类**所有**字段退回原始标注、时间字段退化成 JSON。要么逐字段解析，要么把注释写实；这条回退路径没有测试。
2. **同一根因的另一处**：`config_parts/toml.py:48` `_managed_tree` 仍用 `field_obj.type`。本 PR 为「`from __future__ import annotations` 让 `field.type` 变字符串」这个前提加了 `_resolved_field_types`，保存侧的未知键保护却还是老写法。现在 `config/schemas/` 下没有 future annotations（实测 `_managed_tree(BotConfig)` 21 项无退化），所以不影响本 PR，记一笔免得下次再踩。
3. **`.gitignore:181-183` 属夹带的无关改动**：本 PR 顺手加了 `tmp/`（commit `7f58067`），与功能无关；该文件通篇 CRLF，新加的 `tmp/` 既没有行尾也没有末尾换行（`\ No newline at end of file`）。建议从这个 PR 里拿掉，或至少补回 CRLF 结尾。
4. **两处一致性小项**：`该字段必填，不能清空`（`schema.py:302-307`）只在**本体**校验路径出现，插件必经 Pydantic、只能回通用文案，PR 描述没区分，建议文档说清；`TemporalField.tsx:99` 的 `step={mode === 'date' ? undefined : 1}` 是「保留秒」的行为要点，但测试只断言了 `type`，没断言 `step`，`toSubmitValue`（`:57-63`）的补秒也依赖浏览器是否省略秒，建议各补一条断言。

### 测试质量

- 后端新增 26 条用例**有真断言**：kind 映射、ISO 下发、`_coerce_payload`、必填文案、插件嵌套/对象列表清空都锁住了；我实跑 26 passed（与描述一致）。
- 但**保存链路只在字符串层面验证**：`test_dataclass_save_with_null_removes_existing_key` 手工构造 diff 并把**字符串**传给 `_merge_into_document`，没有走 `_coerce_payload → _diff_document → _merge_into_document` 真链路，也没用 `datetime/date/time` **对象**写 tomlkit —— 阻断 1 正好漏在这个缺口里，补一条真链路用例即可复现（我这边现在会红）。
- 前端 17 条用例断言落点正确（控件 `type`/`value`/`onChange` 参数），实现回归时会失败，质量可以。

### 跑过的检查（真实输出）

- `uv run ruff check .` → `All checks passed!`（我自己的评审产物已从 `.py` 移走；`--exclude .review` 结果相同、同样是全绿，可确认本 PR 干净）
- `uv run python scripts/flow/check_flow_diagrams.py --strict-drift` → `结论：阻断 0 项，警告 1 项 -> 通过`（警告是既有的 `00-overview` 节点 43 > 40）
- `uv run python scripts/check_pr_size.py --base $(git merge-base origin/main HEAD) --head HEAD` → `体积门禁通过：14 个代码文件参与检查，无文件新增超过 800 行`
- `uv run python scripts/check_pr_title.py --title "feat(dashboard): 支持配置表单的日期与时间控件" --strict` → `标题校验通过`
- `uv run pytest app/tests/modules/builtin_plugins/test_temporal_fields.py -m "not browser and not network and not slow and not llm"` → `26 passed in 25.35s`
- 既有相关用例（`test_dashboard_config_coercion` / `_unknown_keys` / `_masking` / `test_dashboard_describe_options` / `test_plugin_config_schema` / `_controls` / `_form_aliases` / `_secrets` / `_source_validation` / `test_converter` / `test_temporal_fields`，同 marker）→ `143 passed, 1 warning in 13.04s`（warning 为既有 aiohttp `NotAppKeyWarning`）
- 前端：**未跑 vitest**（本 worktree 无 node_modules，本机 Node v24，PR 说用 Node 22 构建）。改为核验已提交产物：`web/assets` 33 个 chunk 之间的 `./X-hash.js` 引用 **0 处缺失**，`index.html` 的 `assets/index-D6XTg956.js` / `index-BA0-RYZu.css` 都存在，`datetime-local` 出现在 `ConfigManager-`/`FormField-`/`index-`/`ScheduledTasks-` 四个包里 → 产物确实重建过、引用自洽。
- 环境备注：本 worktree 的 `.venv` 初始缺 workspace 依赖（`ModuleNotFoundError: tomlkit`），先 `uv sync --frozen --all-packages` 才能跑 pytest；之后 `git status` 干净，未改 `uv.lock`、未改源码。

### 核对 PR 描述

- 「现有配置 schema 没有时间类字段，升级不涉及迁移」→ **成立**：`config/schemas/**` 与内置插件 config 模型都没有 `datetime/date/time` 字段（`streaming_parser/panel_models.py` 的 `datetime | None` 是面板/DB 模型，不走 `describe_pydantic_model`）。
- 「现有配置都没有 `Annotated` 写法」→ **对配置路径成立**（`config/` 下无 `Annotated`；`panel_models.py:24` 的 `GroupId = Annotated[str, …]` 只服务面板动作模型）。
- 「值统一用 `isoformat()` 下发」→ 本体**成立**，插件**不成立**（阻断 3）。
- 「三条清空路径一致」→ **不成立**（阻断 1/2）。
- 数字：新增后端 26 条、前端 17 条与文件里的用例数对得上；`8371 passed` 我**没有复现**（按要求不跑全量离线套件）。另有一个与本 PR 无关、但会绊住复现的既有问题：这个 base 上 `import neobot_app.config.models` 直接失败（`ImportError: cannot import name 'Dashboard' from neobot_app.config.schemas.bot`，该文件与 `origin/main` 一字不差），复现时请从 `neobot_app.config.schemas.bot` 导入。

### CI 现状（与本 PR 代码无关，供作者参考）

- `PR 评审（阻断）`：发这条评论前是 **fail**（最后一次提交晚于最后一条评审），现在已 **pass**。
- `check`（QuailEgg PR）：红在**最后一步** `gh pr comment --edit-last -F plan.md` → `GraphQL: Resource not accessible by integration (addComment)`，是 bot 缺 PR 评论权限，不是 `qegg check --ci` 失败；建议管理员检查 App 的 Pull requests / Issues 写权限。
- 其余检查（体积限制、分支流向、修复 PR 关联 issue、前端、CLI 模板验收、SDK 回归）全绿。

