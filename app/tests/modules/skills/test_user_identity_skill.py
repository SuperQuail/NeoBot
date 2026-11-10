"""user_identity skill: agent 主动映射官方 ID → QQ 号。"""

from __future__ import annotations

import json

import pytest

from neobot_app.skills.user_identity import UserIdentitySkill
from neobot_app.user_identity import bind_user_identity, qq_for_user

SYNTHETIC = 9000000000001
REAL_QQ = 123456789


@pytest.fixture(autouse=True)
def _bind(tmp_path):
    bind_user_identity(tmp_path)
    yield
    bind_user_identity(None)


def _parse(raw: str) -> dict:
    return json.loads(raw)


@pytest.mark.asyncio
async def test_skill_links_and_reads_mapping():
    skill = UserIdentitySkill()

    linked = _parse(
        await skill.execute(
            "link_user_qq", {"user_id": str(SYNTHETIC), "qq_number": str(REAL_QQ)}
        )
    )
    assert linked["ok"] is True
    assert qq_for_user(SYNTHETIC) == REAL_QQ

    read = _parse(await skill.execute("get_user_qq", {"user_id": str(SYNTHETIC)}))
    assert read["ok"] is True and read["qq_number"] == REAL_QQ


@pytest.mark.asyncio
async def test_skill_rejects_invalid_qq():
    skill = UserIdentitySkill()

    result = _parse(
        await skill.execute(
            "link_user_qq", {"user_id": str(SYNTHETIC), "qq_number": "abc"}
        )
    )

    assert result["ok"] is False
    assert qq_for_user(SYNTHETIC) is None


@pytest.mark.asyncio
async def test_skill_unlink():
    skill = UserIdentitySkill()
    await skill.execute(
        "link_user_qq", {"user_id": str(SYNTHETIC), "qq_number": str(REAL_QQ)}
    )

    result = _parse(await skill.execute("unlink_user_qq", {"user_id": str(SYNTHETIC)}))

    assert result["ok"] is True
    assert qq_for_user(SYNTHETIC) is None
