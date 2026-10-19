"""Offline regression tests for profile images and public badge generation."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

from scripts import update_profile_badges as badges
from scripts.validate_profile import RAW_PREFIX, SVG_TAG, validate_assets


class BadgeTests(unittest.TestCase):
    def test_svg_is_accessible_and_escapes_labels(self):
        svg = ElementTree.fromstring(badges.badge_svg("Stars & followers", 1234))
        self.assertEqual(svg.tag, SVG_TAG)
        self.assertEqual(svg.attrib["aria-label"], "Stars & followers: 1,234")
        self.assertIn("1,234", " ".join(svg.itertext()))

    def test_invalid_counts_are_not_published(self):
        for value in (-1, "invalid", None, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                badges.badge_svg("Followers", value)

    @patch.object(badges, "github_json")
    def test_counts_only_public_owned_repositories(self, request):
        def repository(stars, private=False, owner=badges.OWNER):
            return {
                "private": private,
                "owner": {"login": owner},
                "stargazers_count": stars,
            }
        request.side_effect = [
            {"followers": 15, "public_repos": 41},
            [repository(5)] * 100,
            [repository(3), repository(900, private=True), repository(100, owner="other")],
        ]
        self.assertEqual(badges.public_counts(), (15, 503, 41))
        self.assertIn("page=2", request.call_args.args[0])

    def test_failed_refresh_preserves_existing_badges(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / "followers.svg"
            target.write_text("last-known-good", encoding="utf-8")
            with patch.object(badges, "PROFILE", Path(directory)), patch.object(
                badges, "public_counts", side_effect=OSError("API unavailable")
            ), self.assertRaises(OSError):
                badges.main()
            self.assertEqual(target.read_text(), "last-known-good")


class AssetTests(unittest.TestCase):
    def check_assets(self, markup, svg=None):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            readme = root / "README.md"
            readme.write_text(markup, encoding="utf-8")
            if svg is not None:
                (root / "card.svg").write_text(svg, encoding="utf-8")
            return validate_assets(readme)

    def test_raw_github_url_is_checked_locally(self):
        errors = self.check_assets(
            f'<img src="{RAW_PREFIX}card.svg?v=2" alt="Stats"/>',
            '<svg xmlns="http://www.w3.org/2000/svg"><text>Stars: 683</text></svg>',
        )
        self.assertEqual(errors, [])

    def test_missing_image_is_rejected(self):
        self.assertTrue(self.check_assets('<img src="./card.svg" alt="Stats"/>'))

    def test_picture_source_is_checked(self):
        errors = self.check_assets(f'<picture><source srcset="{RAW_PREFIX}missing.svg"/></picture>')
        self.assertTrue(errors)

    def test_error_card_and_html_are_rejected(self):
        for body in (
            '<svg xmlns="http://www.w3.org/2000/svg"><text>Something went wrong</text></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg"><title>Followers: invalid</title></svg>',
            '<html><body>502 Bad Gateway</body></html>',
            'not XML',
        ):
            with self.subTest(body=body):
                self.assertTrue(self.check_assets('<img src="card.svg" alt="Stats"/>', body))

    def test_missing_alt_is_rejected(self):
        self.assertTrue(self.check_assets('<img src="https://example.com/card.svg"/>'))

    def test_path_traversal_is_rejected(self):
        self.assertTrue(self.check_assets('<img src="../card.svg" alt="Stats"/>'))


if __name__ == "__main__":
    unittest.main()
