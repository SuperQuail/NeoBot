"""提示词注册表/组合器测试的共享 fixture：默认提示词 store、BotConfig 与最小替身。

与 app/tests/modules/config/test_prompt_builder.py 的辅助保持同一套语义
（同步默认提示词到临时目录、自定义文件覆盖默认），但不跨文件 import 测试模块。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.prompt.store import PromptStore, sync_default_prompts


@pytest.fixture(scope="session")
def prompt_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """一次性同步默认提示词到会话级临时目录，供各用例复用（只读）。"""
    root = tmp_path_factory.mktemp("prompt-data")
    sync_default_prompts(root)
    return root


@pytest.fixture()
def prompt_store(prompt_root: Path) -> PromptStore:
    """默认提示词 store（无自定义覆盖）。"""
    return PromptStore(prompt_root)


@pytest.fixture()
def bot_config() -> BotConfig:
    """默认配置（gentle_language_enabled 等开关均为默认值）。"""
    return BotConfig()


@pytest.fixture()
def custom_store(tmp_path: Path):
    """返回工厂：向临时目录写入自定义提示词文本，得到覆盖后的 PromptStore。"""
    sync_default_prompts(tmp_path)

    def _make(text: str) -> PromptStore:
        custom = tmp_path / "prompts" / "custom" / "prompts.toml"
        custom.write_text(text, encoding="utf-8")
        return PromptStore(tmp_path)

    return _make


class FakeProfileService:
    """用户档案服务替身：各渲染方法返回固定文本，不触达真实存储/API。"""

    async def get_group_name(self, group_id):
        return "测试群名"

    async def render_group_member_list(
        self, group_id, message_queue, *, archive_fetch_window=None, include_archives=False
    ):
        return "成员列表：小明、小红"

    async def render_bot_group_admin_status(self, group_id, bot_account, message_queue):
        return "你不是该群管理员"

    async def render_group_owner_text(self, group_id, message_queue):
        return "群主：老王（QQ：10086）"

    async def ensure_user_profile(self, user_id):
        return SimpleNamespace(nick_name="小明", remark="测试备注", profile="小明是个程序员")

    async def render_friend_info(self, user_id, *, profile=None):
        return "好友信息：小明"


class FakeQueue:
    """消息队列替身：没有任何消息（关键词规则不命中）。"""

    def to_text(self, key, last_reply_message_id=None, *, all_new=False):
        return "消息记录：你好"

    def iterate_from_newest(self, key):
        raise KeyError(key)


@pytest.fixture()
def fake_profile() -> FakeProfileService:
    return FakeProfileService()


@pytest.fixture()
def fake_queue() -> FakeQueue:
    return FakeQueue()
