#!/usr/bin/env python3
"""Validate that the profile links to a small, public project portfolio."""

from __future__ import annotations

import json
import argparse
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


OWNER = "jzjzzzzzzz"
MAX_REPOSITORIES = 12
REPOSITORY_LINK = re.compile(
    rf"https://github\.com/{re.escape(OWNER)}/([A-Za-z0-9_.-]+)(?=[)#/?\s]|$)"
)
RAW_PREFIX = f"https://raw.githubusercontent.com/{OWNER}/{OWNER}/main/"
SVG_TAG = "{http://www.w3.org/2000/svg}svg"


class ProfileImages(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "img":
            if not attributes.get("alt"):
                self.errors.append("Every profile image must have alt text")
            if not attributes.get("src"):
                self.errors.append("Profile image is missing its src")
            else:
                self.sources.append(attributes["src"])
        elif tag == "source" and attributes.get("srcset"):
            self.sources.append(attributes["srcset"])


def validate_assets(readme: Path) -> list[str]:
    """Check embedded local SVGs, including absolute raw GitHub URLs, offline."""
    images = ProfileImages()
    images.feed(readme.read_text(encoding="utf-8"))
    errors = images.errors.copy()
    checked: set[Path] = set()
    root = readme.resolve().parent
    for source in images.sources:
        if source.startswith(RAW_PREFIX):
            relative = urlparse(source[len(RAW_PREFIX):]).path
        elif not urlparse(source).scheme and not source.startswith("//"):
            relative = urlparse(source).path
        else:
            # The output-branch snake is not a local file on main.
            continue
        asset = (root / unquote(relative)).resolve()
        if not asset.is_relative_to(root):
            errors.append(f"Image path escapes the repository: {source}")
            continue
        if asset in checked:
            continue
        checked.add(asset)
        try:
            svg = ElementTree.parse(asset).getroot()
            if svg.tag != SVG_TAG:
                errors.append(f"{relative}: expected an SVG image")
            text = " ".join(svg.itertext()).lower()
            for marker in (
                "something went wrong", "could not fetch", "bad credentials",
                "api rate limit", "invalid", "service unavailable",
            ):
                if marker in text:
                    errors.append(f"{relative}: generated image contains {marker!r}")
        except (OSError, ElementTree.ParseError) as error:
            errors.append(f"{relative}: missing or invalid SVG: {error}")
    print(f"Checked {len(checked)} self-hosted profile images.")
    return errors


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("readme", nargs="?", type=Path, default=Path("README.md"))
    parser.add_argument("--assets-only", action="store_true", help="Skip GitHub API requests")
    args = parser.parse_args()
    errors = validate_assets(args.readme)
    if not args.assets_only:
        errors.extend(validate(args.readme))
    if errors:
        print("\nProfile validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Profile validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
