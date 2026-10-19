#!/usr/bin/env python3
"""Generate self-hosted badges from GitHub's public REST API (stdlib only)."""

from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen


OWNER = "jzjzzzzzzz"
PROFILE = Path(__file__).resolve().parent.parent / "profile"


def github_json(path: str) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{OWNER}-profile-badges",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com{path}", headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"Expected a non-negative GitHub count, got {value!r}")
    return value


def public_counts() -> tuple[int, int]:
    user = github_json(f"/users/{OWNER}")
    followers = count(user["followers"])
    stars = 0
    page = 1
    while True:
        repositories = github_json(
            f"/users/{OWNER}/repos?type=owner&per_page=100&page={page}"
        )
        if not isinstance(repositories, list):
            raise ValueError("Expected a list of public repositories")
        for repository in repositories:
            # Never publish private counts, even if a token can access them.
            if (
                repository.get("private") is False
                and repository.get("owner", {}).get("login", "").lower() == OWNER
            ):
                stars += count(repository["stargazers_count"])
        if len(repositories) < 100:
            return followers, stars
        page += 1


def badge_svg(label: str, value: int) -> str:
    message = f"{count(value):,}"
    left = len(label) * 7 + 16
    right = len(message) * 7 + 16
    width = left + right
    title = escape(f"{label}: {message}", quote=True)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" viewBox="0 0 {width} 20" role="img" aria-label="{title}">
  <title>{title}</title>
  <clipPath id="badge"><rect width="{width}" height="20" rx="3"/></clipPath>
  <g clip-path="url(#badge)">
    <path fill="#555" d="M0 0h{left}v20H0z"/>
    <path fill="#007ec6" d="M{left} 0h{right}v20H{left}z"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{left / 2}" y="14">{escape(label)}</text>
    <text x="{left + right / 2}" y="14">{message}</text>
  </g>
</svg>
'''


def main() -> None:
    # Finish every request before touching the last-known-good assets.
    followers, stars = public_counts()
    PROFILE.mkdir(exist_ok=True)
    for name, label, value in (
        ("followers", "Followers", followers),
        ("stars", "Total stars", stars),
    ):
        target = PROFILE / f"{name}.svg"
        temporary = target.with_suffix(".svg.tmp")
        temporary.write_text(badge_svg(label, value), encoding="utf-8")
        temporary.replace(target)
    print(f"Updated public badges: {followers} followers, {stars} stars.")


if __name__ == "__main__":
    main()
