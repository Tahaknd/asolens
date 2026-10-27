"""ASO metadata audit.

Each check returns a Finding. Findings carry a weight that is subtracted from
a 100-point score when the check does not pass, so the score is just
"how much known-fixable surface is left on the table".

Every threshold here is an App Store rule or a widely used ASO convention;
where a judgement call is unavoidable the finding is INFO and quotes the text
so a human decides instead of the tool pretending to know.
"""

import collections
import datetime
import re

CRITICAL = "critical"
WARN = "warn"
INFO = "info"
OK = "ok"

# App Store field limits (characters).
TITLE_MAX = 30
SUBTITLE_MAX = 30
DESCRIPTION_MAX = 4000
FOLD = 170  # description characters shown before "more"

SCREENSHOT_MAX = 10

GENERIC_NOTES = (
    "bug fixes and performance improvements",
    "bug fixes and stability improvements",
    "various bug fixes",
    "minor bug fixes",
    "performance improvements",
    "hata düzeltmeleri",
    "iyileştirmeler ve hata düzeltmeleri",
    "küçük hata düzeltmeleri",
)

BENEFIT_WORDS = (
    "free", "fast", "easy", "track", "save", "create", "find", "learn", "plan",
    "share", "manage", "discover", "built", "without", "offline", "secure",
    "ücretsiz", "hızlı", "kolay", "takip", "kaydet", "oluştur", "bul", "öğren",
    "planla", "paylaş", "yönet", "keşfet", "güvenli", "çevrimdışı",
)

STOPWORDS = set(
    """a an the and or of for to in on with your you app apps is are be can we
    our it its this that from by at as all more most new now get use using will
    ve veya ile için bir bu da de en çok daha her the app""".split()
)

TOKEN = re.compile(r"[0-9a-zğüşıöçĞÜŞİÖÇ]+", re.I)


class Finding:
    def __init__(self, check, severity, title, detail, weight=0, evidence=None):
        self.check = check
        self.severity = severity
        self.title = title
        self.detail = detail
        self.weight = weight
        self.evidence = evidence

    @property
    def lost(self):
        return 0 if self.severity == OK else self.weight

    def as_dict(self):
        return {
            "check": self.check,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "weight": self.weight,
            "lost": self.lost,
            "evidence": self.evidence,
        }


def tokens(text):
    return [t.lower() for t in TOKEN.findall(text or "")]


def content_tokens(text):
    return [t for t in tokens(text) if t not in STOPWORDS and len(t) > 2]


