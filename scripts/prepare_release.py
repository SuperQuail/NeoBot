"""Detect a manually updated workspace version without modifying project files."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from http.client import HTTPException
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

from packaging.version import InvalidVersion, Version

if __package__:
    from .semver_validation import validate_semver
else:
    from semver_validation import validate_semver


class ReleaseError(ValueError):
    """Release preparation is unsafe; leave the project unchanged."""


def parse_version(value: str, source: str) -> Version:
    if not isinstance(value, str) or value != value.strip() or "\n" in value or "\r" in value:
        raise ReleaseError(f"Invalid version in {source}: {value!r}")
    try:
        version = Version(value)
    except (InvalidVersion, TypeError) as exc:
        raise ReleaseError(f"Invalid version in {source}: {value!r}") from exc
    if version.dev is not None or version.post is not None or version.local is not None:
        raise ReleaseError(f"Unsupported dev/post/local version in {source}: {value}")
    return version


@dataclass(frozen=True)
class Project:
    path: Path
    name: str
    version: Version
    raw_version: str
    publishable: bool


def load_projects(root: Path) -> list[Project]:
    paths = [root / "pyproject.toml", *sorted(root.glob("packages/*/pyproject.toml"))]
    app = root / "app" / "pyproject.toml"
    if app.exists():
        paths.append(app)
    projects = []
    for path in paths:
        try:
            text = path.read_bytes().decode("utf-8")
            data = tomllib.loads(text)
            name = data["project"]["name"]
            raw_version = data["project"]["version"]
            if not isinstance(name, str) or not name.strip() or not isinstance(raw_version, str):
                raise ReleaseError(f"Missing static project name/version in {path}")
            if "version" in data["project"].get("dynamic", []):
                raise ReleaseError(f"Dynamic project.version is not supported: {path}")
            try:
                validate_semver(raw_version, str(path))
            except ValueError as exc:
                raise ReleaseError(str(exc)) from exc
            try:
                version = parse_version(raw_version, str(path))
            except ReleaseError as exc:
                raise ReleaseError(f"Valid SemVer but not supported for PyPI in {path}: {raw_version!r}") from exc
        except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
            raise ReleaseError(f"Cannot load {path}: {exc}") from exc
        projects.append(Project(path, name, version, raw_version, "build-system" in data))
    if any(project.version != projects[0].version for project in projects):
        raise ReleaseError("Local project versions are not synchronized")
    return projects


def published_versions(name: str) -> list[Version]:
    url = f"https://pypi.org/pypi/{quote(name, safe='')}/json"
    try:
        with urlopen(url, timeout=30) as response:
            status = response.status
            if status == 404:
                return []
            if status != 200:
                raise ReleaseError(f"Unexpected HTTP status {status} from {url}")
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            return []
        raise ReleaseError(f"PyPI HTTP failure for {name}: {exc.code}") from exc
    except (URLError, OSError, HTTPException, ValueError) as exc:
        raise ReleaseError(f"Cannot query PyPI for {name}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("releases"), dict):
        raise ReleaseError(f"Invalid PyPI releases JSON for {name}")
    versions = []
    for value, files in payload["releases"].items():
        if not isinstance(files, list):
            raise ReleaseError(f"Invalid PyPI release entry for {name}: {value}")
        # Include prereleases, yanked releases and empty release lists: never reuse a version.
        versions.append(parse_version(value, f"PyPI {name}"))
    return versions


@dataclass(frozen=True)
class ReleasePlan:
    version: str
    publish: bool
    reason: str


def previous_version(root: Path, base_ref: str) -> Version:
    # Require an explicit baseline; never guess HEAD^ for a multi-commit push.
    if not base_ref or base_ref.startswith("-") or set(base_ref) == {"0"}:
        raise ReleaseError("A valid pre-push base ref is required")
    try:
        result = subprocess.run(
            ["git", "show", f"{base_ref}:pyproject.toml"],
            cwd=root, check=True, capture_output=True, text=True, encoding="utf-8",
        )
        data = tomllib.loads(result.stdout)
        if "version" in data["project"].get("dynamic", []):
            raise ReleaseError("Dynamic baseline project.version is not supported")
        return parse_version(data["project"]["version"], f"{base_ref}:pyproject.toml")
    except (OSError, subprocess.CalledProcessError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        raise ReleaseError(f"Cannot read baseline {base_ref}: {exc}") from exc


def prepare_release(root: Path, *, base_ref: str) -> ReleasePlan:
    root = Path(root)
    projects = load_projects(root)
    local = projects[0].version
    version = projects[0].raw_version
    previous = previous_version(root, base_ref)
    if local == previous:
        return ReleasePlan(version, False, "Version unchanged")
    if local < previous:
        raise ReleaseError(f"Version must increase manually: {previous} -> {version}")
    publishable = [project for project in projects if project.publishable]
    if not publishable:
        raise ReleaseError("No publishable workspace packages")
    histories = [(project, published_versions(project.name)) for project in publishable]
    for project, published in histories:
        if published and local < max(published):
            raise ReleaseError(f"{project.name}: {version} is older than PyPI {max(published)}; update versions manually")
    if all(local in published for _, published in histories):
        return ReleasePlan(version, False, "Version already published for all packages")
    return ReleasePlan(version, True, "Manual version update detected")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--base-ref", help="Git ref before the push (github.event.before)")
    mode.add_argument("--check-only", action="store_true", help="Validate local versions without Git or PyPI access")
    args = parser.parse_args(argv)
    try:
        if args.check_only:
            projects = load_projects(args.repo_root)
            print(f"{projects[0].raw_version}: Workspace versions validated")
            return 0
        plan = prepare_release(args.repo_root, base_ref=args.base_ref)
        if output := os.environ.get("GITHUB_OUTPUT"):
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(f"version={plan.version}\npublish={str(plan.publish).lower()}\n")
        print(f"{plan.version}: {plan.reason}")
    except (ReleaseError, OSError) as exc:
        print(f"prepare_release: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
