"""Offline checks of source monitoring, retained freshness and manual review."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import watch_sources as watch

ROOT = Path(__file__).resolve().parents[1]
RESOURCE = {"id": "menu", "url": "https://example.com/menu", "kind": "html",
            "required_text": ["Clams & Chips"],
            "sections": [{"start": "Clams & Chips", "end": "Next dish"}]}
PAGE = b"<html><head><title>A menu</title></head><body>Clams &amp; Chips $20 Next dish</body></html>"
OLD = "2026-11-25T12:00:00Z"
NEW = "2026-12-02T12:00:00Z"


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = {"schema_version": 1, "timeout_seconds": 10,
                       "maximum_download_bytes": 1024,
                       "sources": [{"id": "example", "name": "Example", "resources": [copy.deepcopy(RESOURCE)]}]}
        self.write_config()

    def write_config(self):
        watch.atomic_json(self.root / "config/sources.json", self.config)

    def run_watch(self, **kwargs):
        return watch.watch(self.root, fetcher=lambda *_: PAGE, now=OLD, **kwargs)

    def baseline(self):
        return (self.root / "config/source-fingerprints.json").read_bytes()

    def test_manual_acceptance_requires_review_date(self):
        with self.assertRaisesRegex(ValueError, "requires"):
            self.run_watch(accept_reviewed=True)
        with self.assertRaisesRegex(ValueError, "no later"):
            self.run_watch(accept_reviewed=True, reviewed_at="2026-12-01")

    def test_new_source_is_not_silently_accepted(self):
        status, code = self.run_watch()
        self.assertEqual((status["status"], code), ("needs_review", 0))
        self.assertIsNone(status["reviewed_at"])
        self.assertFalse((self.root / "config/source-fingerprints.json").exists())

    def test_changed_price_publishes_review_flag_without_changing_baseline(self):
        self.run_watch(accept_reviewed=True, reviewed_at="2026-11-25")
        original = self.baseline()
        status, code = watch.watch(self.root, fetcher=lambda *_: PAGE.replace(b"$20", b"$21"), now=NEW)
        self.assertEqual((status["status"], code), ("needs_review", 0))
        self.assertEqual(status["checked_at"], NEW)
        self.assertEqual(status["reviewed_at"], "2026-11-25")
        self.assertEqual(self.baseline(), original)

    def test_failed_check_retains_last_success_and_baseline(self):
        self.run_watch(accept_reviewed=True, reviewed_at="2026-11-25")
        original = self.baseline()
        def offline(*_):
            raise OSError("HTTP 403")
        status, code = watch.watch(self.root, fetcher=offline, now=NEW,
                                  accept_reviewed=True, reviewed_at="2026-12-02")
        self.assertEqual((status["status"], code), ("error", 1))
        self.assertEqual(status["checked_at"], OLD)
        self.assertEqual(status["attempted_at"], NEW)
        self.assertEqual(status["reviewed_at"], "2026-11-25")
        self.assertEqual(status["sources"][0]["resources"][0]["checked_at"], OLD)
        self.assertIn("403", status["sources"][0]["resources"][0]["error"])
        self.assertEqual(self.baseline(), original)
        self.assertEqual(watch.read_json(self.root / "web/data/status.json"), status)

    def test_one_failed_resource_does_not_freshen_entire_shop(self):
        self.config["sources"][0]["resources"].append({**RESOURCE, "id": "hours"})
        self.write_config()
        self.run_watch(accept_reviewed=True, reviewed_at="2026-11-25")
        def partial(resource, _config):
            if resource["id"] == "hours":
                raise TimeoutError("Timeout")
            return PAGE
        status, code = watch.watch(self.root, fetcher=partial, now=NEW)
        self.assertEqual(code, 1)
        self.assertEqual(status["checked_at"], OLD)
        self.assertEqual(status["sources"][0]["resources"][0]["checked_at"], NEW)
        self.assertEqual(status["sources"][0]["resources"][1]["checked_at"], OLD)

    def test_new_shop_beyond_defaults_is_counted_and_unreviewed(self):
        self.run_watch(accept_reviewed=True, reviewed_at="2026-11-25")
        self.config["sources"].append({"id": "new-shop", "name": "New", "resources": [RESOURCE]})
        self.write_config()
        status, code = self.run_watch()
        self.assertEqual(status["source_count"], 2)
        self.assertEqual(status["sources"][1]["status"], "needs_review")
        self.assertIsNone(status["reviewed_at"])

    def test_alternating_failures_never_advance_last_complete_check(self):
        self.config["sources"].append({"id": "other", "name": "Other", "resources": [{**RESOURCE, "url": "https://other.example/menu"}]})
        self.write_config()
        self.run_watch(accept_reviewed=True, reviewed_at="2026-11-25")
        def first(resource, _config):
            if resource["url"] == RESOURCE["url"]:
                raise OSError("First restaurant offline")
            return PAGE
        status, code = watch.watch(self.root, fetcher=first, now=NEW)
        self.assertEqual((code, status["checked_at"]), (1, OLD))
        def second(resource, _config):
            if resource["url"] != RESOURCE["url"]:
                raise OSError("Other restaurant offline")
            return PAGE
        status, code = watch.watch(self.root, fetcher=second, now="2026-12-09T12:00:00Z")
        self.assertEqual((code, status["checked_at"]), (1, OLD))
        self.assertEqual(status["sources"][0]["checked_at"], "2026-12-09T12:00:00Z")
        self.assertEqual(status["sources"][1]["checked_at"], NEW)
        status, code = watch.watch(self.root, fetcher=lambda *_: PAGE, now="2026-12-16T12:00:00Z")
        self.assertEqual((code, status["checked_at"]), (0, "2026-12-16T12:00:00Z"))

    def test_changed_source_definition_needs_review_even_if_content_same(self):
        self.run_watch(accept_reviewed=True, reviewed_at="2026-11-25")
        self.config["sources"][0]["resources"][0]["url"] = "https://example.com/new-menu"
        self.write_config()
        status, _ = self.run_watch()
        self.assertEqual(status["status"], "needs_review")

    def test_scripts_navigation_and_whitespace_do_not_trigger_menu_change(self):
        noisy = PAGE.replace(b"<body>", b"<body>New navigation<script>random daily nonce</script>")
        noisy = noisy.replace(b"$20", b"\n  $20 \n")
        self.assertEqual(watch.fingerprint(RESOURCE, PAGE), watch.fingerprint(RESOURCE, noisy))

    def test_error_pages_and_missing_sections_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            watch.fingerprint(RESOURCE, b"<body>Access denied</body>")
        with self.assertRaisesRegex(ValueError, "boundaries"):
            watch.fingerprint(RESOURCE, PAGE.replace(b"Next dish", b"Changed heading"))
        with self.assertRaisesRegex(ValueError, "PNG"):
            watch.fingerprint({"kind": "png"}, PAGE)
        with self.assertRaisesRegex(ValueError, "JPEG"):
            watch.fingerprint({"kind": "jpeg"}, PAGE)
        with self.assertRaisesRegex(ValueError, "JPEG"):
            watch.fingerprint({"kind": "jpeg"}, b"\xff\xd8truncated")

    def test_image_content_and_relinked_menu_are_monitored(self):
        png = {"kind": "png"}
        self.assertNotEqual(watch.fingerprint(png, b"\x89PNG\r\n\x1a\nold"),
                            watch.fingerprint(png, b"\x89PNG\r\n\x1a\nnew"))
        jpeg = {"kind": "jpeg"}
        self.assertNotEqual(watch.fingerprint(jpeg, b"\xff\xd8old\xff\xd9"),
                            watch.fingerprint(jpeg, b"\xff\xd8new\xff\xd9"))
        resource = {**RESOURCE, "asset_path_contains": "/uploads/"}
        old = PAGE + b'<img src="/uploads/old.png">'
        new = PAGE + b'<img src="/uploads/new.png">'
        self.assertNotEqual(watch.fingerprint(resource, old), watch.fingerprint(resource, new))

    def test_download_limit_is_enforced(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, count): return b"x" * count
        with patch.object(watch, "urlopen", return_value=Response()):
            with self.assertRaisesRegex(ValueError, "oversized"):
                watch.fetch(RESOURCE, self.config)

    def test_repo_config_covers_catalogue_without_fixed_count(self):
        config = watch.validate_config(watch.read_json(ROOT / "config/sources.json"))
        catalogue = watch.read_json(ROOT / "web/data/catalogue.json")
        self.assertEqual({source["id"] for source in config["sources"]},
                         {shop["source_id"] for shop in catalogue["restaurants"]})

    def test_duplicate_config_and_plain_http_are_rejected(self):
        self.config["sources"].append(self.config["sources"][0])
        with self.assertRaisesRegex(ValueError, "unique"):
            watch.validate_config(self.config)
        self.config["sources"].pop()
        self.config["sources"][0]["resources"][0]["url"] = "http://example.com/menu"
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            watch.validate_config(self.config)


if __name__ == "__main__":
    unittest.main()
