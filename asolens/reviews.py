"""Review mining.

Deterministic theme buckets, bilingual (TR/EN), chosen so the output is a
product backlog rather than a sentiment number: each theme maps to something a
team can actually fix. Nothing here calls an LLM — `handoff_brief` writes the
raw material out when you want a model to read the long tail instead.
"""

import collections
import re

THEMES = {
    "crash": {
        "label": "Çökme / donma",
        "terms": ["crash", "crashes", "crashing", "freeze", "frozen", "hang",
                  "çöküyor", "çökme", "kapanıyor", "donuyor", "donma",
                  "kendini kapatıyor", "atıyor"],
    },
    "performance": {
        "label": "Yavaşlık",
        "terms": ["slow", "laggy", "lag", "sluggish", "takes forever",
                  "yavaş", "geç açılıyor", "takılıyor", "kasıyor"],
    },
    "login": {
        "label": "Giriş / hesap",
        "terms": ["can't log in", "cant log in", "login", "log in", "sign in",
                  "password", "verification", "otp", "giriş yapamıyorum",
                  "giriş yapmıyor", "şifre", "doğrulama", "hesabım",
                  "giriş sorunu"],
    },
    "pricing": {
        "label": "Fiyat / abonelik",
        "terms": ["expensive", "price", "subscription", "paywall", "refund",
                  "charged", "trial", "pahalı", "fiyat", "abonelik", "ücret",
                  "para", "iade", "ödeme"],
    },
    "ads": {
        "label": "Reklam",
        "terms": ["ads", "advert", "too many ads", "pop-up", "popup",
                  "reklam", "reklamlar"],
    },
    "update_regression": {
        "label": "Güncelleme sonrası bozulma",
        "terms": ["after the update", "after update", "last update",
                  "new version", "update broke", "güncellemeden sonra",
                  "son güncelleme", "yeni sürüm", "eski hali"],
    },
    "onboarding": {
        "label": "Kurulum / ilk kullanım",
        "terms": ["confusing", "can't figure", "how do i", "hard to use",
                  "complicated", "karışık", "anlaşılmıyor", "kullanışsız",
                  "karmaşık", "nasıl yapılır"],
    },
    "notifications": {
        "label": "Bildirim",
        "terms": ["notification", "notifications", "push", "bildirim",
                  "bildirimler", "uyarı gelmiyor"],
    },
    "missing_feature": {
        "label": "Eksik özellik talebi",
        "terms": ["please add", "wish it had", "would be nice", "needs a",
                  "feature request", "eklenmeli", "olsa çok iyi olur",
                  "eksik", "özellik ekleyin", "keşke"],
    },
    "localization": {
        "label": "Dil / çeviri",
        "terms": ["translation", "in english", "language", "not translated",
                  "türkçe", "çeviri", "dil desteği", "ingilizce"],
    },
    "data_loss": {
        "label": "Veri kaybı / senkron",
        "terms": ["lost my data", "deleted my", "sync", "not syncing",
                  "backup", "verilerim gitti", "kayboldu", "senkron",
                  "yedek"],
    },
    "support": {
        "label": "Destek yanıtsız",
        "terms": ["no response", "support", "customer service", "contacted",
                  "destek", "cevap vermiyor", "ulaşamıyorum",
                  "müşteri hizmetleri"],
    },
}

NEGATIVE_MAX = 3  # ratings at or below this count as complaints


def _matcher(terms):
    """Compile a theme's terms into one left-anchored pattern.

    Matching is anchored at a word start but deliberately left open at the
    end. A plain substring test counts "downloads", "roads" and "uploads" as
    the "ads" theme, which corrupts the headline numbers; anchoring both ends
    would instead break Turkish, where the language is agglutinative and
    "çöküyor" legitimately appears as "çöküyordu" or "çöküyorum". A left
    anchor is the only form that satisfies both.
    """
    return re.compile(
        "|".join(r"\b" + re.escape(term) for term in terms), re.IGNORECASE)


