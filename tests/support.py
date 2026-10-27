"""Builders for test data.

Tests never touch the network: everything is built from these dictionaries,
shaped exactly like `ios_store.fetch_app` returns.
"""

DEFAULT_DESCRIPTION = (
    "Track every expense in seconds and save more each month.\n\n"
    "Centsible keeps budgets, recurring bills and shared wallets in one "
    "place, and every one of them works offline first. Scan a receipt and "
    "the amount, merchant and category are filled in before you put your "
    "phone down.\n\n"
    "Set a monthly plan per category and watch the remaining balance move "
    "as you spend. Recurring bills are detected from your own history "
    "rather than typed in by hand, so a rent increase or a cancelled "
    "subscription shows up on its own.\n\n"
    "Share a wallet with a partner or a flatmate. Everyone adds entries "
    "from their own phone, the ledger reconciles when the devices next "
    "meet, and nobody has to settle up from memory at the end of the "
    "month."
)


def make_app(**overrides):
    """A healthy app profile. Pass overrides to break one thing at a time."""
    app = {
        "id": "123456789",
        "country": "us",
        "name": "Centsible — Budget Tracker",
        "subtitle": "Save money without effort",
        "bundle_id": "com.example.centsible",
        "developer": "Example Labs",
        "seller_url": "https://example.com/",
        "store_url": "https://apps.apple.com/us/app/id123456789",
        "description": DEFAULT_DESCRIPTION,
        "release_notes": "Shared wallets now sync offline and reconcile on reconnect.",
        "version": "2.4.0",
        "released": "2021-03-02T10:00:00Z",
        "version_released": _recent(),
        "price": "Free",
        "genres": ["Finance"],
        "primary_genre": "Finance",
        "content_rating": "4+",
        "min_os": "15.0",
        "size_bytes": 48 * 1048576,
        "languages": ["EN", "TR", "DE"],
        "rating": 4.6,
        "rating_count": 5400,
        "icon_url": "https://example.com/icon.png",
        "screenshots": ["https://example.com/%d.png" % i for i in range(1, 7)],
        "ipad_screenshots": ["https://example.com/ipad%d.png" % i for i in range(1, 4)],
        "features": ["iosUniversal"],
        "rating_counts": {5: 4000, 4: 800, 3: 300, 2: 150, 1: 150},
        "privacy_types": [],
        "similar_apps": [],
        "editors_choice": False,
        "localization": {
            "probed": ["us"], "available_in": ["us"], "ratings": {"us": 5400},
            "by_variant": {"abc": ["us"]}, "distinct": 1,
        },
        "review_markets": ["us"],
        "reviews": [],
    }
    app.update(overrides)
    return app


def _recent():
    import datetime

    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=12)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def days_ago(days):
    import datetime

    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_review(rating=1, title="", body="", version="2.4.0", country="us", rid=None):
    make_review.counter = getattr(make_review, "counter", 0) + 1
    return {
        "id": rid or str(make_review.counter),
        "author": "tester",
        "rating": rating,
        "version": version,
        "title": title,
        "body": body,
        "updated": "2026-10-20T10:00:00-07:00",
        "country": country,
    }


def find(findings, check):
    """The single finding for a check id, or None."""
    for finding in findings:
        if finding.check == check:
            return finding
    return None
