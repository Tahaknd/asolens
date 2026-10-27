import unittest

from asolens import reviews
from tests.support import make_review


def themes_of(*texts, rating=1):
    summary = reviews.summarize([make_review(rating=rating, title=t) for t in texts])
    return {t["key"]: t["count"] for t in summary["themes"]}


class ThemeMatchingTests(unittest.TestCase):
    def test_words_merely_containing_a_term_do_not_match(self):
        """Regression: substring matching filed "downloads" under ads."""
        found = themes_of(
            "Downloads are slow to start",
            "The roads feature is great",
            "App uploads my photos twice",
        )
        self.assertNotIn("ads", found)

    def test_genuine_mentions_still_match(self):
        self.assertEqual(themes_of("Too many ads in this app").get("ads"), 1)
        self.assertEqual(themes_of("reklamlar çok fazla").get("ads"), 1)

    def test_turkish_suffixes_do_not_break_matching(self):
        """Turkish is agglutinative, so terms must match inflected forms."""
        for text in ("uygulama sürekli çöküyordu",
                     "açarken çöküyor",
                     "giriş yapamıyorum bir türlü"):
            with self.subTest(text=text):
                self.assertTrue(themes_of(text), "no theme matched %r" % text)

    def test_english_inflections_match(self):
        self.assertEqual(themes_of("it keeps crashing").get("crash"), 1)
        self.assertEqual(themes_of("the app is so laggy").get("performance"), 1)

    def test_matching_ignores_case(self):
        self.assertEqual(themes_of("CRASHES every time").get("crash"), 1)

    def test_a_review_can_carry_several_themes(self):
        found = themes_of("It crashes constantly and the ads are everywhere")
        self.assertEqual(found.get("crash"), 1)
        self.assertEqual(found.get("ads"), 1)


class SummaryTests(unittest.TestCase):
    def test_the_storefront_split_is_reported(self):
        """Output must say where the reviews came from, so a thin result is
        recognisable as "wrong storefront" rather than "few complaints"."""
        summary = reviews.summarize([
            make_review(rating=1, country="tr"),
            make_review(rating=1, country="tr"),
            make_review(rating=2, country="us"),
        ])
        self.assertEqual(summary["markets"], [("tr", 2), ("us", 1)])

    def test_empty_input_returns_an_empty_shape(self):
        summary = reviews.summarize([])
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["themes"], [])
        self.assertIsNone(summary["average"])

    def test_only_negative_reviews_are_mined_for_themes(self):
        summary = reviews.summarize([
            make_review(rating=5, title="No ads at all, wonderful"),
            make_review(rating=1, title="Too many ads"),
        ])
        self.assertEqual(summary["negative"], 1)
        self.assertEqual([t["count"] for t in summary["themes"]], [1])

    def test_three_stars_counts_as_a_complaint(self):
        summary = reviews.summarize([make_review(rating=3, title="constant crashes")])
        self.assertEqual(summary["negative"], 1)

    def test_average_and_histogram(self):
        summary = reviews.summarize([
            make_review(rating=5), make_review(rating=5), make_review(rating=1),
        ])
        self.assertAlmostEqual(summary["average"], 11 / 3)
        self.assertEqual(summary["histogram"][5], 2)
        self.assertEqual(summary["histogram"][1], 1)
        self.assertEqual(summary["histogram"][4], 0)

    def test_quotes_are_capped_and_carry_context(self):
        summary = reviews.summarize(
            [make_review(rating=1, title="crashes on launch", version="3.1.0")] * 1
            + [make_review(rating=1, title="crashes again") for _ in range(6)])
        theme = summary["themes"][0]
        self.assertLessEqual(len(theme["quotes"]), 3)
        self.assertIn("version", theme["quotes"][0])
        self.assertIn("country", theme["quotes"][0])

    def test_share_is_relative_to_negative_reviews(self):
        summary = reviews.summarize([
            make_review(rating=1, title="too many ads"),
            make_review(rating=1, title="nothing in particular"),
            make_review(rating=5, title="great"),
        ])
        self.assertAlmostEqual(summary["themes"][0]["share"], 0.5)


class VersionRollupTests(unittest.TestCase):
    def test_versions_sort_newest_first_numerically(self):
        summary = reviews.summarize([
            make_review(version="9.0.0"), make_review(version="10.0.0"),
            make_review(version="2.0.0"),
        ])
        self.assertEqual([v["version"] for v in summary["by_version"]],
                         ["10.0.0", "9.0.0", "2.0.0"])

    def test_missing_version_is_grouped_not_dropped(self):
        summary = reviews.summarize([make_review(version="")])
        self.assertEqual(summary["by_version"][0]["version"], "?")

    def test_per_version_average_and_negative_share(self):
        summary = reviews.summarize([
            make_review(rating=1, version="5.0"), make_review(rating=5, version="5.0"),
        ])
        row = summary["by_version"][0]
        self.assertEqual(row["count"], 2)
        self.assertAlmostEqual(row["average"], 3.0)
        self.assertAlmostEqual(row["negative_share"], 0.5)


class TrimTests(unittest.TestCase):
    def test_whitespace_is_collapsed(self):
        self.assertEqual(reviews._trim("a\n\n  b\tc"), "a b c")

    def test_long_text_is_truncated_with_an_ellipsis(self):
        trimmed = reviews._trim("x" * 300, limit=50)
        self.assertEqual(len(trimmed), 50)
        self.assertTrue(trimmed.endswith("…"))


if __name__ == "__main__":
    unittest.main()
