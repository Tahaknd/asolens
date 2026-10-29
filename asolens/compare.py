"""Competitor comparison and keyword-gap analysis.

The keyword gap is the single most actionable ASO output: words competitors put
in their indexed fields (title + subtitle) that you do not use at all.
"""

import collections

from asolens import aso, ios_store
from asolens.util import days_since, parallel_map



def row(app):
    return {
        "id": app["id"],
        "name": app["name"],
        "subtitle": app.get("subtitle") or "",
        "developer": app.get("developer"),
        "title_len": len(app.get("name") or ""),
        "subtitle_len": len(app.get("subtitle") or ""),
        "screenshots": len(app.get("screenshots") or []),
        "languages": len(app.get("languages") or []),
        "rating": app.get("rating"),
        "rating_count": app.get("rating_count"),
        "days_since_update": days_since(app.get("version_released")),
        "size_mb": round((app.get("size_bytes") or 0) / 1048576.0),
        "price": app.get("price"),
        "store_url": app.get("store_url"),
    }


def keyword_gap(target, competitors):
    """Words in competitors' indexed fields that the target never uses.

    Indexed surface on iOS is title + subtitle. The target's description is
    included on the "ours" side only to avoid suggesting words the team has
    clearly already considered and chosen to put elsewhere.
    """
    ours = set(aso.content_tokens(
        "%s %s" % (target.get("name") or "", target.get("subtitle") or "")))
    ours_anywhere = ours | set(aso.content_tokens(target.get("description") or ""))

    usage = collections.Counter()
    examples = collections.defaultdict(list)
    for competitor in competitors:
        surface = "%s %s" % (competitor.get("name") or "", competitor.get("subtitle") or "")
        for token in set(aso.content_tokens(surface)):
            usage[token] += 1
            if len(examples[token]) < 3:
                examples[token].append(competitor.get("name"))

    gaps = []
    for token, count in usage.most_common():
        if token in ours:
            continue
        gaps.append({
            "term": token,
            "competitors": count,
            "share": count / max(1, len(competitors)),
            "used_by": examples[token],
            "in_our_description": token in ours_anywhere,
        })
    shared = sorted(t for t in usage if t in ours)
    return {"gaps": gaps, "shared": shared, "our_surface": sorted(ours)}


def run(target, competitor_ids, country="us", ttl=3600):
    def fetch(app_id):
        try:
            # The comparison table needs listing fields only. A storefront
            # survey per competitor turned six rivals into 120 requests.
            return ios_store.fetch_app(
                app_id, country=country, ttl=ttl,
                with_reviews=False, with_localization=False), None
        except Exception as exc:  # a dead competitor id must not kill the run
            return None, {"id": app_id, "error": str(exc)}

    competitors, errors = [], []
    for app, error in parallel_map(fetch, competitor_ids):
        (errors if error else competitors).append(error or app)
    return {
        "rows": [row(target)] + [row(c) for c in competitors],
        "keyword_gap": keyword_gap(target, competitors),
        "errors": errors,
        "count": len(competitors),
    }
