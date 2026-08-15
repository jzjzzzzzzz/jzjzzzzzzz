#!/usr/bin/env python3
"""Validate that the profile links to a small, public project portfolio."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OWNER = "jzjzzzzzzz"
MAX_REPOSITORIES = 12
REPOSITORY_LINK = re.compile(
    rf"https://github\.com/{re.escape(OWNER)}/([A-Za-z0-9_.-]+)(?=[)#/?\s]|$)"
)


def repository_names(readme: Path) -> list[str]:
    """Return unique owner/repository links in display order."""
    names: list[str] = []
    for name in REPOSITORY_LINK.findall(readme.read_text(encoding="utf-8")):
        if name not in names:
            names.append(name)
    return names


def repository_metadata(name: str) -> dict[str, object]:
    """Read public repository metadata from the GitHub REST API."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{OWNER}-profile-validator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    request = Request(
        f"https://api.github.com/repos/{OWNER}/{name}", headers=headers
    )
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def validate(readme: Path) -> list[str]:
    names = repository_names(readme)
    errors: list[str] = []

    if not names:
        errors.append("README does not contain any project repository links")
    if len(names) > MAX_REPOSITORIES:
        errors.append(
            f"README links to {len(names)} repositories; limit is {MAX_REPOSITORIES}"
        )

    for name in names:
        try:
            metadata = repository_metadata(name)
        except HTTPError as error:
            errors.append(f"{name}: GitHub API returned HTTP {error.code}")
            continue
        except URLError as error:
            errors.append(f"{name}: GitHub API request failed: {error.reason}")
            continue

        if metadata.get("private") is not False:
            errors.append(f"{name}: repository is not public")
        if metadata.get("archived") is not False:
            errors.append(f"{name}: repository is archived")
        if metadata.get("fork") is not False:
            errors.append(f"{name}: repository is a fork")
        if metadata.get("owner", {}).get("login") != OWNER:
            errors.append(f"{name}: repository is not owned by {OWNER}")

    print(f"Checked {len(names)} curated repository links.")
    return errors


def main() -> int:
    readme = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("README.md")
    errors = validate(readme)
    if errors:
        print("\nProfile validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Profile validation passed: all projects are public, active, and owned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
