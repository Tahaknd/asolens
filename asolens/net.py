"""HTTP helpers with an on-disk cache.

Every store request goes through here so repeated runs during development do
not hammer Apple's endpoints. Cache entries are keyed by URL and expire after
`ttl` seconds.
"""

import contextlib
import gzip
import hashlib
import json
import os
import random
import tempfile
import time
import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# For the apple-app-site-association check we identify the tool instead of
# claiming to be a browser. That is both honest and more accurate: sites that
# route unknown paths through a web front end answer browser agents with an
# HTML page, while a plain client gets the real file — which is what iOS
# itself receives.
TOOL_UA = "asolens (universal-links verifier)"

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "asolens")

# Apple rate-limits the lookup endpoint, and parallel runs reach that limit
# sooner. These statuses are worth retrying; anything else is a real answer.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4
BACKOFF_BASE = 0.8
BACKOFF_CAP = 8.0


class FetchError(RuntimeError):
    pass


def _cache_path(url, ua):
    key = "%s|%s" % (url, ua)
    return os.path.join(CACHE_DIR, hashlib.sha1(key.encode()).hexdigest() + ".bin")


def get(url, ttl=3600, timeout=25, binary=False, ua=UA):
    """Fetch `url`, returning bytes (binary=True) or decoded text."""
    path = _cache_path(url, ua)
    if ttl and os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        with open(path, "rb") as fh:
            raw = fh.read()
    else:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": ua,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip",
            },
        )
        raw = _fetch_with_retries(req, url, timeout)
        _write_atomically(path, raw)
    return raw if binary else raw.decode("utf-8", "replace")


def _fetch_with_retries(req, url, timeout):
    """Issue the request, retrying rate limits and transient server errors.

    Backoff is exponential with jitter so parallel workers that all hit the
    limit at once do not then retry in lockstep. A 429 that names Retry-After
    is obeyed instead.
    """
    last = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as exc:
            last = FetchError("HTTP %s for %s" % (exc.code, url))
            if exc.code not in RETRY_STATUSES:
                raise last from exc
            delay = _retry_after(exc) or _backoff(attempt)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = FetchError("%s for %s" % (exc, url))
            delay = _backoff(attempt)
        except Exception as exc:
            raise FetchError("%s for %s" % (exc, url)) from exc

        if attempt == MAX_ATTEMPTS - 1:
            break
        time.sleep(delay)
    raise last


def _backoff(attempt):
    return min(BACKOFF_CAP, BACKOFF_BASE * (2 ** attempt)) * (0.5 + random.random())


def _retry_after(exc):
    """Seconds from a Retry-After header, when the server sends a sane one."""
    header = getattr(exc, "headers", None)
    value = header.get("Retry-After") if header else None
    if not value:
        return None
    try:
        return max(0.0, min(BACKOFF_CAP, float(value)))
    except (TypeError, ValueError):
        return None


def _write_atomically(path, raw):
    """Write through a temp file so a concurrent reader never sees a partial
    cache entry — fetches run in parallel and may target the same URL."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=CACHE_DIR, suffix=".part")
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(raw)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def get_json(url, ttl=3600, ua=UA):
    try:
        return json.loads(get(url, ttl=ttl, ua=ua))
    except ValueError as exc:
        raise FetchError("invalid JSON from %s" % url) from exc


def download(url, dest, ttl=86400):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(get(url, ttl=ttl, binary=True))
    return dest
