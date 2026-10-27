import json
import unittest
from unittest import mock

from asolens import aso, deeplinks, net
from tests.support import find, make_app

AASA = {
    "applinks": {
        "details": [{
            "appIDs": ["ABCDE12345.com.example.centsible"],
            "components": [{"/": "/wallet/*"}, {"/": "/receipt/*"}],
        }]
    }
}

BANNER = '<html><head><meta name="apple-itunes-app" content="app-id=123456789">' \
         '</head><body>hi</body></html>'
NO_BANNER = "<html><head><title>Example</title></head><body>hi</body></html>"


def responder(mapping, default=None):
    """Serve canned bodies by URL; anything unmapped raises like the real net."""
    def fake_get(url, ttl=3600, timeout=25, binary=False, ua=None):
        if url in mapping:
            return mapping[url]
        if default is not None:
            return default
        raise net.FetchError("no route for %s" % url)
    return fake_get


class HostVariantTests(unittest.TestCase):
    def test_apex_gets_the_www_form_and_the_other_way_round(self):
        self.assertEqual(deeplinks.host_variants("example.com"),
                         ["example.com", "www.example.com"])
        self.assertEqual(deeplinks.host_variants("www.example.com"),
                         ["www.example.com", "example.com"])

    def test_html_detection(self):
        self.assertTrue(deeplinks.looks_like_html("<!DOCTYPE html><html>"))
        self.assertTrue(deeplinks.looks_like_html("\n  <html lang='en'>"))
        self.assertFalse(deeplinks.looks_like_html('{"applinks": {}}'))


class AasaTests(unittest.TestCase):
    def check(self, mapping, app=None):
        with mock.patch.object(net, "get", responder(mapping)):
            return deeplinks.check(app or make_app(), ttl=0)

    def test_valid_file_passes_every_check(self):
        findings = self.check({
            "https://example.com/.well-known/apple-app-site-association":
                json.dumps(AASA),
            "https://example.com/": BANNER,
        })
        self.assertEqual(find(findings, "deeplink.aasa").severity, aso.OK)
        self.assertEqual(find(findings, "deeplink.bundle").severity, aso.OK)
        self.assertEqual(find(findings, "deeplink.paths").severity, aso.OK)
        self.assertEqual(find(findings, "deeplink.banner").severity, aso.OK)

    def test_file_found_only_on_the_www_variant(self):
        findings = self.check({
            "https://www.example.com/.well-known/apple-app-site-association":
                json.dumps(AASA),
            "https://example.com/": BANNER,
        })
        self.assertEqual(find(findings, "deeplink.aasa").severity, aso.OK)

    def test_missing_file_is_critical(self):
        findings = self.check({"https://example.com/": BANNER})
        self.assertEqual(find(findings, "deeplink.aasa").severity, aso.CRITICAL)

    def test_a_catch_all_route_serving_html_is_reported(self):
        """The failure mode that bit instagram.com: a web route answers the path."""
        findings = self.check({
            "https://example.com/.well-known/apple-app-site-association":
                "<!DOCTYPE html><html><body>app</body></html>",
            "https://www.example.com/.well-known/apple-app-site-association":
                json.dumps(AASA),
            "https://example.com/": BANNER,
        })
        html_finding = find(findings, "deeplink.aasa_html")
        self.assertEqual(html_finding.severity, aso.WARN)
        self.assertEqual(find(findings, "deeplink.aasa").severity, aso.OK)

    def test_html_everywhere_is_critical(self):
        findings = self.check({
            "https://example.com/.well-known/apple-app-site-association":
                "<!DOCTYPE html><html></html>",
            "https://example.com/": NO_BANNER,
        })
        self.assertEqual(find(findings, "deeplink.aasa_html").severity, aso.CRITICAL)

    def test_malformed_json_is_critical(self):
        findings = self.check({
            "https://example.com/.well-known/apple-app-site-association": "{nope",
            "https://example.com/": BANNER,
        })
        self.assertEqual(find(findings, "deeplink.aasa_json").severity, aso.CRITICAL)

    def test_bundle_id_absent_from_the_file(self):
        other = {"applinks": {"details": [{"appIDs": ["ABCDE.com.other.app"],
                                           "paths": ["*"]}]}}
        findings = self.check({
            "https://example.com/.well-known/apple-app-site-association":
                json.dumps(other),
            "https://example.com/": BANNER,
        })
        self.assertEqual(find(findings, "deeplink.bundle").severity, aso.CRITICAL)

    def test_wildcard_only_paths_are_called_out(self):
        wild = {"applinks": {"details": [{
            "appIDs": ["ABCDE12345.com.example.centsible"], "paths": ["*"]}]}}
        findings = self.check({
            "https://example.com/.well-known/apple-app-site-association":
                json.dumps(wild),
            "https://example.com/": BANNER,
        })
        self.assertEqual(find(findings, "deeplink.paths").severity, aso.INFO)

    def test_legacy_root_path_is_accepted(self):
        findings = self.check({
            "https://example.com/apple-app-site-association": json.dumps(AASA),
            "https://example.com/": BANNER,
        })
        self.assertEqual(find(findings, "deeplink.aasa").severity, aso.OK)

    def test_single_detail_object_instead_of_a_list(self):
        single = {"applinks": {"details": {
            "appID": "ABCDE12345.com.example.centsible", "paths": ["/x/*"]}}}
        findings = self.check({
            "https://example.com/.well-known/apple-app-site-association":
                json.dumps(single),
            "https://example.com/": BANNER,
        })
        self.assertEqual(find(findings, "deeplink.bundle").severity, aso.OK)


class BannerTests(unittest.TestCase):
    def run_check(self, home):
        mapping = {
            "https://example.com/.well-known/apple-app-site-association":
                json.dumps(AASA),
            "https://example.com/": home,
        }
        with mock.patch.object(net, "get", responder(mapping)):
            return deeplinks.check(make_app(), ttl=0)

    def test_missing_banner_is_flagged(self):
        self.assertEqual(find(self.run_check(NO_BANNER), "deeplink.banner").severity,
                         aso.WARN)

    def test_banner_pointing_at_another_app_is_flagged(self):
        wrong = '<meta name="apple-itunes-app" content="app-id=999">'
        self.assertEqual(find(self.run_check(wrong), "deeplink.banner").severity,
                         aso.WARN)


class DomainTests(unittest.TestCase):
    def test_domain_extraction(self):
        self.assertEqual(deeplinks.domain_of("https://example.com/path"), "example.com")
        self.assertEqual(deeplinks.domain_of("example.com"), "example.com")
        self.assertEqual(deeplinks.domain_of("http://Example.com:8080/"), "example.com")
        self.assertIsNone(deeplinks.domain_of(None))

    def test_app_without_a_website_is_skipped_cleanly(self):
        findings = deeplinks.check(make_app(seller_url=None), ttl=0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, aso.INFO)


if __name__ == "__main__":
    unittest.main()
