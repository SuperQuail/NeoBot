"""Pure in-memory policy evaluation using server wall time."""

from datetime import timedelta, timezone
from zoneinfo import ZoneInfo
from neobot_contracts.ports.speaking import SpeakingDecision
from .config import intervals


def windows_for(config, conversation):
    return next(
        (o.windows for o in config.overrides if (o.kind, o.id) == (conversation.kind, conversation.id)), config.windows
    )


def evaluate(config, conversation, now):
    windows = windows_for(config, conversation)
    if not windows:
        return SpeakingDecision(True)
    local = now.astimezone(ZoneInfo(config.timezone))
    current = (local.isoweekday() - 1) * 1440 + local.hour * 60 + local.minute
    allowed = any(start <= current < end for start, end in intervals(windows))
    return SpeakingDecision(allowed, "" if allowed else "不在允许发言时段")


def next_boundary(config, conversation, now):
    windows = windows_for(config, conversation)
    if not windows:
        return None
    # Scan real UTC minutes: handles missing/repeated local minutes during DST.
    # Cover two weekly cycles plus offset-change margin: a missing local hour
    # can erase this week's entire window, leaving the next real boundary a
    # week later. Keep a finite bound for schedules with no permission change.
    cursor = now.astimezone(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
    allowed = evaluate(config, conversation, now).allowed
    for _ in range(16 * 1440):
        if evaluate(config, conversation, cursor).allowed != allowed:
            return cursor.astimezone(ZoneInfo(config.timezone))
        cursor += timedelta(minutes=1)
    return None
