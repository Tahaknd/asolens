"""Command line entry point."""

import argparse
import os
import platform
import sys
import webbrowser

from asolens import (
    __version__, aso, assets, compare, deeplinks, ios_store, net, report, reviews)
from asolens.aso import CRITICAL, WARN
from asolens.util import human_size, wrap


def build_parser():
    parser = argparse.ArgumentParser(
        prog="asolens",
        description="Mobil uygulama analiz aracı — ASO denetimi ve paket denetimi.",
    )
    parser.add_argument(
        "--version", action="version",
        version="asolens %s (Python %s)" % (__version__, platform.python_version()))
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze", help="Bir App Store sayfasını dışarıdan analiz et")
    analyze.add_argument("target", help="App Store URL'i, id123456 veya çıplak id")
    analyze.add_argument("--country", "-c", default=None,
                         help="Mağaza ülkesi (varsayılan: URL'den, yoksa us)")
    analyze.add_argument("--review-country", action="append", default=[],
                         metavar="KOD",
                         help="Yorum çekilecek ülkeyi elle belirle; birden çok "
                              "kez verilebilir. Verilmezse en çok oy alan "
                              "mağazalar otomatik seçilir.")
    analyze.add_argument("--review-markets", type=int, default=3, metavar="N",
                         help="Otomatik seçimde kaç mağazadan yorum okunacak "
                              "(varsayılan 3)")
    analyze.add_argument("--no-localization", action="store_true",
                         help="Mağaza taramasını atla (daha hızlı, ama yorumlar "
                              "yalnızca --country mağazasından okunur)")
    analyze.add_argument("--review-pages", type=int, default=4, metavar="N",
                         help="Ülke başına yorum sayfası, 50 yorum/sayfa (varsayılan 4, üst sınır 10)")
    analyze.add_argument("--compare", nargs="*", default=None, metavar="APP",
                         help="Rakip URL/id listesi; boş verilirse mağazanın "
                              "önerdiği benzer app'ler kullanılır")
    analyze.add_argument("--no-reviews", action="store_true")
    analyze.add_argument("--no-assets", action="store_true",
                         help="Ekran görüntülerini indirme")
    analyze.add_argument("--out", "-o", default=None, help="Çıktı dizini")
    analyze.add_argument("--json", action="store_true", help="report.json da yaz")
    analyze.add_argument("--fresh", action="store_true", help="Önbelleği atla")
    analyze.add_argument("--open", action="store_true", help="Raporu tarayıcıda aç")
    analyze.add_argument("--no-color", action="store_true")

    crawl = subparsers.add_parser(
        "crawl", help="Derlenmiş bir .app paketini içeriden denetle")
    crawl.add_argument("app_path", help=".app paketinin yolu")
    crawl.add_argument("--sweep", action="store_true",
                       help="Simulator'da başlat ve ekran görüntüsü al (deneysel)")
    crawl.add_argument("--device", default=None, help="Simulator adı veya UDID")
    crawl.add_argument("--steps", type=int, default=6)
    crawl.add_argument("--out", "-o", default=None)
    crawl.add_argument("--no-color", action="store_true")

    cache = subparsers.add_parser(
        "cache", help="Önbelleği görüntüle veya temizle")
    cache.add_argument("--clear", action="store_true",
                       help="Tüm önbelleği sil")
    cache.add_argument("--prune", type=float, metavar="GÜN",
                       help="Yalnızca bu günden eski girdileri sil")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "analyze":
        return cmd_analyze(args)
    if args.command == "cache":
        return cmd_cache(args)
    return cmd_crawl(args)


def cmd_cache(args):
    if args.clear or args.prune is not None:
        removed, freed = net.cache_clear(
            None if args.clear else args.prune)
        print("  %d girdi silindi, %s boşaldı." % (removed, human_size(freed)))
        if args.clear and args.prune is not None:
            print("  (--clear verildiği için --prune yok sayıldı.)")
        return 0

    stats = net.cache_stats()
    print("")
    print("  Konum : %s" % net.CACHE_DIR)
    print("  Girdi : %d" % stats["entries"])
    print("  Boyut : %s" % human_size(stats["bytes"]))
    print("  En eski: %s" % (
        "%s gün" % stats["oldest_days"] if stats["oldest_days"] is not None else "—"))
    print("")
    print("  Temizlemek için: asolens cache --clear")
    print("  Eskileri atmak için: asolens cache --prune 7")
    print("")
    return 0


