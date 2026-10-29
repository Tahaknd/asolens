import unittest

from asolens import aso
from tests.support import days_ago, find, make_app


class HealthyAppTests(unittest.TestCase):
    def test_a_well_formed_listing_scores_full_marks(self):
        findings = aso.audit(make_app())
        failed = [f for f in findings if f.severity in (aso.CRITICAL, aso.WARN)]
        self.assertEqual(failed, [], "unexpected findings: %s" % [f.check for f in failed])
        self.assertEqual(aso.score(findings), 100)

    def test_score_never_goes_below_zero(self):
        broken = make_app(
            name="x" * 40, subtitle=None, description="", release_notes="",
            version_released=days_ago(900), screenshots=[], ipad_screenshots=[],
            languages=["EN"], size_bytes=900 * 1048576, rating_count=3,
            rating_counts={5: 0, 4: 0, 3: 0, 2: 0, 1: 3}, icon_url=None,
        )
        self.assertGreaterEqual(aso.score(aso.audit(broken)), 0)


class TitleTests(unittest.TestCase):
    def test_title_over_thirty_characters_is_critical(self):
        finding = find(aso.audit(make_app(name="A" * 31)), "title.length")
        self.assertEqual(finding.severity, aso.CRITICAL)

    def test_title_at_the_limit_passes(self):
        finding = find(aso.audit(make_app(name="A" * 30)), "title.length")
        self.assertEqual(finding.severity, aso.OK)

    def test_brand_only_title_is_flagged(self):
        finding = find(aso.audit(make_app(name="Centsible")), "title.keyword")
        self.assertEqual(finding.severity, aso.WARN)


class SubtitleTests(unittest.TestCase):
    def test_missing_subtitle_is_critical(self):
        findings = aso.audit(make_app(subtitle=None))
        self.assertEqual(find(findings, "subtitle.present").severity, aso.CRITICAL)

    def test_short_subtitle_wastes_indexed_surface(self):
        finding = find(aso.audit(make_app(subtitle="Budgets")), "subtitle.length")
        self.assertEqual(finding.severity, aso.WARN)

    def test_words_shared_with_the_title_are_flagged(self):
        findings = aso.audit(
            make_app(name="Centsible Budget", subtitle="Budget tracker for teams"))
        finding = find(findings, "subtitle.overlap")
        self.assertEqual(finding.severity, aso.WARN)
        self.assertIn("budget", finding.evidence)

    def test_distinct_wording_passes(self):
        finding = find(aso.audit(make_app()), "subtitle.overlap")
        self.assertEqual(finding.severity, aso.OK)


class DescriptionTests(unittest.TestCase):
    def test_fold_without_a_benefit_phrase_is_flagged(self):
        app = make_app(description="Centsible is an application. " * 12)
        self.assertEqual(find(aso.audit(app), "description.hook").severity, aso.WARN)

    def test_repeated_term_is_reported_as_stuffing(self):
        app = make_app(description=("budget " * 40) + "and more besides here")
        finding = find(aso.audit(app), "description.stuffing")
        self.assertEqual(finding.severity, aso.WARN)

    def test_normal_prose_is_not_stuffing(self):
        self.assertEqual(
            find(aso.audit(make_app()), "description.stuffing").severity, aso.OK)


class ReleaseTests(unittest.TestCase):
    def test_boilerplate_release_notes_are_flagged(self):
        app = make_app(release_notes="Bug fixes and performance improvements.")
        self.assertEqual(find(aso.audit(app), "release.notes").severity, aso.WARN)

    def test_turkish_boilerplate_is_flagged_too(self):
        app = make_app(release_notes="Küçük hata düzeltmeleri.")
        self.assertEqual(find(aso.audit(app), "release.notes").severity, aso.WARN)

    def test_a_long_specific_note_passes_even_if_it_mentions_bug_fixes(self):
        app = make_app(release_notes=(
            "Shared wallets reconcile correctly after a long offline stretch, "
            "the receipt scanner no longer rotates portrait photos, and we "
            "fixed the crash some of you hit when editing a recurring bill "
            "whose category had been deleted. Bug fixes and performance "
            "improvements throughout the sync engine."))
        self.assertEqual(find(aso.audit(app), "release.notes").severity, aso.OK)

    def test_update_cadence_thresholds(self):
        self.assertEqual(
            find(aso.audit(make_app(version_released=days_ago(30))),
                 "release.cadence").severity, aso.OK)
        self.assertEqual(
            find(aso.audit(make_app(version_released=days_ago(120))),
                 "release.cadence").severity, aso.WARN)
        self.assertEqual(
            find(aso.audit(make_app(version_released=days_ago(400))),
                 "release.cadence").severity, aso.CRITICAL)