THEME_MATCHERS = {key: _matcher(spec["terms"]) for key, spec in THEMES.items()}


def summarize(reviews):
    """Aggregate ratings, themes and version signal from a review list."""
    if not reviews:
        return {
            "total": 0, "average": None, "histogram": {}, "themes": [],
            "by_version": [], "negative": 0, "quotes": {}, "markets": [],
        }

    hist = collections.Counter(r["rating"] for r in reviews)
    negatives = [r for r in reviews if r["rating"] <= NEGATIVE_MAX]

    theme_hits = collections.Counter()
    theme_quotes = collections.defaultdict(list)
    for review in negatives:
        text = ("%s %s" % (review["title"], review["body"])).lower()
        for key, matcher in THEME_MATCHERS.items():
            if matcher.search(text):
                theme_hits[key] += 1
                if len(theme_quotes[key]) < 3:
                    theme_quotes[key].append({
                        "rating": review["rating"],
                        "version": review["version"],
                        "text": _trim(review["title"] or review["body"]),
                        "country": review["country"],
                    })

    themes = [
        {
            "key": key,
            "label": THEMES[key]["label"],
            "count": count,
            "share": count / len(negatives) if negatives else 0,
            "quotes": theme_quotes[key],
        }
        for key, count in theme_hits.most_common()
    ]

    by_version = collections.defaultdict(lambda: {"n": 0, "sum": 0, "neg": 0})
    for review in reviews:
        slot = by_version[review["version"] or "?"]
        slot["n"] += 1
        slot["sum"] += review["rating"]
        if review["rating"] <= NEGATIVE_MAX:
            slot["neg"] += 1
    versions = sorted(
        (
            {
                "version": version,
                "count": slot["n"],
                "average": slot["sum"] / slot["n"],
                "negative_share": slot["neg"] / slot["n"],
            }
            for version, slot in by_version.items()
        ),
        key=lambda v: _version_key(v["version"]),
        reverse=True,
    )

    markets = collections.Counter(r["country"] for r in reviews)
    return {
        "markets": [(c, n) for c, n in markets.most_common()],
        "total": len(reviews),
        "average": sum(r["rating"] for r in reviews) / len(reviews),
        "histogram": {k: hist.get(k, 0) for k in range(5, 0, -1)},
        "negative": len(negatives),
        "themes": themes,
        "by_version": versions[:8],
    }


def _trim(text, limit=160):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _version_key(version):
    return [int(p) if p.isdigit() else 0 for p in re.split(r"[^0-9]+", version or "0")[:4]]


def handoff_brief(app, summary):
    """Markdown bundle of the raw negative reviews, for a model to read.

    The deterministic buckets above catch the common themes; this file exists
    for the long tail they miss.
    """
    lines = [
        "# Yorum analizi için ham veri — %s" % app["name"],
        "",
        "Store: %s" % app.get("store_url"),
        "Sürüm: %s · Ortalama (son yorumlar): %s"
        % (app.get("version"), round(summary["average"], 2) if summary["average"] else "—"),
        "",
        "## Görev",
        "",
        "Aşağıdaki olumsuz yorumları oku. Deterministik kural setinin kaçırdığı",
        "temaları çıkar, her temayı tek cümlelik bir ürün maddesine çevir ve",
        "etkilenen yorum sayısına göre sırala. Tekrarları birleştir.",
        "",
        "## Kuralların bulduğu temalar",
        "",
    ]
    for theme in summary["themes"]:
        lines.append("- %s — %d yorum" % (theme["label"], theme["count"]))
    lines += ["", "## Olumsuz yorumlar (%d)" % summary["negative"], ""]
    for review in app["reviews"]:
        if review["rating"] > NEGATIVE_MAX:
            continue
        lines.append(
            "- **%d★ · v%s · %s** — %s"
            % (review["rating"], review["version"] or "?", review["country"].upper(),
               _trim("%s. %s" % (review["title"], review["body"]), 400))
        )
    return "\n".join(lines) + "\n"
