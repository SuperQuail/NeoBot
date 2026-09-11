"""Strict SemVer 2.0.0 syntax validation (https://semver.org/lang/zh-CN/).

This is not PEP 440 validation: build metadata and arbitrary prerelease labels
are valid SemVer even when they cannot be uploaded to PyPI.
"""
from __future__ import annotations

import re


_NUMERIC = r"(?:0|[1-9][0-9]*)"
_PRERELEASE = rf"(?:{_NUMERIC}|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_SEMVER = re.compile(
    rf"{_NUMERIC}\.{_NUMERIC}\.{_NUMERIC}"
    rf"(?:-{_PRERELEASE}(?:\.{_PRERELEASE})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def validate_semver(value: str, source: str = "version") -> str:
    """Return the original spelling, or reject invalid SemVer without coercion."""
    if not isinstance(value, str) or _SEMVER.fullmatch(value) is None:
        raise ValueError(
            f"Invalid SemVer 2.0.0 in {source}: {value!r}; "
            "expected X.Y.Z[-prerelease][+build] without leading zeros in numeric version/prerelease identifiers"
        )
    return value
