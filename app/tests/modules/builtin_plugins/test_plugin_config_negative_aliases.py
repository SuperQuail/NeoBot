"""同一序列扩容时，已存在的负别名不能冻结为旧的绝对位置。"""

from pydantic import AliasPath, BaseModel, Field

from neobot_app.builtin_plugins.dashboard.config_parts.pydantic_fields import describe_pydantic_fields


def test_multiple_negative_aliases_keep_relative_paths_after_sequence_growth():
    class Config(BaseModel):
        last: int = Field(10, validation_alias=AliasPath("payload", -1, "a"))
        previous: int = Field(20, validation_alias=AliasPath("payload", -2, "b"))

    for values in ({"payload": [{"a": 10}]}, {"payload": [{"b": 25}, {"a": 15}]}):
        fields = {field["name"]: field for field in describe_pydantic_fields(Config, values)}
        assert fields["last"]["path"] == ["payload", -1, "a"]
        assert fields["previous"]["path"] == ["payload", -2, "b"]
    assert fields["last"]["value"] == Config.model_validate(values).last == 15
    assert fields["previous"]["value"] == Config.model_validate(values).previous == 25
