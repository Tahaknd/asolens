"""Creative assets: download icon and screenshots, and prepare a vision brief.

Screenshot quality is where most store pages actually lose installs, and it is
the one thing a rule engine cannot judge. So the tool's job here is to fetch
the images and ask the right questions; a vision model (or a human) answers
them.
"""

import os
import re

from asolens import net

# The Lookup API returns a thumbnail URL with the size baked into the path.
SIZE_IN_URL = re.compile(r"/\d+x\d+bb")


def _full_size(url, size="1242x2688"):
    return SIZE_IN_URL.sub("/%sbb" % size, url)


def _extension(path):
    """Name the file after what it actually is.

    Apple serves these URLs with a .png path but the bytes are often JPEG, and
    a wrong extension breaks anything downstream that trusts it.
    """
    with open(path, "rb") as fh:
        head = fh.read(12)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None


def _retype(path):
    extension = _extension(path)
    if not extension or path.endswith(extension):
        return path
    corrected = os.path.splitext(path)[0] + extension
    os.replace(path, corrected)
    return corrected


def download(app, out_dir, limit=10):
    """Fetch the icon and up to `limit` iPhone screenshots."""
    saved = {"icon": None, "screenshots": [], "errors": []}
    shots_dir = os.path.join(out_dir, "screenshots")

    if app.get("icon_url"):
        try:
            saved["icon"] = _retype(net.download(
                app["icon_url"], os.path.join(out_dir, "icon.png")))
        except net.FetchError as exc:
            saved["errors"].append(str(exc))

    for index, url in enumerate((app.get("screenshots") or [])[:limit], start=1):
        dest = os.path.join(shots_dir, "%02d.png" % index)
        try:
            saved["screenshots"].append(_retype(net.download(_full_size(url), dest)))
        except net.FetchError as exc:
            saved["errors"].append(str(exc))
    return saved


BRIEF = """# Görsel denetim brifingi — {name}

Store: {store_url}
İkon: `{icon}`
Ekran görüntüleri: `{shots_dir}` ({count} dosya, mağazadaki sırayla)

## Görev

Görselleri sırayla incele. Her soruyu dosya adı vererek yanıtla; genel yorum
değil, değiştirilecek şeyin adresi lazım.

### İlk izlenim (yalnızca 01 ve 02)

Arama sonuçlarında kullanıcı yalnızca ilk iki görseli yan yana görür.

1. Sadece bu ikisine bakarak: app ne yapıyor? Tek cümleyle yaz.
2. Yanıtın mağaza açıklamasındaki vaatle örtüşüyor mu?
3. Metin, telefon boyutunda (yaklaşık 1/3 ölçek) okunabiliyor mu?

### Tüm set

4. Her görselde bir başlık metni var mı, yoksa çıplak ekran görüntüsü mü?
   Çıplak ekran görüntüleri dönüşümde ölçülebilir biçimde geride kalır.
5. Görseller bir sıra anlatıyor mu (sorun → çözüm → sonuç), yoksa rastgele
   ekran dizisi mi?
6. Cihaz çerçevesi güncel mi, yoksa eski model mi (çentik/dinamik ada)?
7. Metinler hangi dilde? Mağaza {languages} dilde yayında — görseller
   lokalize mi?
8. Boş durum, sahte veri veya placeholder ("Lorem", "Test", "John Doe")
   görünen görsel var mı?
9. Kontrast: açık renk zemin üstünde açık metin veya tersi var mı?
10. İkon: 60x60'a küçültüldüğünde ayırt edilebilir mi? Metin içeriyor mu
    (içeriyorsa o boyutta okunmaz)?

### Çıktı

Sonunda en fazla 5 maddelik, etkisine göre sıralı bir değişiklik listesi ver.
Her madde: hangi dosya, ne değişecek, neden.
"""


def vision_brief(app, saved, out_dir):
    path = os.path.join(out_dir, "vision-brief.md")
    text = BRIEF.format(
        name=app.get("name"),
        store_url=app.get("store_url"),
        icon=saved.get("icon") or "indirilemedi",
        shots_dir=os.path.join(out_dir, "screenshots"),
        count=len(saved.get("screenshots") or []),
        languages=len(app.get("languages") or []),
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path