class CreativeTests(unittest.TestCase):
    def test_too_few_screenshots_is_critical(self):
        app = make_app(screenshots=["https://example.com/1.png"] * 2)
        self.assertEqual(find(aso.audit(app), "creative.count").severity, aso.CRITICAL)

    def test_ipad_capable_app_without_ipad_screenshots(self):
        app = make_app(ipad_screenshots=[])
        self.assertEqual(find(aso.audit(app), "creative.ipad").severity, aso.WARN)

    def test_iphone_only_app_is_not_asked_for_ipad_screenshots(self):
        app = make_app(features=[], ipad_screenshots=[])
        self.assertIsNone(find(aso.audit(app), "creative.ipad"))


class ReachAndRatingTests(unittest.TestCase):
    def test_binary_languages_are_reported_without_penalty(self):
        """languageCodesISO2A describes the binary, not the listing."""
        finding = find(aso.audit(make_app(languages=["EN"])), "reach.app_languages")
        self.assertEqual(finding.severity, aso.INFO)
        self.assertEqual(finding.weight, 0)

    def test_a_multilingual_binary_does_not_excuse_an_unlocalized_listing(self):
        """Regression: 15 listing localizations were reported as "one language"
        because the check read the binary's language list instead."""
        app = make_app(
            languages=["EN"],
            localization={
                "probed": ["us", "de", "tr"],
                "available_in": ["us", "de", "tr"],
                "ratings": {"us": 100, "de": 80, "tr": 60},
                "by_variant": {"same": ["us", "de", "tr"]},
                "distinct": 1,
            })
        self.assertEqual(
            find(aso.audit(app), "reach.listing_localization").severity, aso.WARN)

    def test_a_localized_listing_passes_even_with_a_single_language_binary(self):
        app = make_app(
            languages=["EN"],
            localization={
                "probed": ["us", "de", "tr"],
                "available_in": ["us", "de", "tr"],
                "ratings": {"us": 100, "de": 80, "tr": 60},
                "by_variant": {"en": ["us"], "de": ["de"], "tr": ["tr"]},
                "distinct": 3,
            })
        self.assertEqual(
            find(aso.audit(app), "reach.listing_localization").severity, aso.OK)

    def test_a_single_market_app_is_not_asked_to_localize(self):
        finding = find(aso.audit(make_app()), "reach.listing_localization")
        self.assertEqual(finding.severity, aso.INFO)
        self.assertEqual(finding.weight, 0)

    def test_large_download_is_flagged(self):
        app = make_app(size_bytes=420 * 1048576)
        self.assertEqual(find(aso.audit(app), "reach.size").severity, aso.WARN)

    def test_low_rating_volume_is_flagged(self):
        app = make_app(rating_count=12,
                       localization={"available_in": ["us"], "ratings": {"us": 12},
                                     "by_variant": {"a": ["us"]}, "distinct": 1,
                                     "probed": []})
        self.assertEqual(find(aso.audit(app), "ratings.volume").severity, aso.WARN)

    def test_volume_is_judged_on_the_surveyed_total_not_one_storefront(self):
        """Regression: rating volume is per storefront and varies by orders of
        magnitude, so one storefront's count is not the app's audience."""
        app = make_app(
            rating_count=9,  # the queried storefront
            localization={"available_in": ["us", "tr", "br"],
                          "ratings": {"us": 9, "tr": 40_000, "br": 12_000},
                          "by_variant": {"a": ["us"], "b": ["tr"], "c": ["br"]},
                          "distinct": 3, "probed": []})
        finding = find(aso.audit(app), "ratings.volume")
        self.assertEqual(finding.severity, aso.OK)
        self.assertIn("TR", finding.detail)

    def test_one_star_share_thresholds(self):
        heavy = make_app(rating_counts={5: 50, 4: 10, 3: 10, 2: 10, 1: 120})
        self.assertEqual(find(aso.audit(heavy), "ratings.one_star").severity,
                         aso.CRITICAL)
        middling = make_app(rating_counts={5: 700, 4: 100, 3: 50, 2: 50, 1: 180})
        self.assertEqual(find(aso.audit(middling), "ratings.one_star").severity,
                         aso.WARN)

    def test_histogram_absent_means_no_finding(self):
        self.assertIsNone(find(aso.audit(make_app(rating_counts=None)),
                               "ratings.one_star"))


