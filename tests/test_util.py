import unittest

from asolens import util
from tests.support import days_ago


class DaysSinceTests(unittest.TestCase):
    def test_counts_whole_days(self):
        self.assertEqual(util.days_since(days_ago(7)), 7)

    def test_date_only_stamps_are_accepted(self):
        self.assertIsNotNone(util.days_since("2024-01-01"))

    def test_unparseable_input_returns_none(self):
        for value in (None, "", "yesterday", "2024-13-99", 12345):
            with self.subTest(value=value):
                self.assertIsNone(util.days_since(value))


class HumanSizeTests(unittest.TestCase):
    def test_small_sizes_read_as_kilobytes(self):
        self.assertEqual(util.human_size(2000), "2 KB")

    def test_large_sizes_read_as_megabytes(self):
        self.assertEqual(util.human_size(48 * 1_000_000), "48.0 MB")

    def test_sizes_match_what_the_store_page_shows(self):
        """Regression: Apple counts megabytes decimally. 2,520,064 bytes is
        "2.5 MB" on the product page, not the 2.4 that 2^20 gives."""
        self.assertEqual(util.human_size(2_520_064), "2.5 MB")
        self.assertAlmostEqual(util.megabytes(2_520_064), 2.520064)

    def test_zero_and_none(self):
        self.assertEqual(util.human_size(0), "0 KB")
        self.assertEqual(util.human_size(None), "0 KB")


class WrapTests(unittest.TestCase):
    def test_wraps_at_the_given_width(self):
        lines = util.wrap("one two three four five six", 10)
        self.assertTrue(all(len(line) <= 10 for line in lines))
        self.assertEqual(" ".join(lines), "one two three four five six")

    def test_empty_input(self):
        self.assertEqual(util.wrap("", 10), [])
        self.assertEqual(util.wrap(None, 10), [])


class ParallelMapTests(unittest.TestCase):
    def test_order_is_preserved(self):
        self.assertEqual(util.parallel_map(lambda n: n * 2, range(10)),
                         [n * 2 for n in range(10)])

    def test_single_and_empty_inputs_skip_the_pool(self):
        self.assertEqual(util.parallel_map(str, []), [])
        self.assertEqual(util.parallel_map(str, [1]), ["1"])

    def test_exceptions_propagate(self):
        def boom(n):
            if n == 3:
                raise ValueError("boom")
            return n
        with self.assertRaises(ValueError):
            util.parallel_map(boom, range(6))


if __name__ == "__main__":
    unittest.main()