def cmd_analyze(args):
    try:
        app_id, url_country = ios_store.parse_url(args.target)
    except ValueError as exc:
        print("Hata: %s" % exc, file=sys.stderr)
        return 2

    country = (args.country or url_country or "us").lower()
    ttl = 0 if args.fresh else 3600
    review_pages = max(1, min(10, args.review_pages))

    out_dir = args.out or os.path.join("out", "%s-%s" % (app_id, country))
    os.makedirs(out_dir, exist_ok=True)

    print("· %s mağazasından app %s çekiliyor…" % (country.upper(), app_id))
    try:
        app = ios_store.fetch_app(
            app_id,
            country=country,
            review_countries=args.review_country,
            review_pages=review_pages,
            ttl=ttl,
            with_reviews=not args.no_reviews,
            with_localization=not args.no_localization,
            review_markets=max(1, args.review_markets),
        )
    except Exception as exc:
        print("Hata: %s" % exc, file=sys.stderr)
        return 1

    findings = aso.audit(app)
    result = {
        "app": app,
        "findings": findings,
        "score": aso.score(findings),
        "reviews": None,
        "comparison": None,
        "deeplinks": None,
        "assets": None,
    }

    markets = app.get("review_markets") or [country]
    if not args.no_reviews and not app["reviews"]:
        # Silence here reads as "reviews were skipped" rather than "none
        # exist", which is the difference between a gap and a finding.
        print("· %s mağazasında yazılı yorum bulunamadı." % (
            "/".join(c.upper() for c in markets)))
    if app["reviews"]:
        print("· %s mağazasından %d yorum analiz ediliyor…" % (
            "/".join(c.upper() for c in markets), len(app["reviews"])))
        result["reviews"] = reviews.summarize(app["reviews"])
        brief = os.path.join(out_dir, "reviews-brief.md")
        with open(brief, "w", encoding="utf-8") as fh:
            fh.write(reviews.handoff_brief(app, result["reviews"]))

    for failure in app.get("review_errors") or []:
        print("  ! %s yorumları %d. sayfada kesildi, örneklem eksik: %s" % (
            failure["country"].upper(), failure["page"], failure["error"]))

    print("· Universal Links doğrulanıyor…")
    result["deeplinks"] = deeplinks.check(app, ttl=ttl)

    if args.compare is not None:
        ids = []
        for value in args.compare:
            try:
                ids.append(ios_store.parse_url(value)[0])
            except ValueError:
                print("  ! atlandı: %s" % value, file=sys.stderr)
        if not ids:
            ids = [a["id"] for a in app["similar_apps"][:6]]
            if not ids:
                print("· Karşılaştırılacak benzer app bulunamadı%s."
                      % (" (ürün sayfası okunamadı)"
                         if app.get("page_data_ok") is False else ""))
            else:
                print("· Mağazanın önerdiği %d benzer app karşılaştırılıyor…"
                      % len(ids))
        else:
            print("· %d rakip karşılaştırılıyor…" % len(ids))
        if ids:
            result["comparison"] = compare.run(app, ids, country=country, ttl=ttl)

    if not args.no_assets:
        print("· Görseller indiriliyor…")
        saved = assets.download(app, out_dir)
        result["assets"] = saved
        assets.vision_brief(app, saved, out_dir)

    html_path = report.html_report(result, out_dir)
    result["html_path"] = html_path
    if args.json:
        report.json_report(result, out_dir)

    print(report.console(result, color=not args.no_color))
    if args.open:
        webbrowser.open("file://" + os.path.abspath(html_path))

    blocking = sum(1 for f in findings + (result["deeplinks"] or [])
                   if f.severity == CRITICAL)
    return 1 if blocking else 0


def cmd_crawl(args):
    from asolens import crawl

    out_dir = args.out or os.path.join(
        "out", os.path.basename(args.app_path.rstrip("/")))
    os.makedirs(out_dir, exist_ok=True)

    try:
        info, findings = crawl.static_audit(args.app_path)
    except (FileNotFoundError, OSError) as exc:
        print("Hata: %s" % exc, file=sys.stderr)
        return 2

    print("")
    print("  %s · %s" % (info["name"] or "?", info["bundle_id"]))
    print("  v%s (%s) · min iOS %s · %s" % (
        info["version"], info["build"], info["min_os"],
        human_size(info["size_bytes"])))
    print("")

    glyph = {CRITICAL: "✗", WARN: "!", "info": "·", "ok": "✓"}
    for finding in sorted(findings, key=lambda f: report.SEV_ORDER[f.severity]):
        print("  %s %s" % (glyph.get(finding.severity, "·"), finding.title))
        if finding.detail and finding.severity in (CRITICAL, WARN):
            for chunk in wrap(finding.detail, 72):
                print("      %s" % chunk)
    print("")

    if args.sweep:
        print("  Simulator sweep başlatılıyor (deneysel)…")
        try:
            sweep = crawl.dynamic_sweep(
                args.app_path, out_dir, device=args.device, steps=args.steps)
        except RuntimeError as exc:
            print("  ! %s" % exc, file=sys.stderr)
            return 1
        print("  %d kare alındı → %s" % (
            len(sweep["frames"]), os.path.join(out_dir, "frames")))
        if not sweep["has_accessibility"]:
            print("  ! Erişilebilirlik ağacı okunamadı (idb kurulu değil).")
        print("  %s" % sweep["note"])
        print("")

    return 1 if any(f.severity == CRITICAL for f in findings) else 0
