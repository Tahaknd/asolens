# asolens

***English** · [Türkçe](README.tr.md)*

[![tests](https://github.com/Tahaknd/asolens/actions/workflows/tests.yml/badge.svg)](https://github.com/Tahaknd/asolens/actions/workflows/tests.yml)

A local App Store Optimization auditor and iOS bundle checker. It looks at an
app from two sides:

- **`analyze`** — audits an App Store listing **from the outside**. Works on any
  public page, yours or a competitor's.
- **`crawl`** — audits a built `.app` bundle **from the inside**. Your own
  builds only.

No dependencies, no API keys, no account. Python 3.9+ and nothing else.

## Install

```bash
git clone https://github.com/Tahaknd/asolens.git
cd asolens
python3 -m asolens --help
```

Or install it as a command:

```bash
pip install -e .
asolens --help
```

## What ASO is, in web SEO terms

| Web SEO | Mobile equivalent | Checked |
|---|---|---|
| Title / meta description | App title (30 chars), subtitle (30 chars) | ✓ |
| Keywords | Hidden 100-character keywords field | ✗ — never published, no API exposes it |
| Backlink profile | Rating volume and velocity | ✓ |
| Content freshness | Update cadence, release notes | ✓ |
| CTR | Icon and screenshots | partly — downloaded, judgement left to a model |
| Core Web Vitals | App size, minimum iOS version | ✓ |
| Canonical / hreflang | Localization count | ✓ |
| Site ↔ app continuity | Universal Links, Smart App Banner | ✓ |

On iOS **only the title, the subtitle and the hidden keywords field feed
ranking.** The description is not indexed, so stuffing keywords into it buys
nothing — asolens flags that as a warning rather than an optimization.

## `analyze`

```bash
python3 -m asolens analyze "https://apps.apple.com/us/app/instagram/id389801252"
```

Accepts a store URL, an `id389801252` fragment, or a bare numeric id. The
country is read from the URL and can be overridden with `--country us`.

Written to `out/<id>-<country>/`:

| File | Contents |
|---|---|
| `report.html` | Single-file, self-contained report (light and dark) |
| `report.json` | With `--json`; for CI or your own scripts |
| `screenshots/` | Full-size images, in store order |
| `vision-brief.md` | Question set for handing the screenshots to a vision model |
| `reviews-brief.md` | Raw negative reviews plus the themes the rules found |

### What it checks

**Metadata** — title length and truncation risk, whether the title carries a
non-brand word, subtitle presence and fill rate, title/subtitle word overlap
(Apple indexes each word once, so a repeat is wasted surface), whether the 170
characters above the description fold carry a concrete benefit, keyword
stuffing.

**Release hygiene** — boilerplate release notes, days since the last update.

**Creative** — iPhone screenshot count (the first three appear side by side in
search results), a missing iPad set on an iPad-capable app, icon presence.

**Reach** — localization count, app size (over 200 MB prompts on cellular),
minimum iOS version, tracking categories in the privacy labels.

**Ratings** — rating volume, one-star share, full histogram.

**Review mining** — negative reviews are bucketed into 12 themes (crashes,
performance, login, pricing, ads, post-update regressions, onboarding,
notifications, missing features, localization, data loss, unanswered support)
with sample quotes and a per-version rating breakdown. No LLM involved;
`reviews-brief.md` is written for the long tail the rules miss.

**Universal Links and mobile web** — whether the developer domain serves
`apple-app-site-association`, whether it is valid JSON, whether the bundle id
appears in it, how many path rules exist, and whether a Smart App Banner meta
tag is installed. Both the apex and the `www.` variant are tried, and a
catch-all web route answering those paths with HTML is flagged separately —
that is the most common silent failure.

### Competitors

```bash
# use the store's own "You Might Also Like" shelf
python3 -m asolens analyze id389801252 --compare

# or your own list
python3 -m asolens analyze id389801252 --compare id447188370 id544007664
```

Alongside the comparison table you get a **keyword gap**: words that appear in
competitors' title or subtitle but nowhere in your indexed fields, ranked by
how many competitors use them. In practice this is the most directly
actionable thing the tool produces.

### Reviews

```bash
# 10 pages per country (~500 reviews), across three storefronts
python3 -m asolens analyze id389801252 \
  --review-pages 10 --review-country tr --review-country us --review-country de
```

Apple caps the review feed at 10 pages of 50 per country, so passing several
countries is the only way past a single market.

### Options

```
--no-reviews     skip reviews entirely (fast run)
--no-assets      do not download images
--fresh          bypass the cache
--json           also write report.json
--open           open the report in a browser
--out DIR        change the output directory
```

Responses are cached in `~/.cache/asolens` for an hour. The exit code is `1`
when a critical finding exists, `2` on bad input and `0` otherwise, so it can
gate CI.

## `cache`

Screenshot downloads go through the same cache as API responses, so it grows.

```bash
asolens cache              # location, entry count, total size, oldest entry
asolens cache --prune 7    # drop entries older than a week
asolens cache --clear      # empty it
```

## `crawl`

```bash
python3 -m asolens crawl ~/Library/Developer/Xcode/DerivedData/App-xyz/Build/Products/Debug-iphonesimulator/App.app
```

Reads `Info.plist`, the signed entitlements and the bundle layout. It catches:

- Placeholder or too-short permission usage strings (App Review rejects on these)
- A missing `PrivacyInfo.xcprivacy` (required for App Store submission)
- `NSAllowsArbitraryLoads` disabling the HTTPS requirement wholesale
- `UIFileSharingEnabled` left on, exposing the Documents folder
- No launch screen defined
- No associated domains — which, next to a custom URL scheme, means Universal
  Links were never set up
- A missing `ITSAppUsesNonExemptEncryption` (the key that stops TestFlight
  asking the encryption question on every upload)
- Localization count

Reading entitlements needs a signed build; on a Simulator build that check is
skipped and the tool says so.

### Simulator sweep (experimental)

```bash
xcrun simctl boot "iPhone 17 Pro"
python3 -m asolens crawl path/to/App.app --sweep --steps 8
```

Installs, launches and captures frames into `out/<app>/frames/`.

**Limitation:** this is a visual record of the launch flow, not a crawl.
`simctl` has no command that exposes the accessibility tree, so the tool
cannot know what it tapped. A real UI crawler needs either an XCUITest target
inside the app or Meta's `idb` (`idb ui describe-all`). If `idb` is installed,
asolens uses it automatically and records the element tree with each frame.

## What it deliberately does not do

- **It cannot look inside a competitor's app.** There is no legitimate route
  from a store URL to the binary; on iOS it is signed and account-bound.
  `crawl` is for your own builds.
- **It cannot read the hidden keywords field.** It is published nowhere. What a
  competitor targets can only be inferred from their title and subtitle, which
  is what the keyword gap table does.
- **It does not estimate rankings or downloads.** That data is proprietary and
  modelled; inventing a number seemed worse than leaving the gap.
- **It does not score creative quality.** A rule engine cannot judge it, so the
  tool downloads the images and hands them to a model or a human via
  `vision-brief.md`.
- **No Google Play yet.** The structure is platform-agnostic, but only the App
  Store client is written.

## Development

The test suite is stdlib `unittest` and never touches the network — every
fixture is built in `tests/support.py`.

```bash
python3 -m unittest discover -s tests -t .
```

CI runs the same command on Python 3.9, 3.11 and 3.13, and separately installs
the package to check the console script works.

## Layout

```
asolens/
  cli.py          command line
  net.py          cached HTTP
  ios_store.py    lookup API + page scrape + review feed
  aso.py          metadata rules and scoring
  reviews.py      theme mining
  deeplinks.py    Universal Links + Smart App Banner
  compare.py      competitor table + keyword gap
  assets.py       image download + vision brief
  report.py       console, HTML and JSON output
  crawl/
    ios_sim.py    .app static audit + Simulator sweep
tests/
  support.py      fixture builders shared by every suite
  test_*.py       the suites
  make_fixture.py builds a deliberately broken .app
```

Every rule returns a `Finding` carrying a severity, a title, a rationale,
evidence and a weight. The score is 100 minus the weights of the checks that
did not pass — meaning "how much known, fixable surface is still on the table",
not an absolute quality measure.

## Data sources

The public iTunes Lookup API, the public product page, and the public customer
reviews RSS feed. All unauthenticated, all rate-limited by caching.

## License

MIT
