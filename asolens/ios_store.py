"""App Store data access.

Three sources are combined, because none of them is complete on its own:

* the public iTunes Lookup API — name, description, screenshots, version, size
* the product web page — subtitle, rating histogram, privacy labels, similar
  apps (none of these appear in the Lookup API)
* the customer-reviews RSS feed — up to ~500 recent reviews per country
"""

import hashlib
import json
import re
import urllib.parse

from asolens import net
from asolens.util import parallel_map

LOOKUP = "https://itunes.apple.com/lookup?id={app_id}&country={country}"
PAGE = "https://apps.apple.com/{country}/app/id{app_id}"
REVIEWS = (
    "https://itunes.apple.com/{country}/rss/customerreviews/page={page}"
    "/id={app_id}/sortby=mostrecent/json"
)

REVIEW_PAGES = 10  # Apple caps the feed at 10 pages of 50

# Storefronts probed to tell whether the App Store *listing* is localized.
# The listing (name, subtitle, description) is localized in App Store Connect
# and is a different thing from the languages the binary ships, which is what
# languageCodesISO2A reports. An app can support 39 languages and still show
# English copy in every storefront.
PROBE_STOREFRONTS = (
    "us", "gb", "de", "fr", "es", "it", "nl", "pl",
    "tr", "ru", "br", "mx", "jp", "kr", "cn", "in", "id", "sa",
)


APPLE_HOSTS = ("apps.apple.com", "itunes.apple.com", "music.apple.com")


def parse_url(value):
    """Accept a store URL, an `id123` fragment or a bare numeric id.

    Returns (app_id, country) where country falls back to None so the caller
    can apply its own default.
    """
    value = (value or "").strip()
    if value.isdigit():
        return value, None

    parsed = urllib.parse.urlparse(value if "//" in value else "https://" + value)
    host = parsed.netloc.lower().split(":")[0]
    on_apple = host.endswith(APPLE_HOSTS)

    match = re.search(r"\bid(\d{6,})", value)
    if not match and on_apple:
        # Some Apple URLs carry the id without the "id" prefix. Only trust a
        # bare number on an Apple host: elsewhere it is far more likely to be
        # a date or an unrelated path segment.
        match = re.search(r"(\d{8,})", parsed.path)
    if not match:
        raise ValueError("could not find an app id in %r" % value)

    country = None
    parts = [p for p in parsed.path.split("/") if p]
    if parts and len(parts[0]) == 2 and parts[0].isalpha():
        country = parts[0].lower()
    return match.group(1), country


def lookup(app_id, country="us", ttl=3600):
    data = net.get_json(LOOKUP.format(app_id=app_id, country=country), ttl=ttl)
    results = data.get("results") or []
    if not results:
        raise net.FetchError(
            "app %s not found in the %s store" % (app_id, country.upper())
        )
    return results[0]


