"""Atomic plugin-local state and advisory OneBot time health."""

import json
import math
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta


def utc_now():
    return datetime.now(timezone.utc)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".schedule-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class MuteStore:
    def __init__(self, path, *, now=utc_now, monotonic=time.monotonic):
        self.path, self.now, self.monotonic = path, now, monotonic
        self.deadlines = {}
        self.utc = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for account, scopes in data.items():
                for scope, value in scopes.items():
                    deadline = datetime.fromisoformat(value)
                    if deadline.tzinfo is None:
                        raise ValueError("静默截止时间必须带时区")
                    remaining = (deadline - now()).total_seconds()
                    if remaining > 0:
                        self.utc.setdefault(account, {})[scope] = value
                        self.deadlines[(account, scope)] = monotonic() + remaining

    def remaining(self, account, scope):
        return max(0, self.deadlines.get((account, scope), 0) - self.monotonic())

    def set(self, account, scope, seconds):
        if not math.isfinite(seconds) or not 0 < seconds <= 365 * 86400:
            raise ValueError("静默时长必须在0至365天之间")
        data = {a: dict(s) for a, s in self.utc.items()}
        data.setdefault(account, {})[scope] = (self.now() + timedelta(seconds=seconds)).isoformat()
        atomic_write(self.path, json.dumps(data, ensure_ascii=False, indent=2))
        self.utc = data
        self.deadlines[(account, scope)] = self.monotonic() + seconds

    def clear(self, account, scope):
        data = {a: dict(s) for a, s in self.utc.items()}
        data.setdefault(account, {}).pop(scope, None)
        atomic_write(self.path, json.dumps(data, ensure_ascii=False, indent=2))
        self.utc = data
        self.deadlines.pop((account, scope), None)


class ClockHealth:
    def __init__(self, *, monotonic=time.monotonic):
        self.monotonic = monotonic
        self.latest = None
        self.received = None
        self.health = "未收到本账号时间样本"
        self.account = None

    def select_account(self, account):
        if account != self.account:
            self.account = account
            self.latest = self.received = None
            self.health = "未收到本账号时间样本"

    def sample(self, event, account, now):
        self.select_account(account)
        if not account or str(event.get("self_id", "")) != account:
            return False
        stamp = event.get("time")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp):
            self.health = "异常：无效事件时间"
            return False
        if abs(now - stamp) > 120:
            self.health = "异常：样本过旧或与服务器偏差超过120秒"
            return False
        if self.latest is not None and stamp <= self.latest:
            return False
        self.latest, self.received = stamp, self.monotonic()
        self.health = "正常（仅校验，执行使用服务器时间）"
        return True

    def status(self):
        if self.received is not None and self.monotonic() - self.received > 300:
            return "时间样本过期；执行仍使用服务器时间"
        return self.health