class TokenisingTests(unittest.TestCase):
    def test_turkish_characters_survive_tokenisation(self):
        self.assertEqual(aso.tokens("Çöp Kutusu şişman"), ["çöp", "kutusu", "şişman"])

    def test_stopwords_and_short_words_are_dropped(self):
        self.assertEqual(aso.content_tokens("the app is a budget tool"),
                         ["budget", "tool"])


if __name__ == "__main__":
    unittest.main()


class MalformedSurveyTests(unittest.TestCase):
    """The survey comes off the network, so the audit must not trust its shape."""

    def audit_with(self, localization):
        return aso.audit(make_app(localization=localization))

    def test_empty_variant_map_does_not_crash(self):
        self.audit_with({"available_in": ["us", "de"], "ratings": {},
                         "by_variant": {}, "distinct": 2, "probed": []})

    def test_missing_keys_do_not_crash(self):
        self.audit_with({"available_in": ["us", "de"]})

    def test_localization_absent_entirely(self):
        findings = self.audit_with(None)
        self.assertIsNone(find(findings, "reach.listing_localization"))
        self.assertIsNotNone(find(findings, "ratings.volume"))


class UnusableSurveyTests(unittest.TestCase):
    """A throttled or blocked survey must not be reported as fact."""

    UNUSABLE = {"probed": ["us", "de", "tr"], "available_in": [], "ratings": {},
                "by_variant": {}, "distinct": 0, "failed": ["us", "de", "tr"],
                "usable": False}

    def test_localization_is_reported_as_unknown(self):
        finding = find(aso.audit(make_app(localization=self.UNUSABLE)),
                       "reach.listing_localization")
        self.assertEqual(finding.severity, aso.INFO)
        self.assertEqual(finding.weight, 0)

    def test_rating_volume_falls_back_to_the_queried_storefront(self):
        app = make_app(rating_count=5400, localization=self.UNUSABLE)
        finding = find(aso.audit(app), "ratings.volume")
        self.assertEqual(finding.severity, aso.OK)
        self.assertNotIn("mağaza toplamı", finding.title)

    def test_single_storefront_detail_is_not_padded_with_noise(self):
        """"En çok oy: TR 9. TR: 9." reads as a bug, because it is one."""
        app = make_app(
            rating_count=9,
            localization={"probed": ["tr"], "available_in": ["tr"],
                          "ratings": {"tr": 9}, "by_variant": {"a": ["tr"]},
                          "distinct": 1, "failed": [], "usable": True})
        finding = find(aso.audit(app), "ratings.volume")
        self.assertNotIn("En çok oy", finding.detail)
        self.assertNotIn("TR: 9", finding.detail)


class SizeReportingTests(unittest.TestCase):
    def test_size_is_printed_the_way_the_store_page_prints_it(self):
        """Regression: %.0f turned a 2.5 MB app into "3 MB"."""
        finding = find(aso.audit(make_app(size_bytes=2_520_064)), "reach.size")
        self.assertIn("2.5 MB", finding.title)

    def test_the_cellular_threshold_uses_apple_units(self):
        """205 MB as Apple counts it is over the 200 MB prompt, and used to
        read as 196 MB after a 2^20 divide."""
        over = find(aso.audit(make_app(size_bytes=205_000_000)), "reach.size")
        self.assertEqual(over.severity, aso.WARN)
        under = find(aso.audit(make_app(size_bytes=195_000_000)), "reach.size")
        self.assertEqual(under.severity, aso.OK)
