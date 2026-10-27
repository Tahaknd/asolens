# asolens

*[English](README.md) · **Türkçe***

[![tests](https://github.com/Tahaknd/asolens/actions/workflows/tests.yml/badge.svg)](https://github.com/Tahaknd/asolens/actions/workflows/tests.yml)

Mobil uygulama analizi için yerel bir CLI. İki yönden bakar:

- **`analyze`** — bir App Store sayfasını **dışarıdan** denetler. Herkesin
  sayfası için çalışır: kendi app'in de, rakibin de.
- **`crawl`** — derlenmiş bir `.app` paketini **içeriden** denetler. Yalnızca
  kendi build'in için.

Bağımlılığı yok: Python 3.9+ yeterli, `pip install` gerekmiyor. API anahtarı
istemiyor.

## Kurulum

```bash
cd asolens
python3 -m asolens --help
```

## Mobilde SEO'nun karşılığı: ASO

| Web SEO | Mobil karşılığı | Araç bunu kontrol ediyor mu |
|---|---|---|
| Title / meta description | App title (30), subtitle (30) | ✓ |
| Keyword'ler | Gizli keywords alanı (100 karakter) | ✗ — sayfada görünmüyor, API vermiyor |
| Backlink profili | Oy sayısı, puan ivmesi | ✓ |
| İçerik tazeliği | Güncelleme sıklığı, sürüm notları | ✓ |
| CTR | İkon ve ekran görüntüleri | kısmen — görseller indirilir, yargı modele bırakılır |
| Core Web Vitals | Uygulama boyutu, min iOS sürümü | ✓ |
| Canonical / hreflang | Lokalizasyon sayısı | ✓ |
| Site ↔ app devamlılığı | Universal Links, Smart App Banner | ✓ |

iOS'ta **yalnızca başlık, subtitle ve gizli keywords alanı sıralamaya girer.**
Açıklama indekslenmez; o yüzden açıklamaya kelime doldurmanın ASO faydası yok,
araç bunu uyarı olarak işaretler.

## `analyze` — store sayfası denetimi

```bash
python3 -m asolens analyze "https://apps.apple.com/tr/app/instagram/id389801252"
```

URL yerine `id389801252` veya çıplak `389801252` de verebilirsin. Ülke
URL'den okunur, `--country tr` ile ezilir.

Üretilenler (`out/<id>-<ülke>/` altında):

| Dosya | İçerik |
|---|---|
| `report.html` | Tek dosyalık, bağımsız rapor (açık/koyu tema) |
| `report.json` | `--json` ile; CI veya kendi scriptin için |
| `screenshots/` | Mağazadaki sırayla, tam boyutlu görseller |
| `vision-brief.md` | Görselleri bir vision modeline verirken kullanılacak soru seti |
| `reviews-brief.md` | Olumsuz yorumların ham hali + kuralların bulduğu temalar |

### Ne denetliyor

**Metadata** — başlık uzunluğu ve kesilme riski, başlıkta marka dışı kelime
olup olmadığı, subtitle'ın varlığı ve doluluk oranı, başlık–subtitle kelime
tekrarı (Apple her kelimeyi bir kez indeksler, tekrar harcanmış yer),
açıklamanın "daha fazla" kırılımından önceki 170 karakterinde somut fayda
ifadesi olup olmadığı, kelime doldurma.

**Sürüm hijyeni** — şablon sürüm notu ("hata düzeltmeleri ve performans
iyileştirmeleri"), son güncellemeden geçen gün.

**Görseller** — iPhone görsel sayısı (arama sonucunda ilk 3 yan yana görünür),
iPad desteği varken iPad seti eksikliği, ikonun varlığı.

**Erişim** — lokalizasyon sayısı, uygulama boyutu (200 MB üstü hücresel veride
onay ister), minimum iOS sürümü, gizlilik etiketlerindeki takip kategorileri.

**Puanlar** — oy hacmi ve 1 yıldız oranı, tam histogram.

**Yorum madenciliği** — olumsuz yorumlar 12 temaya ayrılır (çökme, yavaşlık,
giriş, fiyat, reklam, güncelleme sonrası bozulma, kurulum, bildirim, eksik
özellik, dil, veri kaybı, destek), her tema için örnek alıntılar ve sürüme göre
ortalama puan kırılımı verilir. LLM kullanılmaz; kuralların kaçırdığı uzun
kuyruk için `reviews-brief.md` yazılır.

**Universal Links ve mobil web** — geliştirici alan adında
`apple-app-site-association` var mı, geçerli JSON mu, bundle id dosyada tanımlı
mı, kaç yol kuralı var, Smart App Banner meta etiketi kurulu mu. Hem apex hem
`www.` varyantı denenir; catch-all bir web rotası bu yola HTML döndürüyorsa
ayrıca işaretlenir — en sık rastlanan sessiz arıza bu.

### Rakip karşılaştırması

```bash
# mağazanın "Benzer" bölümünü otomatik kullan
python3 -m asolens analyze id389801252 --compare

# kendi listenle
python3 -m asolens analyze id389801252 --compare id447188370 id544007664
```

Karşılaştırma tablosunun yanında **anahtar kelime boşluğu** çıkar: rakiplerin
başlık veya subtitle alanında geçip sizin indekslenen alanlarınızda geçmeyen
kelimeler, kaç rakipte geçtiğine göre sıralı. Pratikte aracın en doğrudan
kullanılabilir çıktısı bu.

### Yorumlar

```bash
# ülke başına 10 sayfa (≈500 yorum), üç ülkeden
python3 -m asolens analyze id389801252 \
  --review-pages 10 --review-country tr --review-country us --review-country de
```

Apple yorum feed'ini ülke başına 10 sayfa × 50 yorumla sınırlıyor. Birden çok
ülke vermek, tek bir pazarın ötesine geçmenin tek yolu.

### Diğer seçenekler

```
--no-reviews     yorumları hiç çekme (hızlı koşu)
--no-assets      görselleri indirme
--fresh          önbelleği atla
--json           report.json da yaz
--open           raporu tarayıcıda aç
--out DIZIN      çıktı dizinini değiştir
```

Yanıtlar `~/.cache/asolens` altında 1 saat önbelleklenir. Çıkış kodu kritik
bulgu varsa `1`, hatalı girdide `2`, temizse `0` — CI'da eşik olarak
kullanılabilir.

## `cache` — önbellek yönetimi

Ekran görüntüleri de API yanıtlarıyla aynı önbellekten geçtiği için klasör
zamanla büyüyor.

```bash
asolens cache              # konum, girdi sayısı, boyut, en eski girdi
asolens cache --prune 7    # bir haftadan eski girdileri at
asolens cache --clear      # tamamen boşalt
```

## `crawl` — paket denetimi

```bash
python3 -m asolens crawl ~/Library/Developer/Xcode/DerivedData/App-xyz/Build/Products/Debug-iphonesimulator/App.app
```

`Info.plist`, imzalı entitlement'lar ve paket düzenini okur. Yakaladıkları:

- Şablon veya fazla kısa izin açıklamaları (App Review bu metinler yüzünden
  red veriyor)
- `PrivacyInfo.xcprivacy` eksikliği (App Store yüklemesinde zorunlu)
- `NSAllowsArbitraryLoads` ile kapatılmış HTTPS zorunluluğu
- `UIFileSharingEnabled` açık bırakılmış Documents klasörü
- Tanımsız açılış ekranı
- Associated domains eksikliği — özel URL şeması varken bu, Universal Links'in
  hiç kurulmadığı anlamına geliyor
- Eksik `ITSAppUsesNonExemptEncryption` (her TestFlight yüklemesinde şifreleme
  sorusunu tekrar sorduran şey)
- Dil paketi sayısı

Entitlement okuması imzalı build gerektirir; Simulator derlemesinde o kontrol
atlanır ve bunu açıkça söyler.

### Simulator sweep (deneysel)

```bash
xcrun simctl boot "iPhone 17 Pro"
python3 -m asolens crawl path/to/App.app --sweep --steps 8
```

Kurar, başlatır ve `out/<app>/frames/` altına kare kare ekran görüntüsü alır.

**Sınır:** bu bir gezinme değil, açılış akışının görsel kaydı. `simctl`'in
erişilebilirlik ağacını veren bir komutu yok, yani araç neye dokunduğunu
bilemez. Gerçek bir UI gezgini için iki yoldan biri gerekiyor: app içinde bir
XCUITest hedefi, ya da kurulu bir `idb` (`idb ui describe-all`). `idb` varsa
araç onu kendiliğinden kullanır ve erişilebilirlik ağacını kaydeder.

## Yapamadıkları

Dürüst olmak gerekirse:

- **Rakip app'in içine giremez.** Store URL'inden binary'ye ulaşmanın meşru bir
  yolu yok; iOS'ta imzalı ve hesaba bağlı. `crawl` yalnızca kendi build'in için.
- **Gizli keywords alanını okuyamaz.** Hiçbir yerde yayınlanmıyor. Rakibin
  hedeflediği kelimeler ancak başlık + subtitle'dan ve anahtar kelime boşluğu
  tablosundan çıkarsanabilir.
- **Sıralama ve indirme tahmini vermez.** O veri ücretli ASO servislerinde ve
  tahmine dayalı; burada uydurulmuş sayı üretmemeyi tercih ettim.
- **Görsel kalitesine puan vermez.** Kural motoru bunu ölçemez; görselleri
  indirip `vision-brief.md` ile birlikte bir modele veya insana bırakır.
- **Google Play desteklemiyor.** Yapı platform-agnostik ama şu an yalnızca
  App Store istemcisi yazılı.

## Geliştirme

Testler stdlib `unittest` ile yazıldı ve hiçbiri ağa çıkmıyor — bütün veri
`tests/support.py` içinde kuruluyor.

```bash
python3 -m unittest discover -s tests -t .
```

CI aynı komutu Python 3.9, 3.11 ve 3.13 üzerinde çalıştırıyor; ayrı bir iş de
paketi kurup konsol komutunun çalıştığını doğruluyor.

## Yapı

```
asolens/
  cli.py          komut satırı
  net.py          önbellekli HTTP
  ios_store.py    lookup API + sayfa scrape + yorum feed'i
  aso.py          metadata denetim kuralları ve puanlama
  reviews.py      tema madenciliği
  deeplinks.py    Universal Links + Smart App Banner
  compare.py      rakip tablosu + anahtar kelime boşluğu
  assets.py       görsel indirme + vision brifingi
  report.py       konsol + HTML + JSON çıktı
  crawl/
    ios_sim.py    .app statik denetimi + Simulator sweep
tests/
  support.py      tüm testlerin paylaştığı veri üreticileri
  test_*.py       test dosyaları
  make_fixture.py bilinçli bozuk bir .app üretir
```

Her denetim kuralı bir `Finding` döndürür: önem derecesi, başlık, gerekçe,
kanıt ve bir ağırlık. Puan, 100'den geçemeyen kontrollerin ağırlıklarının
düşülmesiyle bulunur — yani "bilinen ve düzeltilebilir ne kadar yer boş kalmış"
demek, mutlak bir kalite ölçüsü değil.
