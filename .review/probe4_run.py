"""PR325 re-review probes (not committed)."""
from __future__ import annotations

import tempfile
import pathlib
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import List, Optional

import tomlkit
from pydantic import BaseModel

from neobot_app.builtin_plugins.dashboard.config_parts.schema import (
    _coerce_payload,
    _validate_payload,
)
from neobot_app.builtin_plugins.dashboard.config_parts.toml import (
    _diff_document,
    _merge_into_document,
)
from neobot_app.builtin_plugins.dashboard.plugin_config import (
    PluginConfigEditor,
    _jsonable as plugin_jsonable,
)
from neobot_app.builtin_plugins.dashboard.config_parts.normalize import normalize_config_values


@dataclass
class Row:
    name: str = ""
    at: Optional[datetime] = None


@dataclass
class Root:
    rows: List[Row] = field(default_factory=list)


print("== A1: 本体 新增行 + 前端回传空串（真链路：coerce -> validate -> diff -> merge） ==")
doc = tomlkit.parse('[[rows]]\nname = "a"\nat = 2026-11-16T23:39:55\n')
payload = _coerce_payload(Root, {"rows": [{"name": "a", "at": "2026-11-16T23:39:55"}, {"name": "b", "at": ""}]})
errors: list = []
_validate_payload(Root, payload, "", errors)
print("coerced:", payload, "| errors:", errors)
diff = _diff_document(doc.unwrap(), payload, Root)
try:
    _merge_into_document(doc, diff)
    print("dumps:", repr(tomlkit.dumps(doc)))
    print("read back:", doc.unwrap())
    print("OK: no ConvertError, at key absent in new row ->", "at" not in doc.unwrap()["rows"][1])
except Exception as exc:
    print("!! STILL RAISES:", type(exc).__name__, exc)

print()
print("== A2: 表数组文件里还不存在时的第一行 ==")
doc2 = tomlkit.parse("other = 1\n")
p2 = _coerce_payload(Root, {"rows": [{"name": "b", "at": ""}]})
d2 = _diff_document(doc2.unwrap(), {**doc2.unwrap(), **p2}, Root)
try:
    _merge_into_document(doc2, d2)
    print("dumps:", repr(tomlkit.dumps(doc2)))
    print("read back:", doc2.unwrap())
except Exception as exc:
    print("!! RAISES:", type(exc).__name__, exc)

print()
print("== B: 插件 ISO 往返 ==")
print("_jsonable(datetime) ->", plugin_jsonable(datetime(2026, 11, 16, 23, 39, 55)))
print("_jsonable(date)     ->", plugin_jsonable(date(2026, 11, 16)))
print("_jsonable(time)     ->", plugin_jsonable(time(23, 39, 55)))
print("_jsonable(for_toml) ->", repr(plugin_jsonable(datetime(2026, 11, 16, 23, 39, 55), for_toml=True)))


class M(BaseModel):
    run_at: Optional[datetime] = None


tmp = pathlib.Path(tempfile.mkdtemp()) / "config.toml"
tmp.write_text("run_at = 2026-11-16T23:39:55\n", encoding="utf-8")
ed = PluginConfigEditor(tmp, defaults={"run_at": None}, model=M)
print("read config value   :", repr(ed.read()["config"]["run_at"]))
print("schema value        :", repr(ed.read()["schema"][0]["value"]))

# 前端提交的是 ISO 字符串，API 先 model_validate 再 normalize
submitted = normalize_config_values({"run_at": "2026-11-16T23:39:55"}, M.model_validate({"run_at": "2026-11-16T23:39:55"}))
ed.save(config=submitted)
text = tmp.read_text(encoding="utf-8")
print("file after save     :", repr(text))
print("native datetime?    :", isinstance(tomlkit.parse(text)["run_at"], datetime))
print("read after save     :", repr(ed.read()["config"]["run_at"]))

print()
print("== B2: 原样保存别的字段后，时间列是否还保持原生 ==")
ed.save(config={"run_at": "2026-11-16T23:39:55"})   # 未经 normalize 的纯字符串（手动/旧客户端）
print("file (string input):", repr(tmp.read_text(encoding="utf-8")))

print()
print("== E: _without_none 对无类型 list 的影响 ==")
@dataclass
class Loose:
    items: list = field(default_factory=list)

doc3 = tomlkit.parse("other = 1\n")
p3 = _coerce_payload(Loose, {"items": ["a", None, "b"]})
e3: list = []
_validate_payload(Loose, p3, "", e3)
print("payload:", p3, "| validation errors:", e3)
_merge_into_document(doc3, _diff_document(doc3.unwrap(), p3, Loose))
print("after merge:", doc3.unwrap())

@dataclass
class Typed:
    tags: List[str] = field(default_factory=list)

p4 = _coerce_payload(Typed, {"tags": ["a", None]})
e4: list = []
_validate_payload(Typed, p4, "", e4)
print("typed list validation errors:", e4)
