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
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
        except urllib.error.HTTPError as exc:
            raise FetchError("HTTP %s for %s" % (exc.code, url)) from exc
        except Exception as exc:
            raise FetchError("%s for %s" % (exc, url)) from exc
        _write_atomically(path, raw)
    return raw if binary else raw.decode("utf-8", "replace")


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
