"""积分读写：快照、增减、排行榜与对外能力自描述。"""

from __future__ import annotations

from typing import Any

from .constants import POINTS_API_NAME, POINTS_API_VERSION, POINTS_RANK_MAX_PAGE_SIZE
from .registration import plugin


class _PluginPointsMixin:
    async def points_snapshot(self, user_id: Any) -> dict[str, Any]:
        """某个用户的积分档案（能力 points.get 的实现）。

        score / best_score / plays / wins 来自统一积分账户 mg_profile；
        streak 与 checked_in_today 来自今天的 mg_checkin（未签到则为 0 / False）。
        """
        service = self.require_service()
        uid = str(user_id)
        profile = await service.get_profile(uid)
        today = await service.get_checkin(uid)
        return {
            "ok": True,
            "user_id": uid,
            "score": int(profile.get("score") or 0),
            "best_score": int(profile.get("best_score") or 0),
            "plays": int(profile.get("plays") or 0),
            "wins": int(profile.get("wins") or 0),
            "streak": int(today["streak"]) if today is not None else 0,
            "checked_in_today": today is not None,
            "updated_at": str(profile.get("updated_at") or ""),
        }

    async def adjust_points(
        self,
        *,
        user_id: Any,
        delta: Any,
        source: str = "",
        note: str = "",
        allow_negative: bool = False,
        play: bool = False,
        win: bool = False,
    ) -> dict[str, Any]:
        """其它插件增减积分（能力 points.add 的实现）。

        契约（可预期的业务结果一律用返回值表达，不抛异常）：

        - 成功：ok=True、applied=delta、score=新余额；
        - 余额不足（扣分且 allow_negative=False）：ok=False、reason=insufficient、
          applied=0，**整笔不生效**（不做部分扣减）；
        - 被配置关掉（points_allow_external_write=false）：ok=False、reason=disabled；
        - 参数非法（缺 user_id / delta 非整数 / 超过 points_max_delta）：抛 ValueError。
        """
        service = self.require_service()
        uid = str(user_id)
        amount = int(delta)
        limit = int(getattr(self.config, "points_max_delta", 100_000) or 100_000)
        if abs(amount) > limit:
            raise ValueError(f"单次增减幅度超过上限 {limit}（收到 {amount}）")
        label = str(source or "").strip() or "未署名"
        remark = str(note or "").strip()
        if not bool(getattr(self.config, "points_allow_external_write", True)):
            self._log_points(
                f"小游戏积分变更被拒: user={uid} delta={amount:+d} source={label} "
                f"note={remark or '-'} 原因=points_allow_external_write 已关闭",
                warning=True,
            )
            return {
                "ok": False,
                "reason": "disabled",
                "user_id": uid,
                "delta": amount,
                "applied": 0,
                "score": await service.points(uid),
            }
        outcome = await service.apply_points(
            uid,
            amount,
            allow_negative=bool(allow_negative),
            play=bool(play),
            win=bool(win),
        )
        profile = outcome["profile"]
        applied = int(outcome["applied"])
        insufficient = bool(outcome["insufficient"])
        self._log_points(
            f"小游戏积分变更: user={uid} delta={amount:+d} applied={applied} "
            f"score={int(profile.get('score') or 0)} source={label} "
            f"note={remark or '-'}"
            + ("（余额不足，整笔未生效）" if insufficient else ""),
            warning=insufficient,
        )
        return {
            "ok": not insufficient,
            "reason": "insufficient" if insufficient else "",
            "user_id": uid,
            "delta": amount,
            "applied": applied,
            "score": int(profile.get("score") or 0),
            "best_score": int(profile.get("best_score") or 0),
            "plays": int(profile.get("plays") or 0),
            "wins": int(profile.get("wins") or 0),
            "source": label,
        }

    async def points_rank(
        self, *, page: Any = 1, page_size: Any = 10, conversation_id: str = ""
    ) -> dict[str, Any]:
        """积分排行榜（能力 points.rank 的实现）：给了 conversation_id 就查本群榜。"""
        service = self.require_service()
        size = int(page_size)
        if size < 1 or size > POINTS_RANK_MAX_PAGE_SIZE:
            raise ValueError(
                f"page_size 必须在 1-{POINTS_RANK_MAX_PAGE_SIZE} 之间（收到 {size}）"
            )
        conv = str(conversation_id or "").strip()
        if conv:
            rows = await service.group_leaderboard(conv, limit=size)
            return {
                "ok": True,
                "scope": "group",
                "conversation_id": conv,
                "total": len(rows),
                "rows": rows,
            }
        index = int(page)
        if index < 1:
            raise ValueError(f"page 必须 >= 1（收到 {index}）")
        data = await service.leaderboard(page=index, page_size=size)
        return {
            "ok": True,
            "scope": "global",
            "page": int(data["page"]),
            "page_size": int(data["page_size"]),
            "total": int(data["total"]),
            "rows": list(data.get("rows") or []),
        }

    def describe_points_api(self) -> dict[str, Any]:
        """积分对外接口的自描述（能力 points.describe 的实现）。"""
        return {
            "ok": True,
            "api": POINTS_API_NAME,
            "version": POINTS_API_VERSION,
            "plugin": plugin.name,
            "unit": "积分",
            "capabilities": sorted(plugin.capabilities),
            "allow_external_write": bool(
                getattr(self.config, "points_allow_external_write", True)
            ),
            "max_delta": int(getattr(self.config, "points_max_delta", 100_000) or 100_000),
            "allow_negative_default": False,
            "reject_when_insufficient": True,
        }

    def _log_points(self, text: str, *, warning: bool = False) -> None:
        """积分变更留痕（调用方是别的插件，出问题要能查；日志失败不影响接口）。"""
        logger = self._logger
        if logger is None:
            return
        try:
            (logger.warning if warning else logger.info)(text)
        except Exception:  # pragma: no cover - 日志失败不影响接口
            pass
