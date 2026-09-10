"""Choose one workspace release version; run with uv --no-project --with packaging.

No pyproject is written until every local file and every PyPI response is valid.
Only static project.version string values are changed, not dependency constraints.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sys
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

from packaging.version import InvalidVersion, Version


class ReleaseError(ValueError):
    """Release preparation is unsafe; leave the project unchanged."""


def parse_version(value: str, source: str) -> Version:
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
    text: str
    data: dict
    name: str
    version: Version
    publishable: bool


def load_projects(root: Path) -> list[Project]:
    paths = [root / "pyproject.toml", *sorted(root.glob("packages/*/pyproject.toml"))]
    app = root / "app" / "pyproject.toml"
    if app.exists():
        paths.append(app)
    projects = []
    for path in paths:
        try:
            # Preserve CRLF and all formatting outside the version literal.
            text = path.read_bytes().decode("utf-8")
            data = tomllib.loads(text)
            name = data["project"]["name"]
            raw_version = data["project"]["version"]
            if not isinstance(name, str) or not name.strip() or not isinstance(raw_version, str):
                raise ReleaseError(f"Missing static project name/version in {path}")
            if "version" in data["project"].get("dynamic", []):
                raise ReleaseError(f"Dynamic project.version is not supported: {path}")
            version = parse_version(raw_version, str(path))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
            raise ReleaseError(f"Cannot load {path}: {exc}") from exc
        projects.append(Project(path, text, data, name, version, "build-system" in data))
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


def choose_version(local: Version, published: list[Version]) -> Version:
    if not published or local > max(published):
        return local
    latest = max(local, *published)
    prefix = f"{latest.epoch}!" if latest.epoch else ""
    if latest.pre is not None:
        stage, number = latest.pre
        return Version(prefix + ".".join(map(str, latest.release)) + f"{stage}{number + 1}")
    release = list(latest.release)
    if len(release) > 3:
        raise ReleaseError(f"Cannot increment patch of non-standard release: {latest}")
    release += [0] * (3 - len(release))
    release[2] += 1
    return Version(prefix + ".".join(map(str, release)))


# Candidates are proved by parsing, not by assuming a regex understands TOML tables.
_VERSION_LINE = re.compile(
    r'''(?m)^[ \t]*(?:version|"version"|'version')[ \t]*=[ \t]*(?P<literal>"[^"\r\n]*"|'[^'\r\n]*')[ \t]*(?:\#[^\r\n]*)?\r?$'''
)


def replace_project_version(project: Project, version: str) -> str:
    expected = copy.deepcopy(project.data)
    marker = "__prepare_release_version_marker__"
    expected["project"]["version"] = marker
    candidates = []
    for match in _VERSION_LINE.finditer(project.text):
        start, end = match.span("literal")
        probe = project.text[:start] + json.dumps(marker) + project.text[end:]
        try:
            if tomllib.loads(probe) == expected:
                candidates.append((start, end))
        except tomllib.TOMLDecodeError:
            pass
    if len(candidates) != 1:
        raise ReleaseError(f"Cannot precisely locate static project.version in {project.path}")
    start, end = candidates[0]
    delimiter = project.text[start]
    updated = project.text[:start] + delimiter + version + delimiter + project.text[end:]
    expected["project"]["version"] = version
    if tomllib.loads(updated) != expected:
        raise ReleaseError(f"Unexpected TOML change in {project.path}")
    return updated


def prepare_release(root: Path) -> str:
    projects = load_projects(Path(root))
    published = []
    for project in projects:
        if project.publishable:
            published.extend(published_versions(project.name))
    version = str(choose_version(projects[0].version, published))
    # Stage every edit before the first write (including precise-edit validation).
    updates = [(project.path, replace_project_version(project, version)) for project in projects]
    for path, text in updates:
        path.write_bytes(text.encode("utf-8"))
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        version = prepare_release(args.repo_root)
        if output := os.environ.get("GITHUB_OUTPUT"):
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(f"version={version}\n")
        print(version)
    except (ReleaseError, OSError) as exc:
        print(f"prepare_release: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
