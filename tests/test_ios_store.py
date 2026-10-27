import unittest

from asolens import ios_store


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
