import unittest
from unittest import mock

from asolens import ios_store, net


class ParseUrlTests(unittest.TestCase):
    def test_full_store_url_yields_id_and_country(self):
        self.assertEqual(
            ios_store.parse_url("https://apps.apple.com/tr/app/instagram/id389801252"),
            ("389801252", "tr"),
        )

    def test_url_without_country_segment(self):
        self.assertEqual(
            ios_store.parse_url("https://apps.apple.com/app/id389801252"),
            ("389801252", None),
        )

    def test_query_string_is_ignored(self):
        self.assertEqual(
            ios_store.parse_url("https://apps.apple.com/us/app/foo/id389801252?mt=8"),
            ("389801252", "us"),
        )

    def test_scheme_is_optional(self):
        self.assertEqual(
            ios_store.parse_url("apps.apple.com/gb/app/x/id389801252"),
            ("389801252", "gb"),
        )

    def test_bare_id_and_id_prefix(self):
        self.assertEqual(ios_store.parse_url("389801252"), ("389801252", None))
        self.assertEqual(ios_store.parse_url("id389801252"), ("389801252", None))

    def test_digits_in_the_slug_do_not_win_over_the_id(self):
        self.assertEqual(
            ios_store.parse_url("https://apps.apple.com/tr/app/2024-takvim/id389801252"),
            ("389801252", "tr"),
        )

    def test_bare_number_is_accepted_on_an_apple_host(self):
        self.assertEqual(
            ios_store.parse_url("https://apps.apple.com/us/app/foo/389801252"),
            ("389801252", "us"),
        )

    def test_a_long_number_on_another_host_is_not_an_app_id(self):
        """A date in a blog URL used to be read as an app id."""
        for url in ("https://example.com/20240101",
                    "https://blog.example.com/posts/12345678"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    ios_store.parse_url(url)

    def test_garbage_raises(self):
        for value in ("merhaba", "", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    ios_store.parse_url(value)


class LabelTests(unittest.TestCase):
    def test_label_unwraps_apple_feed_nodes(self):
        self.assertEqual(ios_store._label({"label": "hello"}), "hello")

    def test_label_tolerates_plain_values_and_none(self):
        self.assertEqual(ios_store._label("plain"), "plain")
        self.assertEqual(ios_store._label(None), "")
        self.assertEqual(ios_store._label({}), "")


if __name__ == "__main__":
    unittest.main()


class SubtitleFallbackTests(unittest.TestCase):
    """Apple puts the genre in the subtitle slot when an app has no subtitle."""

    def test_a_subtitle_equal_to_the_category_is_treated_as_absent(self):
        self.assertIsNone(
            ios_store.subtitle_or_none("Lifestyle", ["Lifestyle", "Shopping"]))

    def test_comparison_ignores_case_and_padding(self):
        self.assertIsNone(
            ios_store.subtitle_or_none("  lifestyle ", ["Lifestyle"]))

    def test_a_real_subtitle_is_kept(self):
        self.assertEqual(
            ios_store.subtitle_or_none("Çeyiz defteri ve bütçe", ["Lifestyle"]),
            "Çeyiz defteri ve bütçe")

    def test_a_subtitle_merely_containing_the_category_is_kept(self):
        self.assertEqual(
            ios_store.subtitle_or_none("Lifestyle planner for two", ["Lifestyle"]),
            "Lifestyle planner for two")

    def test_empty_and_missing_inputs(self):
        self.assertIsNone(ios_store.subtitle_or_none(None, ["Lifestyle"]))
        self.assertIsNone(ios_store.subtitle_or_none("", ["Lifestyle"]))
        self.assertEqual(ios_store.subtitle_or_none("Real one", None), "Real one")


class ReviewMarketTests(unittest.TestCase):
    """Reviews are per storefront; reading only one misses the audience."""

    SURVEY = {
        "available_in": ["br", "de", "tr", "us"],
        "ratings": {"us": 29_000_000, "br": 11_000_000, "de": 2_400_000,
                    "tr": 3_600_000},
        "by_variant": {}, "distinct": 4, "probed": [],
    }

    def test_busiest_storefronts_are_chosen(self):
        self.assertEqual(
            ios_store.rank_review_markets(self.SURVEY, limit=3),
            ["us", "br", "tr"])

    def test_the_requested_storefront_is_pinned_first(self):
        """Asking about the TR store must read the TR store, whatever the
        global numbers say."""
        self.assertEqual(
            ios_store.rank_review_markets(self.SURVEY, preferred="de", limit=3),
            ["de", "us", "br"])

    def test_a_storefront_the_app_is_absent_from_is_not_pinned(self):
        self.assertEqual(
            ios_store.rank_review_markets(self.SURVEY, preferred="jp", limit=2),
            ["us", "br"])

    def test_limit_is_respected(self):
        self.assertEqual(len(ios_store.rank_review_markets(self.SURVEY, limit=1)), 1)

    def test_an_empty_survey_yields_nothing_to_rank(self):
        self.assertEqual(ios_store.rank_review_markets(None), [])
        self.assertEqual(ios_store.rank_review_markets({}), [])


class SurveyFailureTests(unittest.TestCase):
    """A survey that reached nothing must not look like a single-market app."""

    def survey(self, outcomes):
        """outcomes: {country: payload | FetchError}"""
        def fake_get_json(url, ttl=3600, ua=None):
            code = url.rsplit("country=", 1)[1]
            value = outcomes.get(code)
            if isinstance(value, Exception):
                raise value
            return {"results": value or []}

        with mock.patch.object(net, "get_json", fake_get_json):
            return ios_store.storefront_survey(
                "1", storefronts=tuple(outcomes), ttl=0)

    def record(self, name="App", desc="Text", ratings=10):
        return [{"trackName": name, "description": desc, "releaseNotes": "",
                 "userRatingCount": ratings}]

    def test_an_absent_app_is_not_a_failure(self):
        result = self.survey({"us": self.record(), "jp": []})
        self.assertEqual(result["available_in"], ["us"])
        self.assertEqual(result["failed"], [])
        self.assertTrue(result["usable"])

    def test_failed_probes_are_recorded_separately(self):
        result = self.survey({
            "us": self.record(), "de": net.FetchError("boom"), "tr": self.record()})
        self.assertEqual(result["failed"], ["de"])
        self.assertEqual(result["available_in"], ["tr", "us"])

    def test_a_survey_that_reached_nothing_is_not_usable(self):
        result = self.survey({c: net.FetchError("boom") for c in ("us", "de", "tr")})
        self.assertFalse(result["usable"])
        self.assertEqual(result["available_in"], [])

    def test_mostly_failed_is_not_usable_either(self):
        result = self.survey({
            "us": self.record(), "de": net.FetchError("x"),
            "tr": net.FetchError("x"), "br": net.FetchError("x")})
        self.assertFalse(result["usable"])

    def test_identical_copy_collapses_into_one_variant(self):
        result = self.survey({"us": self.record(), "gb": self.record()})
        self.assertEqual(result["distinct"], 1)

    def test_different_copy_counts_as_separate_localizations(self):
        result = self.survey({
            "us": self.record(desc="Track your spending"),
            "de": self.record(desc="Behalte deine Ausgaben im Blick")})
        self.assertEqual(result["distinct"], 2)
