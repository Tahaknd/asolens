"""Console summary and a self-contained HTML report."""

import datetime
import html
import json
import os

from asolens.aso import CRITICAL, INFO, OK, WARN

SEV_ORDER = {CRITICAL: 0, WARN: 1, INFO: 2, OK: 3}
SEV_LABEL = {CRITICAL: "KRİTİK", WARN: "UYARI", INFO: "BİLGİ", OK: "TAMAM"}
SEV_GLYPH = {CRITICAL: "✗", WARN: "!", INFO: "·", OK: "✓"}
ANSI = {CRITICAL: "\033[31m", WARN: "\033[33m", INFO: "\033[36m", OK: "\033[32m"}
RESET = "\033[0m"


# --------------------------------------------------------------------- console

def console(result, color=True):
    app = result["app"]
    lines = []

    def paint(text, severity):
        if not color:
            return text
        return "%s%s%s" % (ANSI[severity], text, RESET)

    lines.append("")
    lines.append("  %s%s" % (app["name"], " — " + app["subtitle"] if app["subtitle"] else ""))
    lines.append("  %s · v%s · %s · %s oy, ortalama %s" % (
        app["developer"], app["version"], app["price"],
        f"{app['rating_count']:,}", round(app["rating"] or 0, 2)))
    lines.append("")
    lines.append("  ASO puanı: %d/100   (%d kritik, %d uyarı)" % (
        result["score"],
        sum(1 for f in result["findings"] if f.severity == CRITICAL),
        sum(1 for f in result["findings"] if f.severity == WARN)))
    lines.append("")

    def emit(findings):
        for finding in sorted(findings, key=lambda f: SEV_ORDER[f.severity]):
            if finding.severity == OK:
                continue
            lines.append("  %s %s" % (
                paint(SEV_GLYPH[finding.severity], finding.severity), finding.title))
            if finding.detail:
                for chunk in _wrap(finding.detail, 72):
                    lines.append("      %s" % chunk)
            lines.append("")

    emit(result["findings"])

    if result.get("deeplinks"):
        lines.append("  Universal Links ve mobil web")
        lines.append("")
        emit(result["deeplinks"])

    summary = result.get("reviews")
    if summary and summary["total"]:
        lines.append("  Yorum temaları (%d olumsuz / %d yorum)" % (
            summary["negative"], summary["total"]))
        for theme in summary["themes"][:6]:
            bar = "█" * max(1, int(theme["share"] * 24))
            lines.append("    %-26s %-24s %3d" % (theme["label"], bar, theme["count"]))
        lines.append("")

    gap = (result.get("comparison") or {}).get("keyword_gap")
    if gap and gap["gaps"]:
        lines.append("  Rakiplerde olup sizde olmayan kelimeler")
        for item in gap["gaps"][:8]:
            lines.append("    %-20s %d rakip%s" % (
                item["term"], item["competitors"],
                "  (açıklamanızda var)" if item["in_our_description"] else ""))
        lines.append("")

    ok_count = sum(1 for f in result["findings"] + (result.get("deeplinks") or [])
                   if f.severity == OK)
    lines.append("  %d kontrol sorunsuz geçti." % ok_count)
    if result.get("html_path"):
        lines.append("  Rapor: %s" % result["html_path"])
    lines.append("")
    return "\n".join(lines)


def _wrap(text, width):
    words, line, out = text.split(), "", []
    for word in words:
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        out.append(line)
    return out


# ------------------------------------------------------------------------ html

