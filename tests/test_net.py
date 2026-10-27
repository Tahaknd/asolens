import io
import unittest
import urllib.error
from unittest import mock

from asolens import net


class FakeResponse(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def http_error(code, headers=None):
    """An HTTPError with a real file object, so cleanup stays quiet."""
    return urllib.error.HTTPError(
        "http://x", code, "nope", headers or {}, io.BytesIO(b""))


class RetryTests(unittest.TestCase):
    def setUp(self):
        # never actually sleep, and keep backoff deterministic
        self.sleeps = []
        patcher = mock.patch.object(net.time, "sleep", self.sleeps.append)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fetch(self, side_effect):
        with mock.patch.object(net.urllib.request, "urlopen",
                               side_effect=side_effect) as opener:
            try:
                body = net.get("https://example.com/x", ttl=0)
            except net.FetchError as exc:
                return None, opener.call_count, exc
            return body, opener.call_count, None

    def test_a_rate_limit_is_retried_until_it_succeeds(self):
        body, calls, error = self.fetch(
            [http_error(429), http_error(429), FakeResponse(b"ok")])
        self.assertEqual(body, "ok")
        self.assertEqual(calls, 3)
        self.assertIsNone(error)
        self.assertEqual(len(self.sleeps), 2)

    def test_retry_after_header_is_obeyed(self):
        self.fetch([http_error(429, {"Retry-After": "2"}), FakeResponse(b"ok")])
        self.assertEqual(self.sleeps, [2.0])

    def test_a_nonsense_retry_after_falls_back_to_backoff(self):
        self.fetch([http_error(429, {"Retry-After": "soon"}), FakeResponse(b"ok")])
        self.assertEqual(len(self.sleeps), 1)
        self.assertGreater(self.sleeps[0], 0)

    def test_server_errors_are_retried(self):
        body, calls, _ = self.fetch([http_error(503), FakeResponse(b"ok")])
        self.assertEqual(body, "ok")
        self.assertEqual(calls, 2)

    def test_a_404_is_not_retried(self):
        _, calls, error = self.fetch([http_error(404)])
        self.assertEqual(calls, 1)
        self.assertIn("404", str(error))

    def test_timeouts_are_retried_then_give_up(self):
        _, calls, error = self.fetch(TimeoutError("timed out"))
        self.assertEqual(calls, net.MAX_ATTEMPTS)
        self.assertIsNotNone(error)

    def test_backoff_grows_and_is_capped(self):
        delays = [net._backoff(n) for n in range(8)]
        self.assertTrue(all(d <= net.BACKOFF_CAP * 1.5 for d in delays))
        self.assertLess(delays[0], delays[-1])

    def test_gzip_bodies_are_decompressed(self):
        import gzip
        packed = gzip.compress(b"hello")
        body, _, _ = self.fetch(
            [FakeResponse(packed, {"Content-Encoding": "gzip"})])
        self.assertEqual(body, "hello")


class CacheKeyTests(unittest.TestCase):
    def test_the_user_agent_is_part_of_the_key(self):
        """Two agents can get different bodies for one URL, as instagram.com does."""
        self.assertNotEqual(
            net._cache_path("https://example.com/a", net.UA),
            net._cache_path("https://example.com/a", net.TOOL_UA),
        )


if __name__ == "__main__":
    unittest.main()


class CacheManagementTests(unittest.TestCase):
    def setUp(self):
        import tempfile, shutil
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        patcher = mock.patch.object(net, "CACHE_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name, body=b"x" * 100, age_days=0):
        import os, time
        path = os.path.join(self.dir, name)
        with open(path, "wb") as fh:
            fh.write(body)
        if age_days:
            old = time.time() - age_days * 86400
            os.utime(path, (old, old))
        return path

    def test_stats_counts_entries_and_bytes(self):
        self.write("a"), self.write("b")
        stats = net.cache_stats()
        self.assertEqual(stats["entries"], 2)
        self.assertEqual(stats["bytes"], 200)

    def test_stats_on_a_missing_directory(self):
        import shutil
        shutil.rmtree(self.dir)
        self.assertEqual(net.cache_stats(),
                         {"entries": 0, "bytes": 0, "oldest_days": None})

    def test_oldest_age_is_reported(self):
        self.write("old", age_days=5)
        self.write("new")
        self.assertAlmostEqual(net.cache_stats()["oldest_days"], 5.0, places=0)

    def test_clear_removes_everything(self):
        self.write("a"), self.write("b")
        removed, freed = net.cache_clear()
        self.assertEqual(removed, 2)
        self.assertEqual(freed, 200)
        self.assertEqual(net.cache_stats()["entries"], 0)

    def test_prune_keeps_recent_entries(self):
        self.write("old", age_days=30)
        self.write("fresh")
        removed, _ = net.cache_clear(older_than_days=7)
        self.assertEqual(removed, 1)
        self.assertEqual(net.cache_stats()["entries"], 1)
