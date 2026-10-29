"""End-to-end CLI tests.

These run the real argument parser and the real command functions with the
network stubbed out. The refactor that extracted asolens.util broke `crawl`
with an AttributeError and 78 unit tests stayed green, because nothing
exercised cli.py — hence this file.
"""

import contextlib
import io
import os
import plistlib
import shutil
import tempfile
import unittest
from unittest import mock

from asolens import cli, ios_store, net
from tests.support import make_app, make_review


def run(argv):
    """Invoke the CLI, returning (exit_code, stdout)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(argv)
    return code, out.getvalue()


class ParserTests(unittest.TestCase):
    def test_a_command_is_required(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args([])

    def test_review_pages_is_clamped_to_the_feed_limit(self):
        args = cli.build_parser().parse_args(["analyze", "id1", "--review-pages", "99"])
        self.assertEqual(args.review_pages, 99)  # clamped later, in cmd_analyze

    def test_compare_with_no_values_means_auto(self):
        args = cli.build_parser().parse_args(["analyze", "id1", "--compare"])
        self.assertEqual(args.compare, [])

    def test_compare_omitted_means_no_comparison(self):
        args = cli.build_parser().parse_args(["analyze", "id1"])
        self.assertIsNone(args.compare)

    def test_version_flag_reports_the_package_version(self):
        from asolens import __version__
        with self.assertRaises(SystemExit) as caught:
            run(["--version"])
        self.assertEqual(caught.exception.code, 0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with contextlib.suppress(SystemExit):
                cli.main(["--version"])
        self.assertIn(__version__, out.getvalue())


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.out_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.out_dir, ignore_errors=True)

    def analyze(self, extra=(), app=None, deeplink_findings=()):
        profile = app or make_app()
        with mock.patch.object(ios_store, "fetch_app", return_value=profile), \
             mock.patch("asolens.deeplinks.check", return_value=list(deeplink_findings)):
            return run(["analyze", "id123456789", "--out", self.out_dir,
                        "--no-assets", "--no-color", *extra])

    def test_clean_app_exits_zero_and_writes_a_report(self):
        code, output = self.analyze()
        self.assertEqual(code, 0)
        self.assertIn("ASO puanı: 100/100", output)
        self.assertTrue(os.path.exists(os.path.join(self.out_dir, "report.html")))

    def test_critical_finding_sets_a_nonzero_exit_code(self):
        code, _ = self.analyze(app=make_app(subtitle=None))
        self.assertEqual(code, 1)

    def test_json_flag_writes_a_machine_readable_report(self):
        import json
        code, _ = self.analyze(extra=["--json"])
        self.assertEqual(code, 0)
        with open(os.path.join(self.out_dir, "report.json"), encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(payload["score"], 100)
        self.assertNotIn("reviews", payload["app"])
        self.assertTrue(payload["findings"])

    def test_reviews_produce_a_handoff_brief(self):
        app = make_app(reviews=[
            make_review(rating=1, title="crashes on launch"),
            make_review(rating=5, title="love it"),
        ])
        code, output = self.analyze(app=app)
        self.assertEqual(code, 0)
        self.assertIn("Yorum temaları", output)
        brief = os.path.join(self.out_dir, "reviews-brief.md")
        self.assertTrue(os.path.exists(brief))
        with open(brief, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("crashes on launch", text)
        self.assertNotIn("love it", text)  # positives stay out of the brief

    def test_unparseable_target_exits_two(self):
        code, output = run(["analyze", "merhaba"])
        self.assertEqual(code, 2)
        self.assertIn("Hata", output)

    def test_lookup_failure_exits_one(self):
        with mock.patch.object(ios_store, "fetch_app",
                               side_effect=net.FetchError("not found")):
            code, output = run(["analyze", "id123456789", "--out", self.out_dir])
        self.assertEqual(code, 1)
        self.assertIn("not found", output)


class CacheCommandTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        patcher = mock.patch.object(net, "CACHE_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        with open(os.path.join(self.dir, "entry"), "wb") as fh:
            fh.write(b"x" * 2048)

    def test_reports_size_and_location(self):
        code, output = run(["cache"])
        self.assertEqual(code, 0)
        self.assertIn("2 KB", output)
        self.assertIn(self.dir, output)

    def test_clear_empties_it(self):
        code, output = run(["cache", "--clear"])
        self.assertEqual(code, 0)
        self.assertIn("1 girdi silindi", output)
        self.assertEqual(os.listdir(self.dir), [])


class CrawlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.app_path = os.path.join(self.tmp, "Sample.app")
        os.makedirs(os.path.join(self.app_path, "en.lproj"))

    def write_plist(self, extra=None):
        plist = {
            "CFBundleIdentifier": "com.example.sample",
            "CFBundleName": "Sample",
            "CFBundleShortVersionString": "1.0",
            "CFBundleVersion": "1",
            "MinimumOSVersion": "15.0",
            "UILaunchScreen": {},
            "ITSAppUsesNonExemptEncryption": False,
        }
        plist.update(extra or {})
        with open(os.path.join(self.app_path, "Info.plist"), "wb") as fh:
            plistlib.dump(plist, fh)

    def test_a_tidy_bundle_exits_zero(self):
        self.write_plist()
        open(os.path.join(self.app_path, "PrivacyInfo.xcprivacy"), "w").close()
        code, output = run(["crawl", self.app_path, "--out", self.tmp])
        self.assertEqual(code, 0)
        self.assertIn("com.example.sample", output)

    def test_blanket_ats_exception_is_reported_and_fails(self):
        self.write_plist({"NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True}})
        code, output = run(["crawl", self.app_path, "--out", self.tmp])
        self.assertEqual(code, 1)
        self.assertIn("NSAllowsArbitraryLoads", output)

    def test_placeholder_usage_string_is_reported(self):
        self.write_plist({"NSCameraUsageDescription": "TODO"})
        code, output = run(["crawl", self.app_path, "--out", self.tmp])
        self.assertEqual(code, 1)
        self.assertIn("izin açıklaması", output)

    def test_missing_bundle_exits_two(self):
        code, output = run(["crawl", os.path.join(self.tmp, "Nope.app")])
        self.assertEqual(code, 2)
        self.assertIn("Info.plist", output)


if __name__ == "__main__":
    unittest.main()


class UnreadablePageTests(unittest.TestCase):
    """A page that could not be read must not become a finding about the app."""

    def setUp(self):
        self.out_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.out_dir, ignore_errors=True)

    def analyze(self, app):
        with mock.patch.object(ios_store, "fetch_app", return_value=app), \
             mock.patch("asolens.deeplinks.check", return_value=[]):
            return run(["analyze", "id123456789", "--out", self.out_dir,
                        "--no-assets", "--no-color"])

    def test_missing_subtitle_is_not_critical_when_the_page_failed(self):
        app = make_app(subtitle=None, page_data_ok=False)
        code, output = self.analyze(app)
        self.assertIn("Subtitle okunamadı", output)
        self.assertNotIn("Subtitle boş", output)
        self.assertEqual(code, 0)

    def test_missing_subtitle_is_critical_when_the_page_was_read(self):
        app = make_app(subtitle=None, page_data_ok=True)
        code, output = self.analyze(app)
        self.assertIn("Subtitle boş", output)
        self.assertEqual(code, 1)

    def test_a_truncated_review_sample_is_announced(self):
        app = make_app(
            reviews=[make_review(rating=1, title="crashes")],
            review_errors=[{"country": "tr", "page": 4, "error": "HTTP 503"}])
        _, output = self.analyze(app)
        self.assertIn("örneklem eksik", output)
        self.assertIn("TR", output)

    def test_auto_compare_says_why_it_found_nothing(self):
        app = make_app(similar_apps=[], page_data_ok=False)
        with mock.patch.object(ios_store, "fetch_app", return_value=app), \
             mock.patch("asolens.deeplinks.check", return_value=[]):
            _, output = run(["analyze", "id123456789", "--out", self.out_dir,
                             "--no-assets", "--no-color", "--compare"])
        self.assertIn("ürün sayfası okunamadı", output)