CSS = """
:root {
  color-scheme: light dark;
  --bg: #fbfbfa; --panel: #ffffff; --ink: #1a1a19; --muted: #6b6b68;
  --line: #e5e4e1; --accent: #2f6f5b;
  --critical: #b4361f; --warn: #a56a00; --info: #3a6089; --ok: #2f6f5b;
  --critical-bg: #fdecea; --warn-bg: #fdf4e3; --info-bg: #eef3f9; --ok-bg: #ecf3f0;
  --radius: 10px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #16181a; --panel: #1e2124; --ink: #e8e8e6; --muted: #9a9a96;
    --line: #2e3236; --accent: #6fbfa3;
    --critical: #ef8a74; --warn: #e0b35e; --info: #86b0d8; --ok: #6fbfa3;
    --critical-bg: #2c1e1b; --warn-bg: #2a2418; --info-bg: #1c2530; --ok-bg: #1b2724;
  }
}
:root[data-theme="dark"] {
  --bg: #16181a; --panel: #1e2124; --ink: #e8e8e6; --muted: #9a9a96;
  --line: #2e3236; --accent: #6fbfa3;
  --critical: #ef8a74; --warn: #e0b35e; --info: #86b0d8; --ok: #6fbfa3;
  --critical-bg: #2c1e1b; --warn-bg: #2a2418; --info-bg: #1c2530; --ok-bg: #1b2724;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.6 ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 920px; margin: 0 auto; padding: 40px 16px 80px; }
header { display: flex; gap: 20px; align-items: center; margin-bottom: 8px; }
header img { width: 84px; height: 84px; border-radius: 19px; border: 1px solid var(--line); }
h1 { font-size: 26px; margin: 0 0 2px; letter-spacing: -0.01em; }
.sub { color: var(--muted); font-size: 15px; }
.meta { color: var(--muted); font-size: 13px; margin-top: 4px; }
a { color: var(--accent); }
.score { margin-left: auto; text-align: center; flex-shrink: 0; }
.score b { display: block; font-size: 40px; line-height: 1; letter-spacing: -0.03em; }
.score span { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .09em;
     color: var(--muted); margin: 44px 0 14px; font-weight: 600; }
.card { background: var(--panel); border: 1px solid var(--line);
        border-radius: var(--radius); padding: 16px 18px; margin-bottom: 10px; }
.f { display: flex; gap: 12px; }
.f .tag { font-size: 10px; font-weight: 700; letter-spacing: .06em; padding: 3px 7px;
          border-radius: 5px; height: fit-content; flex-shrink: 0; margin-top: 2px; }
.critical .tag { background: var(--critical-bg); color: var(--critical); }
.warn .tag { background: var(--warn-bg); color: var(--warn); }
.info .tag { background: var(--info-bg); color: var(--info); }
.ok .tag { background: var(--ok-bg); color: var(--ok); }
.f h3 { margin: 0 0 3px; font-size: 15px; font-weight: 600; }
.f p { margin: 0; color: var(--muted); font-size: 14px; }
.f code { font-size: 12.5px; background: var(--bg); border: 1px solid var(--line);
          padding: 1px 5px; border-radius: 4px; }
.ev { margin-top: 8px; font-size: 13px; color: var(--muted);
      border-left: 2px solid var(--line); padding-left: 10px; white-space: pre-wrap; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 600; font-size: 11.5px;
     text-transform: uppercase; letter-spacing: .05em; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
tr.me td { font-weight: 600; }
tr.me td:first-child::before { content: "▸ "; color: var(--accent); }
.bar { height: 7px; border-radius: 4px; background: var(--accent); min-width: 3px; }
.track { background: var(--line); border-radius: 4px; height: 7px; }
.quote { font-size: 13px; color: var(--muted); margin: 5px 0 0; padding-left: 10px;
         border-left: 2px solid var(--line); }
.shots { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 8px; }
.shots img { height: 300px; border-radius: 10px; border: 1px solid var(--line); }
footer { margin-top: 56px; color: var(--muted); font-size: 12.5px;
         border-top: 1px solid var(--line); padding-top: 16px; }
@media (max-width: 640px) {
  header { flex-wrap: wrap; gap: 14px; }
  .score { margin-left: 0; text-align: left; }
  header img { width: 64px; height: 64px; border-radius: 14px; }
  .shots img { height: 220px; }
}
"""


def _esc(value):
    return html.escape(str(value if value is not None else ""))


def _finding_html(finding):
    evidence = ""
    if finding.evidence and finding.severity != OK:
        text = finding.evidence
        if isinstance(text, (list, tuple)):
            text = ", ".join(str(t) for t in text)
        evidence = '<div class="ev">%s</div>' % _esc(text)[:600]
    return (
        '<div class="card f %s"><span class="tag">%s</span><div>'
        "<h3>%s</h3>%s%s</div></div>"
    ) % (
        finding.severity, SEV_LABEL[finding.severity], _esc(finding.title),
        "<p>%s</p>" % _esc(finding.detail) if finding.detail else "", evidence,
    )


