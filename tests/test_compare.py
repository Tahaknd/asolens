import unittest
from unittest import mock

from asolens import compare, ios_store
from tests.support import days_ago, make_app


class RowTests(unittest.TestCase):
    def test_row_summarises_an_app_for_the_table(self):
        row = compare.row(make_app(version_released=days_ago(40)))
        self.assertEqual(row["title_len"], len("Centsible — Budget Tracker"))
        self.assertEqual(row["subtitle_len"], len("Save money without effort"))
        self.assertEqual(row["screenshots"], 6)
        self.assertEqual(row["languages"], 3)
        self.assertEqual(row["size_mb"], 50)
        self.assertEqual(row["days_since_update"], 40)

    def test_missing_release_date_does_not_crash(self):
        self.assertIsNone(compare.row(make_app(version_released=None))["days_since_update"])

    def test_absent_subtitle_becomes_an_empty_string(self):
        self.assertEqual(compare.row(make_app(subtitle=None))["subtitle"], "")


class KeywordGapTests(unittest.TestCase):
    def gap(self, target, competitors):
        return compare.keyword_gap(target, competitors)

    def test_terms_competitors_use_and_we_do_not(self):
        target = make_app(name="Centsible", subtitle="Save money", description="")
        competitors = [
            make_app(name="Spendly", subtitle="Expense tracker"),
            make_app(name="Walletly", subtitle="Expense manager"),
        ]
        terms = {g["term"]: g for g in self.gap(target, competitors)["gaps"]}
        self.assertIn("expense", terms)
        self.assertEqual(terms["expense"]["competitors"], 2)
        self.assertAlmostEqual(terms["expense"]["share"], 1.0)

    def test_terms_we_already_use_are_not_gaps(self):
        target = make_app(name="Budget Tracker", subtitle="Save money")
        competitors = [make_app(name="Spendly", subtitle="Budget planner")]
        result = self.gap(target, competitors)
        self.assertNotIn("budget", [g["term"] for g in result["gaps"]])
        self.assertIn("budget", result["shared"])

    def test_a_term_only_in_our_description_is_still_a_gap_but_marked(self):
        target = make_app(name="Centsible", subtitle="Save money",
                          description="A receipt scanner for everyday spending.")
        competitors = [make_app(name="Spendly", subtitle="Receipt scanner")]
        receipt = next(g for g in self.gap(target, competitors)["gaps"]
                       if g["term"] == "receipt")
        self.assertTrue(receipt["in_our_description"])

    def test_gaps_are_ranked_by_how_many_competitors_use_them(self):
        target = make_app(name="Centsible", subtitle="Money", description="")
        competitors = [
            make_app(name="A", subtitle="expense receipt"),
            make_app(name="B", subtitle="expense planner"),
            make_app(name="C", subtitle="expense budget"),
        ]
        gaps = self.gap(target, competitors)["gaps"]
        self.assertEqual(gaps[0]["term"], "expense")
        self.assertEqual(gaps[0]["competitors"], 3)

    def test_used_by_lists_at_most_three_examples(self):
        target = make_app(name="Centsible", subtitle="Money", description="")
        competitors = [make_app(name="App%d" % i, subtitle="expense tracker")
                       for i in range(6)]
        gap = next(g for g in self.gap(target, competitors)["gaps"]
                   if g["term"] == "expense")
        self.assertEqual(len(gap["used_by"]), 3)
        self.assertEqual(gap["competitors"], 6)

    def test_no_competitors_yields_no_gaps(self):
        result = self.gap(make_app(), [])
        self.assertEqual(result["gaps"], [])

    def test_our_surface_is_title_plus_subtitle_only(self):
        target = make_app(name="Centsible Budget", subtitle="Save money",
                          description="receipts and invoices everywhere")
        surface = self.gap(target, [])["our_surface"]
        self.assertIn("budget", surface)
        self.assertNotIn("receipts", surface)


class RunTests(unittest.TestCase):
    def test_a_failing_competitor_is_recorded_not_raised(self):
        def fetch(app_id, **kwargs):
            if app_id == "bad":
                raise RuntimeError("404")
            return make_app(id=app_id, name="Rival " + app_id)

        with mock.patch.object(ios_store, "fetch_app", side_effect=fetch):
            result = compare.run(make_app(), ["good", "bad"], country="us")
        self.assertEqual(result["count"], 1)
        self.assertEqual([e["id"] for e in result["errors"]], ["bad"])

    def test_the_target_is_always_the_first_row(self):
        with mock.patch.object(ios_store, "fetch_app",
                               side_effect=lambda i, **k: make_app(name="Rival")):
            result = compare.run(make_app(name="Mine"), ["a", "b"], country="us")
        self.assertEqual(result["rows"][0]["name"], "Mine")
        self.assertEqual(len(result["rows"]), 3)


if __name__ == "__main__":
    unittest.main()


class CompetitorCostTests(unittest.TestCase):
    def test_competitors_are_fetched_without_a_storefront_survey(self):
        """Regression: six competitors each ran an 18-storefront survey,
        turning a comparison into 120 requests for data the table never uses."""
        seen = []

        def fetch(app_id, **kwargs):
            seen.append(kwargs)
            return make_app(name="Rival")

        with mock.patch.object(ios_store, "fetch_app", side_effect=fetch):
            compare.run(make_app(), ["a", "b"], country="us")
        self.assertTrue(seen)
        for kwargs in seen:
            self.assertFalse(kwargs.get("with_localization", True))
            self.assertFalse(kwargs.get("with_reviews", True))
