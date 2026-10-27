"""Universal Links / Smart App Banner verification.

This is the part of "mobile SEO" that is literally web SEO: whether the app's
own website hands visitors off to the app correctly. It breaks silently and
often, so it is worth checking on every run.
"""

import json
import re
import urllib.parse

from asolens import net
from asolens.aso import CRITICAL, INFO, OK, WARN, Finding

AASA_PATHS = (
    "/.well-known/apple-app-site-association",
    "/apple-app-site-association",
)


def domain_of(url):
    if not url:
        return None
    if "//" not in url:
        url = "https://" + url
    host = urllib.parse.urlparse(url).netloc.lower()
    return host.split(":")[0] or None


def host_variants(host):
    """Both the apex and the www form, because iOS fetches the exact host
    named in the entitlement and the two often differ in configuration."""
    if host.startswith("www."):
        return [host, host[4:]]
    return [host, "www." + host]


def looks_like_html(body):
    head = (body or "")[:400].lstrip().lower()
    return head.startswith("<!doctype html") or head.startswith("<html")


def check(app, ttl=3600):
    """Verify the app's marketing domain supports Universal Links."""
    out = []
    host = domain_of(app.get("seller_url"))
    if not host:
        return [Finding(
            "deeplink.domain", INFO, "Store kaydında geliştirici web sitesi yok",
            "Universal Links doğrulaması için alan adı gerekiyor.", 0)]

    out.append(Finding(
        "deeplink.domain", INFO, "Doğrulanan alan adı: %s" % host, "", 0, host))

    candidates = []
    for candidate_host in host_variants(host):
        for path in AASA_PATHS:
            candidates.append("https://%s%s" % (candidate_host, path))

    document, source = None, None
    html_served = []
    for url in candidates:
        try:
            body = net.get(url, ttl=ttl, ua=net.TOOL_UA)
        except net.FetchError:
            continue
        if looks_like_html(body):
            # A catch-all SPA route answering this path is the most common
            # real-world break: iOS requests the file and gets a web page.
            html_served.append(url)
            continue
        try:
            document = json.loads(body)
            source = url
            break
        except ValueError:
            out.append(Finding(
                "deeplink.aasa_json", CRITICAL,
                "Dosya bulundu ama geçerli JSON değil",
                "%s yanıt veriyor fakat içerik ayrıştırılamıyor. iOS dosyayı "
                "sessizce yok sayar; Universal Links hiç çalışmaz." % url,
                8, url))

    if html_served:
        out.append(Finding(
            "deeplink.aasa_html",
            WARN if document else CRITICAL,
            "%d adres AASA yerine HTML döndürüyor" % len(html_served),
            "Bu yollara bir catch-all web rotası yanıt veriyor: %s. iOS bu "
            "adreslerden JSON bekler; HTML gelirse o alan adı için Universal "
            "Links sessizce devre dışı kalır."
            % ", ".join(html_served),
            0 if document else 8, html_served))

    if document is None:
        out.append(Finding(
            "deeplink.aasa", CRITICAL,
            "apple-app-site-association dosyası bulunamadı",
            "Denenen adresler: %s. Bu dosya olmadan web linkleri app'i açmaz, "
            "kullanıcı tarayıcıda kalır — app'e giden en ucuz trafik kanalı "
            "kapalı." % ", ".join(candidates),
            10, candidates))
        out += _banner_check(host, app, ttl)
        return out

    out.append(Finding(
        "deeplink.aasa", OK, "apple-app-site-association erişilebilir",
        source, 10, source))

    applinks = document.get("applinks") or {}
    details = applinks.get("details")
    if isinstance(details, dict):
        details = [details]
    details = details or []
    if not details:
        out.append(Finding(
            "deeplink.details", CRITICAL, "applinks.details boş",
            "Dosya var ama hiçbir app eşleşmesi tanımlı değil.", 8, None))
        out += _banner_check(host, app, ttl)
        return out

    app_ids = []
    paths = []
    for detail in details:
        ids = detail.get("appIDs") or ([detail["appID"]] if detail.get("appID") else [])
        app_ids += ids
        paths += detail.get("paths") or []
        for component in detail.get("components") or []:
            if component.get("/"):
                paths.append(component["/"])

    bundle = app.get("bundle_id") or ""
    matched = [i for i in app_ids if bundle and i.endswith("." + bundle)]
    if matched:
        out.append(Finding(
            "deeplink.bundle", OK,
            "Bundle id dosyada tanımlı (%s)" % matched[0], "", 8, matched))
    else:
        out.append(Finding(
            "deeplink.bundle", CRITICAL,
            "Bundle id dosyada yok",
            "Dosyadaki app id'leri: %s. Beklenen son ek: %s"
            % (", ".join(app_ids) or "—", bundle), 8, app_ids))

    if not paths:
        out.append(Finding(
            "deeplink.paths", WARN, "Hiç path/component tanımlı değil",
            "Yol listesi boşsa hangi URL'lerin app'e gideceği belirsiz.", 4, None))
    else:
        wildcard_only = paths == ["*"] or paths == ["/*"]
        out.append(Finding(
            "deeplink.paths",
            INFO if wildcard_only else OK,
            "%d yol kuralı tanımlı" % len(paths),
            ("Tümü joker (*): her sayfa app'e yönlenir, web'de kalması gereken "
             "sayfalar da dahil." if wildcard_only
             else ", ".join(paths[:10]) + ("…" if len(paths) > 10 else "")),
            4, paths[:20]))

    out += _banner_check(host, app, ttl)
    return out


def _banner_check(host, app, ttl):
    """Smart App Banner is the mobile-web equivalent of a site-wide CTA."""
    try:
        html = net.get("https://%s/" % host, ttl=ttl)
    except net.FetchError:
        return [Finding(
            "deeplink.banner", INFO, "Site ana sayfası okunamadı",
            "Smart App Banner kontrolü yapılamadı.", 0, host)]
    match = re.search(
        r'<meta[^>]+name=["\']apple-itunes-app["\'][^>]*content=["\']([^"\']+)',
        html, re.I)
    if not match:
        return [Finding(
            "deeplink.banner", WARN, "Smart App Banner meta etiketi yok",
            "Tek satırlık <meta name=\"apple-itunes-app\" content=\"app-id=%s\"> "
            "etiketi, Safari'de siteyi açan herkese app bandı gösteriyor. "
            "Mobil web trafiğini app indirmesine çeviren en düşük maliyetli "
            "kanal." % app.get("id"), 5, None)]
    content = match.group(1)
    if app.get("id") and app["id"] not in content:
        return [Finding(
            "deeplink.banner", WARN, "Smart App Banner farklı bir app id gösteriyor",
            "Etikette: %s · beklenen app-id=%s" % (content, app["id"]), 5, content)]
    return [Finding(
        "deeplink.banner", OK, "Smart App Banner kurulu", content, 5, content)]