def _server_data(html):
    match = re.search(
        r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', html, re.S
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def page_extras(app_id, country="us", ttl=3600):
    """Scrape the fields the Lookup API does not expose.

    Returns a dict with keys that are always present but may be None/empty, so
    callers never have to guard every access.
    """
    out = {
        "subtitle": None,
        "rating_counts": None,
        "privacy_types": [],
        "similar_apps": [],
        "editorial_badge": False,
    }
    try:
        html = net.get(PAGE.format(app_id=app_id, country=country), ttl=ttl)
    except net.FetchError:
        return out
    data = _server_data(html)
    if not data:
        return out
    try:
        page = data["data"][0]["data"]
    except (KeyError, IndexError, TypeError):
        return out

    lock = page.get("lockup") or {}
    out["subtitle"] = lock.get("subtitle")
    out["editorial_badge"] = bool(lock.get("isEditorsChoice"))

    shelves = page.get("shelfMapping") or {}

    ratings = ((shelves.get("productRatings") or {}).get("items") or [{}])[0]
    counts = ratings.get("ratingCounts")
    if isinstance(counts, list) and len(counts) == 5:
        # Apple returns the histogram 5-star first and as floats.
        out["rating_counts"] = {5 - i: int(round(c)) for i, c in enumerate(counts)}

    for item in (shelves.get("privacyTypes") or {}).get("items") or []:
        out["privacy_types"].append(
            {
                "identifier": item.get("identifier"),
                "title": item.get("title"),
                "categories": [
                    c.get("title")
                    for c in (item.get("categories") or [])
                    if c.get("title")
                ],
            }
        )

    for item in (shelves.get("similarItems") or {}).get("items") or []:
        app = {
            "id": str(item.get("adamId") or item.get("id") or ""),
            "name": item.get("title") or item.get("name"),
            "subtitle": item.get("subtitle"),
            "developer": item.get("developerName"),
            "rating": item.get("rating"),
            "rating_count": item.get("ratingCount"),
        }
        if app["id"]:
            out["similar_apps"].append(app)
    return out


def reviews(app_id, country="us", pages=REVIEW_PAGES, ttl=3600):
    """Return recent reviews, newest first. Missing pages are skipped."""
    found = []
    for page in range(1, pages + 1):
        url = REVIEWS.format(country=country, page=page, app_id=app_id)
        try:
            data = net.get_json(url, ttl=ttl)
        except net.FetchError:
            break
        entries = (data.get("feed") or {}).get("entry") or []
        if isinstance(entries, dict):
            entries = [entries]
        batch = 0
        for entry in entries:
            # The first entry of page 1 is the app itself, not a review.
            if "im:rating" not in entry:
                continue
            found.append(
                {
                    "id": _label(entry.get("id")),
                    "author": _label((entry.get("author") or {}).get("name")),
                    "rating": int(_label(entry.get("im:rating")) or 0),
                    "version": _label(entry.get("im:version")),
                    "title": _label(entry.get("title")),
                    "body": _label(entry.get("content")),
                    "updated": _label(entry.get("updated")),
                    "country": country,
                }
            )
            batch += 1
        if batch == 0:
            break
    return found


def subtitle_or_none(subtitle, genres):
    """Drop a "subtitle" that is really the category name.

    An app with no subtitle still gets a populated `subtitle` field on the
    product page: Apple falls back to the genre. Taking that at face value
    turns a missing subtitle — the second most heavily indexed field on iOS —
    into a merely short one, and feeds the category word into the keyword
    surface as if the developer had chosen it.
    """
    if not subtitle:
        return None
    normalised = subtitle.strip().casefold()
    if any(normalised == (genre or "").strip().casefold() for genre in genres or ()):
        return None
    return subtitle


def storefront_survey(app_id, storefronts=PROBE_STOREFRONTS, ttl=3600):
    """One lookup per storefront, answering two questions at once.

    * Is the listing localized? The Lookup API does not publish the set of
      App Store Connect localizations, but it serves each storefront the copy
      that storefront shows, so distinct texts count the localizations
      directly.
    * Where are this app's users? userRatingCount is per storefront and varies
      by orders of magnitude, which is the signal for choosing where to read
      reviews.

    Both come from the same requests, so the survey costs nothing extra.
    """
    def probe(code):
        """(code, state, digest, ratings) where state is present/absent/error.

        "Not sold in this storefront" and "the request failed" must not look
        alike: the first is a fact about the app, the second is a gap in what
        we know, and reporting the second as the first is how a throttled run
        ends up asserting an app is single-market.
        """
        try:
            data = net.get_json(
                LOOKUP.format(app_id=app_id, country=code), ttl=ttl)
        except net.FetchError:
            return code, "error", None, 0
        found = data.get("results") or []
        if not found:
            return code, "absent", None, 0
        record = found[0]
        text = "%s\u0000%s\u0000%s" % (
            record.get("trackName") or "",
            record.get("description") or "",
            record.get("releaseNotes") or "")
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        return code, "present", digest, int(record.get("userRatingCount") or 0)

    available, ratings, variants, failed = [], {}, {}, []
    for code, state, digest, count in parallel_map(probe, storefronts):
        if state == "error":
            failed.append(code)
            continue
        if state == "absent":
            continue
        available.append(code)
        ratings[code] = count
        variants.setdefault(digest, []).append(code)
    return {
        "probed": list(storefronts),
        "available_in": sorted(available),
        "failed": sorted(failed),
        "ratings": ratings,
        "by_variant": {d: sorted(c) for d, c in variants.items()},
        "distinct": len(variants),
        # A survey that reached nothing knows nothing. Callers must be able to
        # tell that apart from an app that genuinely sells in one market.
        "usable": bool(available) and len(failed) < len(storefronts) / 2,
    }


def rank_review_markets(survey, preferred=None, limit=3):
    """Storefronts worth reading reviews from, busiest first.

    The storefront the caller named is pinned to the front when the app sells
    there: it is the market they asked about, whatever the global numbers say.
    """
    available = (survey or {}).get("available_in") or []
    ratings = (survey or {}).get("ratings") or {}
    ranked = sorted(available, key=lambda c: ratings.get(c, 0), reverse=True)
    if preferred in ranked:
        ranked = [preferred] + [c for c in ranked if c != preferred]
    return ranked[:limit]


def _label(node):
    if isinstance(node, dict):
        return node.get("label") or ""
    return node or ""


def fetch_app(app_id, country="us", review_countries=(), review_pages=REVIEW_PAGES,
              ttl=3600, with_reviews=True, with_localization=True,
              review_markets=3):
    """Assemble one app's full profile from every source."""
    record = lookup(app_id, country=country, ttl=ttl)
    extras = page_extras(app_id, country=country, ttl=ttl)
    profile = {
        "id": str(record.get("trackId")),
        "country": country,
        "name": record.get("trackName"),
        "subtitle": subtitle_or_none(extras["subtitle"], record.get("genres")),
        "bundle_id": record.get("bundleId"),
        "developer": record.get("artistName"),
        "seller_url": record.get("sellerUrl"),
        "store_url": record.get("trackViewUrl"),
        "description": record.get("description") or "",
        "release_notes": record.get("releaseNotes") or "",
        "version": record.get("version"),
        "released": record.get("releaseDate"),
        "version_released": record.get("currentVersionReleaseDate"),
        "price": record.get("formattedPrice"),
        "genres": record.get("genres") or [],
        "primary_genre": record.get("primaryGenreName"),
        "content_rating": record.get("contentAdvisoryRating"),
        "min_os": record.get("minimumOsVersion"),
        "size_bytes": int(record.get("fileSizeBytes") or 0),
        "languages": record.get("languageCodesISO2A") or [],
        "rating": record.get("averageUserRating"),
        "rating_count": int(record.get("userRatingCount") or 0),
        "icon_url": record.get("artworkUrl512") or record.get("artworkUrl100"),
        "screenshots": record.get("screenshotUrls") or [],
        "ipad_screenshots": record.get("ipadScreenshotUrls") or [],
        "features": record.get("features") or [],
        "rating_counts": extras["rating_counts"],
        "privacy_types": extras["privacy_types"],
        "similar_apps": extras["similar_apps"],
        "editors_choice": extras["editorial_badge"],
        "localization": None,
        "review_markets": [],
        "reviews": [],
    }
    if with_localization:
        profile["localization"] = storefront_survey(app_id, ttl=ttl)
    if with_reviews:
        countries = list(review_countries)
        if not countries:
            # Reviews are per storefront. Reading only the one the caller
            # happened to name reports a handful of reviews for an app whose
            # audience is elsewhere, with nothing to say that is what happened.
            countries = rank_review_markets(
                profile["localization"], preferred=country,
                limit=review_markets) or [country]
        profile["review_markets"] = countries
        batches = parallel_map(
            lambda code: reviews(app_id, country=code, pages=review_pages, ttl=ttl),
            countries)
        seen = set()
        for batch in batches:
            for review in batch:
                if review["id"] in seen:
                    continue
                seen.add(review["id"])
                profile["reviews"].append(review)
        profile["reviews"].sort(key=lambda r: r["updated"], reverse=True)
    return profile