def _days_since(stamp):
    if not stamp:
        return None
    try:
        when = datetime.datetime.strptime(stamp[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return (datetime.datetime.utcnow() - when).days


def audit(app):
    """Run every check against an app profile from ios_store.fetch_app."""
    out = []
    out += _check_title(app)
    out += _check_subtitle(app)
    out += _check_description(app)
    out += _check_release(app)
    out += _check_creative(app)
    out += _check_reach(app)
    out += _check_ratings(app)
    return out


def score(findings):
    lost = sum(f.lost for f in findings)
    return max(0, 100 - lost)


def _check_title(app):
    name = (app.get("name") or "").strip()
    out = []
    if not name:
        return [Finding("title.present", CRITICAL, "Başlık okunamadı",
                        "Store kaydında app adı yok.", 10)]
    if len(name) > TITLE_MAX:
        out.append(Finding(
            "title.length", CRITICAL,
            "Başlık %d karakter, limit %d" % (len(name), TITLE_MAX),
            "Arama sonuçlarında ve ana ekranda kesilir. İlk 23 karaktere en "
            "önemli kelimeyi sığdır.", 8, name))
    else:
        out.append(Finding(
            "title.length", OK, "Başlık uzunluğu uygun (%d/%d)" % (len(name), TITLE_MAX),
            "Kesilme riski yok.", 8, name))

    words = [w for w in content_tokens(name)]
    if len(tokens(name)) <= 1:
        out.append(Finding(
            "title.keyword", WARN, "Başlıkta açıklayıcı kelime yok",
            "Başlık yalnızca marka adı. iOS'ta başlık en ağırlıklı sıralama "
            "alanı; 'Marka — ana kelime' kalıbı aramada belirgin fark yaratır.",
            6, name))
    else:
        out.append(Finding(
            "title.keyword", OK, "Başlıkta marka dışı kelime var",
            "Anahtar kelime yüzeyi: %s" % ", ".join(words), 6, name))
    return out


def _check_subtitle(app):
    sub = (app.get("subtitle") or "").strip()
    out = []
    if not sub:
        return [Finding(
            "subtitle.present", CRITICAL, "Subtitle boş",
            "30 karakterlik, başlıktan sonra en ağırlıklı ikinci indeksleme "
            "alanı tamamen kullanılmıyor.", 10)]
    if len(sub) > SUBTITLE_MAX:
        out.append(Finding(
            "subtitle.length", CRITICAL,
            "Subtitle %d karakter, limit %d" % (len(sub), SUBTITLE_MAX),
            "Kesilecek.", 6, sub))
    elif len(sub) < SUBTITLE_MAX * 0.6:
        out.append(Finding(
            "subtitle.length", WARN,
            "Subtitle'ın %d karakteri boş" % (SUBTITLE_MAX - len(sub)),
            "Kullanılmayan her karakter indekslenmeyen anahtar kelime demek.",
            4, sub))
    else:
        out.append(Finding(
            "subtitle.length", OK, "Subtitle alanı dolu (%d/%d)" % (len(sub), SUBTITLE_MAX),
            "", 4, sub))

    name_set = set(content_tokens(app.get("name")))
    overlap = sorted(name_set & set(content_tokens(sub)))
    if overlap:
        out.append(Finding(
            "subtitle.overlap", WARN,
            "Başlık ve subtitle aynı kelimeyi paylaşıyor: %s" % ", ".join(overlap),
            "Apple her kelimeyi bir kez indeksler. Tekrar eden kelime, ikinci "
            "alanda harcanmış yer.", 5, overlap))
    else:
        out.append(Finding(
            "subtitle.overlap", OK, "Başlık ve subtitle kelime tekrarı yok",
            "İki alan farklı anahtar kelime yüzeyi kaplıyor.", 5))
    return out


def _check_description(app):
    desc = (app.get("description") or "").strip()
    out = []
    if len(desc) < 300:
        out.append(Finding(
            "description.length", WARN, "Açıklama çok kısa (%d karakter)" % len(desc),
            "iOS'ta açıklama sıralamaya girmez ama dönüşüme girer; özellik ve "
            "kullanım senaryoları eksik.", 5, None))
    else:
        out.append(Finding(
            "description.length", OK,
            "Açıklama uzunluğu makul (%d/%d)" % (len(desc), DESCRIPTION_MAX), "", 5))

    fold = desc[:FOLD].replace("\n", " ").strip()
    has_benefit = any(w in fold.lower() for w in BENEFIT_WORDS)
    first_break = desc.find("\n")
    if not has_benefit:
        out.append(Finding(
            "description.hook", WARN,
            "'Daha fazla'dan önceki %d karakterde somut fayda ifadesi yok" % FOLD,
            "Kullanıcının genişletmeden gördüğü tek metin bu. Fayda cümlesiyle "
            "başlamak dönüşümü en çok etkileyen metin değişikliği.", 6, fold))
    else:
        out.append(Finding(
            "description.hook", OK, "Açıklamanın ilk bloğu fayda ifadesiyle açılıyor",
            "", 6, fold))
    if first_break == -1 or first_break > FOLD:
        out.append(Finding(
            "description.scannable", INFO,
            "İlk satır sonu %s" % ("yok" if first_break == -1 else "%d. karakterde" % first_break),
            "Fold içinde satır kırılması olmazsa metin tek blok görünür; kısa "
            "ilk satır okunurluğu artırır.", 2, None))

    counts = collections.Counter(content_tokens(desc))
    total = sum(counts.values()) or 1
    stuffed = [(w, c) for w, c in counts.most_common(8) if c >= 10 and c / total > 0.02]
    if stuffed:
        out.append(Finding(
            "description.stuffing", WARN,
            "Aşırı tekrar eden kelime: %s" % ", ".join("%s (%d)" % x for x in stuffed),
            "Apple açıklamayı indekslemediği için tekrarın ASO faydası yok, "
            "okunurluğu düşürüyor ve inceleme riski taşıyor.", 4, stuffed))
    else:
        out.append(Finding(
            "description.stuffing", OK, "Kelime tekrarı normal aralıkta",
            "En sık: %s" % ", ".join("%s (%d)" % x for x in counts.most_common(5)), 4))
    return out


def _check_release(app):
    notes = (app.get("release_notes") or "").strip()
    out = []
    lowered = notes.lower()
    if not notes:
        out.append(Finding(
            "release.notes", WARN, "Sürüm notu boş", "", 4))
    elif any(g in lowered for g in GENERIC_NOTES) and len(notes) < 160:
        out.append(Finding(
            "release.notes", WARN, "Sürüm notu şablon metin",
            "'Hata düzeltmeleri ve performans iyileştirmeleri' tipi not, "
            "güncellemeyi gören kullanıcıya hiçbir şey anlatmıyor. Düzelen "
            "şikâyeti adıyla yazmak yorum puanını doğrudan etkiliyor.",
            4, notes))
    else:
        out.append(Finding(
            "release.notes", OK, "Sürüm notu özgün", "", 4, notes[:200]))

    days = _days_since(app.get("version_released"))
    if days is None:
        out.append(Finding("release.cadence", INFO, "Son güncelleme tarihi okunamadı", "", 0))
    elif days > 180:
        out.append(Finding(
            "release.cadence", CRITICAL, "Son güncelleme %d gün önce" % days,
            "6 aydan eski app'ler terk edilmiş algılanıyor ve Apple'ın "
            "güncellik sinyalinde geriye düşüyor.", 8, days))
    elif days > 90:
        out.append(Finding(
            "release.cadence", WARN, "Son güncelleme %d gün önce" % days,
            "90 günü aşan aralıklar güncellik sinyalini zayıflatıyor.", 5, days))
    else:
        out.append(Finding(
            "release.cadence", OK, "Son güncelleme %d gün önce" % days, "", 5, days))
    return out


def _check_creative(app):
    shots = app.get("screenshots") or []
    ipad = app.get("ipad_screenshots") or []
    out = []
    if len(shots) == 0:
        out.append(Finding(
            "creative.count", CRITICAL, "iPhone ekran görüntüsü yok", "", 10))
    elif len(shots) < 3:
        out.append(Finding(
            "creative.count", CRITICAL, "Yalnızca %d ekran görüntüsü" % len(shots),
            "Arama sonucunda ilk 3 görsel yan yana görünür; eksik kalan yer "
            "doğrudan dönüşüm kaybı.", 8, len(shots)))
    elif len(shots) < 5:
        out.append(Finding(
            "creative.count", WARN, "%d ekran görüntüsü (üst sınır %d)" % (len(shots), SCREENSHOT_MAX),
            "Daha fazla görsel, daha fazla özellik anlatma alanı.", 4, len(shots)))
    else:
        out.append(Finding(
            "creative.count", OK, "%d ekran görüntüsü" % len(shots), "", 4, len(shots)))

    universal = "iosUniversal" in (app.get("features") or [])
    if universal and not ipad:
        out.append(Finding(
            "creative.ipad", WARN, "App iPad'i destekliyor ama iPad görseli yok",
            "iPad'de iPhone görselleri gösterilir, sayfa özensiz görünür.", 5, None))
    elif universal:
        out.append(Finding(
            "creative.ipad", OK, "iPad görsel seti var (%d)" % len(ipad), "", 5, len(ipad)))

    if not app.get("icon_url"):
        out.append(Finding("creative.icon", CRITICAL, "İkon bulunamadı", "", 5))
    return out


def _check_reach(app):
    out = []
    langs = app.get("languages") or []
    if len(langs) <= 1:
        out.append(Finding(
            "reach.localization", WARN, "Tek dilde yayında (%s)" % (", ".join(langs) or "?"),
            "Store metinlerini lokalize etmek, ürünü çevirmeden bile o dildeki "
            "aramalarda görünmeyi sağlıyor.", 6, langs))
    else:
        out.append(Finding(
            "reach.localization", OK, "%d dilde yayında" % len(langs),
            ", ".join(langs[:12]) + ("…" if len(langs) > 12 else ""), 6, langs))

    size_mb = (app.get("size_bytes") or 0) / 1048576.0
    if size_mb > 200:
        out.append(Finding(
            "reach.size", WARN, "Uygulama boyutu %.0f MB" % size_mb,
            "200 MB üstü indirmeler hücresel veride onay istiyor; ilk indirme "
            "dönüşümünü düşürüyor.", 4, round(size_mb)))
    elif size_mb:
        out.append(Finding(
            "reach.size", OK, "Uygulama boyutu %.0f MB" % size_mb, "", 4, round(size_mb)))

    if app.get("min_os"):
        out.append(Finding(
            "reach.min_os", INFO, "Minimum iOS %s" % app["min_os"],
            "Yüksek minimum sürüm erişilebilir cihaz tabanını daraltır.", 0,
            app["min_os"]))

    tracking = [t for t in (app.get("privacy_types") or [])
                if t.get("identifier") == "DATA_USED_TO_TRACK_YOU"]
    if tracking:
        cats = tracking[0].get("categories") or []
        out.append(Finding(
            "reach.privacy", INFO, "Gizlilik etiketinde 'takip' kategorisi var",
            "Takip edilen veri: %s. Sayfada görünen bu etiket bazı "
            "kategorilerde indirmeyi ölçülebilir biçimde düşürüyor."
            % (", ".join(cats) or "belirtilmemiş"), 0, cats))
    return out


def _check_ratings(app):
    out = []
    count = app.get("rating_count") or 0
    rating = app.get("rating") or 0
    hist = app.get("rating_counts")
    if count < 50:
        out.append(Finding(
            "ratings.volume", WARN, "Yalnızca %d oy" % count,
            "Düşük oy sayısı hem sıralamada hem dönüşümde dezavantaj. "
            "Uygulama içi puan isteme akışı (SKStoreReviewController) doğru "
            "anda tetiklenmiyor olabilir.", 6, count))
    else:
        out.append(Finding(
            "ratings.volume", OK, "%s oy, ortalama %.2f" % (f"{count:,}", rating),
            "", 6, count))

    if hist:
        total = sum(hist.values()) or 1
        one_share = hist.get(1, 0) / total
        if one_share > 0.25:
            sev, weight = CRITICAL, 8
        elif one_share > 0.15:
            sev, weight = WARN, 5
        else:
            sev, weight = OK, 5
        out.append(Finding(
            "ratings.one_star", sev,
            "1 yıldız oranı %%%.1f" % (one_share * 100),
            "Histogram: " + ", ".join("%d★ %s" % (k, f"{hist[k]:,}")
                                       for k in sorted(hist, reverse=True)),
            weight, hist))
    return out