def _histogram(hist):
    if not hist:
        return ""
    total = sum(hist.values()) or 1
    rows = []
    for star in sorted(hist, reverse=True):
        share = hist[star] / total
        rows.append(
            '<tr><td style="width:46px">%d★</td>'
            '<td><div class="track"><div class="bar" style="width:%.1f%%"></div></div></td>'
            '<td class="n" style="width:110px">%s</td>'
            '<td class="n" style="width:62px">%%%.1f</td></tr>'
            % (star, share * 100, f"{hist[star]:,}", share * 100))
    return '<div class="card"><table>%s</table></div>' % "".join(rows)


def _themes(summary):
    if not summary or not summary["themes"]:
        return ""
    parts = ['<div class="card"><table><tr><th>Tema</th><th>Pay</th>'
             '<th class="n">Yorum</th></tr>']
    for theme in summary["themes"]:
        parts.append(
            '<tr><td>%s</td><td><div class="track"><div class="bar" '
            'style="width:%.1f%%"></div></div></td><td class="n">%d</td></tr>'
            % (_esc(theme["label"]), theme["share"] * 100, theme["count"]))
    parts.append("</table></div>")
    for theme in summary["themes"][:5]:
        if not theme["quotes"]:
            continue
        parts.append('<div class="card"><h3 style="margin:0 0 6px;font-size:14px">%s</h3>'
                     % _esc(theme["label"]))
        for quote in theme["quotes"]:
            parts.append('<p class="quote">%d★ · v%s · %s — %s</p>' % (
                quote["rating"], _esc(quote["version"]),
                _esc(quote["country"].upper()), _esc(quote["text"])))
        parts.append("</div>")
    return "".join(parts)


def _versions(summary):
    if not summary or not summary["by_version"]:
        return ""
    rows = ['<div class="card"><table><tr><th>Sürüm</th><th class="n">Yorum</th>'
            '<th class="n">Ortalama</th><th class="n">Olumsuz</th></tr>']
    for item in summary["by_version"]:
        rows.append('<tr><td>%s</td><td class="n">%d</td><td class="n">%.2f</td>'
                    '<td class="n">%%%.0f</td></tr>'
                    % (_esc(item["version"]), item["count"], item["average"],
                       item["negative_share"] * 100))
    rows.append("</table></div>")
    return "".join(rows)


def _comparison(comparison):
    if not comparison or not comparison["rows"]:
        return ""
    head = ("<tr><th>App</th><th>Subtitle</th><th class='n'>Puan</th>"
            "<th class='n'>Oy</th><th class='n'>Görsel</th><th class='n'>Dil</th>"
            "<th class='n'>Son gün.</th></tr>")
    rows = []
    for index, item in enumerate(comparison["rows"]):
        rows.append(
            "<tr class='%s'><td>%s</td><td>%s</td><td class='n'>%s</td>"
            "<td class='n'>%s</td><td class='n'>%d</td><td class='n'>%d</td>"
            "<td class='n'>%s</td></tr>" % (
                "me" if index == 0 else "",
                _esc(item["name"]), _esc(item["subtitle"] or "—"),
                round(item["rating"] or 0, 2), f"{item['rating_count'] or 0:,}",
                item["screenshots"], item["languages"],
                "%dg" % item["days_since_update"] if item["days_since_update"] is not None else "—"))
    out = '<div class="card"><table>%s%s</table></div>' % (head, "".join(rows))

    gap = comparison["keyword_gap"]["gaps"]
    if gap:
        grows = ["<tr><th>Kelime</th><th class='n'>Kaç rakipte</th>"
                 "<th>Kullananlar</th><th>Durum</th></tr>"]
        for item in gap[:20]:
            grows.append(
                "<tr><td><b>%s</b></td><td class='n'>%d</td><td>%s</td><td>%s</td></tr>"
                % (_esc(item["term"]), item["competitors"],
                   _esc(", ".join(item["used_by"])),
                   "açıklamada var, indekslenen alanda yok"
                   if item["in_our_description"] else "hiç kullanılmıyor"))
        out += ('<h2>Anahtar kelime boşluğu</h2>'
                '<div class="card"><p style="margin:0 0 12px;color:var(--muted);'
                'font-size:14px">Rakiplerin başlık veya subtitle alanında geçip '
                'sizin indekslenen alanlarınızda geçmeyen kelimeler. iOS\'ta '
                'yalnızca başlık, subtitle ve gizli keywords alanı sıralamaya '
                'girer.</p><table>%s</table></div>' % "".join(grows))
    return out


