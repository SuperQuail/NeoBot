"""配置表单与保存接口使用同一条 Pydantic 输入路径。"""

import tomllib

import httpx
import pytest
import tomlkit
from pydantic import AliasChoices, AliasPath, BaseModel, Field

from test_dashboard_api import _login, _start_panel


@pytest.mark.parametrize("kind", ["alias", "validation_alias", "choices", "path", "negative", "same"])
@pytest.mark.parametrize("container", ["nested", "rows"])
async def test_edit_and_save_nested_input_alias(tmp_path, monkeypatch, kind, container):
    declarations = {
        "alias": {"alias": "seconds"},
        "validation_alias": {"validation_alias": "seconds"},
        "choices": {"validation_alias": AliasChoices("seconds", AliasPath("payload", 0, "entry"))},
        "path": {"validation_alias": AliasPath("payload", 0, "entry")},
        "negative": {"validation_alias": AliasPath("payload", -1, "entry")},
        "same": {"alias": "interval"},
    }

    class Nested(BaseModel):
        interval: int = Field(60, **declarations[kind])

    class Config(BaseModel):
        nested: Nested | None = None
        rows: list[Nested] = []

    item = (
        {"payload": [{"entry": 30, "retained": "原有成员"}]}
        if kind in {"path", "choices", "negative"}
        else {"interval" if kind == "same" else "seconds": 30}
    )
    stored = {container: [item] if container == "rows" else item}
    server, control, base, _ = await _start_panel(tmp_path)
    monkeypatch.setattr(control, "config_model", lambda name: Config)
    path = control.plugin_config_path("demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(stored), encoding="utf-8")
    try:
        token, csrf = await _login(base)
        headers = {"X-Token": token, "X-CSRF-Token": csrf}
        async with httpx.AsyncClient(trust_env=False) as client:
            read = await client.get(base + "/api/plugins/demo/config", headers=headers)
            assert read.status_code == 200, read.text
            document = read.json()
            parent = next(field for field in document["schema"] if field["name"] == container)
            children = parent["items"][0]["fields"] if container == "rows" else parent["fields"]
            descriptor = children[0]
            assert descriptor["value"] == 30
            submitted = document["config"]
            node = submitted
            for part in descriptor["path"][:-1]:
                node = node[int(part)] if isinstance(node, list) else node[part]
            node[descriptor["path"][-1]] = 15
            saved = await client.post(
                base + "/api/plugins/demo/config",
                headers=headers,
                json={"config": submitted, "revision": document["revision"]},
            )
            assert saved.status_code == 200, saved.text
            actual = tomllib.loads(path.read_text(encoding="utf-8"))
            assert actual == submitted
            parsed = Config.model_validate(actual)
            current = parsed.rows[0] if container == "rows" else parsed.nested
            assert current.interval == 15
    finally:
        await server.stop()