def _screenshots(saved, out_dir):
    shots = saved.get("screenshots") or []
    if not shots:
        return ""
    imgs = "".join(
        '<img src="%s" alt="Ekran görüntüsü %d" loading="lazy">'
        % (_esc(os.path.relpath(path, out_dir)), index)
        for index, path in enumerate(shots, start=1))
    return '<div class="shots">%s</div>' % imgs


def html_report(result, out_dir):
    app = result["app"]
    findings = sorted(result["findings"], key=lambda f: SEV_ORDER[f.severity])
    actionable = [f for f in findings if f.severity != OK]
    passed = [f for f in findings if f.severity == OK]

    icon_rel = ""
    if (result.get("assets") or {}).get("icon"):
        icon_rel = os.path.relpath(result["assets"]["icon"], out_dir)

    body = [
        '<div class="wrap"><header>',
        '<img src="%s" alt="">' % _esc(icon_rel) if icon_rel else "",
        "<div><h1>%s</h1>" % _esc(app["name"]),
        '<div class="sub">%s</div>' % _esc(app["subtitle"] or "subtitle tanımlı değil"),
        '<div class="meta">%s · v%s · %s · min iOS %s · <a href="%s">App Store</a></div>'
        % (_esc(app["developer"]), _esc(app["version"]), _esc(app["price"]),
           _esc(app["min_os"]), _esc(app["store_url"])),
        "</div>",
        '<div class="score"><b>%d</b><span>ASO puanı</span></div>' % result["score"],
        "</header>",
        '<p class="meta">%d kritik · %d uyarı · %d kontrol sorunsuz</p>' % (
            sum(1 for f in findings if f.severity == CRITICAL),
            sum(1 for f in findings if f.severity == WARN), len(passed)),
    ]

    if actionable:
        body += ["<h2>Yapılacaklar</h2>"] + [_finding_html(f) for f in actionable]

    shots_html = _screenshots(result.get("assets") or {}, out_dir)
    if shots_html:
        body += ["<h2>Mağaza görselleri</h2>", shots_html,
                 '<p class="meta">Görsel kalitesi kural motoruyla ölçülemez; '
                 '<code>vision-brief.md</code> bu setle birlikte bir modele '
                 'verilmek üzere hazırlandı.</p>']

    if app.get("rating_counts"):
        body += ["<h2>Puan dağılımı</h2>", _histogram(app["rating_counts"])]

    summary = result.get("reviews")
    if summary and summary["total"]:
        body += ["<h2>Yorum temaları</h2>", _themes(summary),
                 "<h2>Sürüme göre yorumlar</h2>", _versions(summary)]

    if result.get("deeplinks"):
        body += ["<h2>Universal Links ve mobil web</h2>"] + [
            _finding_html(f) for f in result["deeplinks"]]

    if result.get("comparison"):
        body += ["<h2>Rakip karşılaştırması</h2>", _comparison(result["comparison"])]

    if passed:
        body += ["<h2>Sorunsuz geçen kontroller</h2>"] + [_finding_html(f) for f in passed]

    body += [
        "<footer>asolens · %s · %s mağazası · "
        "veri kaynakları: iTunes Lookup API, store sayfası, müşteri yorumları RSS"
        "</footer></div>" % (
            datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), app["country"].upper()),
    ]

    document = (
        "<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>%s — ASO raporu</title><style>%s</style></head>"
        "<body>%s</body></html>" % (_esc(app["name"]), CSS, "".join(body))
    )
    path = os.path.join(out_dir, "report.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(document)
    return path


def json_report(result, out_dir):
    payload = {
        "app": {k: v for k, v in result["app"].items() if k != "reviews"},
        "score": result["score"],
        "findings": [f.as_dict() for f in result["findings"]],
        "deeplinks": [f.as_dict() for f in result.get("deeplinks") or []],
        "reviews": result.get("reviews"),
        "comparison": result.get("comparison"),
    }
    path = os.path.join(out_dir, "report.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path
