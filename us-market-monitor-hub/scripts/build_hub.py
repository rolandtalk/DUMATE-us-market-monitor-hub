#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
美國大盤監測報告 Hub 構建腳本
- 從 content/ 讀取報告內容（blocks 格式 / legacy 格式），渲染成 reports/*.html
- 生成 index.html 列表頁（以每篇為單位表列）
- 生成 assets/style.css（手機優先響應式）
輸出為純靜態站點，可直接拖入 Cloudflare Pages 部署。
"""
import json
import html
import re
import os

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(HUB, "content")
REPORTS_DIR = os.path.join(HUB, "reports")
ASSETS_DIR = os.path.join(HUB, "assets")

# ---------------------------------------------------------------- tokens
ACCENT = "#0b3d91"
ACCENT_SOFT = "#eef3fb"
UP = "#c03221"      # 美股紅漲
DOWN = "#1e7e4f"    # 綠跌
INK = "#101828"
INK2 = "#475467"
INK3 = "#98a2b3"
LINE = "#e4e7ec"
CANVAS = "#ffffff"
SURFACE = "#f7f8fa"
SURFACE2 = "#eef1f5"

# ---------------------------------------------------------------- report meta
REPORTS = [
    {
        "slug": "2026-10-11",
        "file": "2026-10-11.json",
        "date_label": "10月11日",
        "full_date": "2026-10-11",
        "data_date": "數據截至 10/9 收盤（週末報告）",
        "kind": "blocks",
        "excerpt": "週五三大指數齊漲結束震盪一週，10月6日納指與標普同創歷史收盤新高；虛擬幣板塊反彈領漲，加密概念股 Coinbase 漲超4%。隔夜要聞豐富：特朗普-普京柴油協議、10月消費者信心跌至五個月低點、9月非農僅增2.9萬人。",
        "tags": ["週末報告", "虛擬幣反彈", "柴油協議", "歷史新高"],
    },
    {
        "slug": "2026-10-10",
        "file": "2026-10-10.json",
        "date_label": "10月10日",
        "full_date": "2026-10-10",
        "data_date": "數據截至 10/9 收盤",
        "kind": "blocks",
        "excerpt": "美股三大指數集體上漲，道指收報51,654.95點（+0.83%）、標普500收報7,811.54點（+0.59%）、納指收報27,366.17點（+0.64%）。房地產與非必需消費品領漲，10/8半導體重挫後科技股企穩反彈。",
        "tags": ["三大指數齊漲", "板塊輪動", "半導體反彈"],
    },
    {
        "slug": "2026-10-09",
        "file": "2026-10-09.json",
        "date_label": "10月9日",
        "full_date": "2026-10-09",
        "data_date": "數據截至 10/8 收盤",
        "kind": "legacy",
        "excerpt": "三大指數震盪回落，納指單日下跌1.25%創七週最大跌幅。AI泡沫擔憂＋油價大漲逾4%＋美債收益率2002年新高三重壓力疊加；能源板塊因油價領漲全場，資金明顯轉向防禦。",
        "tags": ["納指 -1.25%", "AI泡沫擔憂", "油價+4%"],
    },
    {
        "slug": "2026-10-08",
        "file": "2026-10-08.json",
        "date_label": "10月8日",
        "full_date": "2026-10-08",
        "data_date": "數據截至 10/7 收盤",
        "kind": "legacy",
        "excerpt": "美股創歷史收盤新高後回落：國債收益率衝高至5.365%（2002年以來新高）、聯準會會議紀要釋放鷹派信號、通脹仍高於目標構成三重壓力；醫療保健板塊逆勢領漲。",
        "tags": ["歷史新高回落", "10Y 5.365%", "鷹派紀要"],
    },
]

# ---------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s), quote=False)


def esc_keep_b(s):
    """轉義 HTML，但保留 <b> 標籤（舊報告 JSON 中少量使用）。"""
    e = html.escape(str(s), quote=False)
    e = e.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    return e


PCT_RE = re.compile(r"^([+-])([\d,\.]+)%")


def cell_class(text):
    """美股習慣：+ 漲 → 紅，- 跌 → 綠。返回 css class 或 None。"""
    t = str(text).strip()
    if PCT_RE.match(t):
        return "up" if t.startswith("+") else "down"
    return None


def render_table(headers, rows, caption=None):
    out = ['<figure class="tbl">']
    if caption:
        out.append(f"<figcaption>{esc(caption)}</figcaption>")
    out.append('<div class="table-wrap"><table>')
    if headers:
        out.append("<thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr></thead>")
    out.append("<tbody>")
    for r in rows:
        cells = []
        for c in r:
            cls = cell_class(c)
            if cls:
                cells.append(f'<td class="{cls}">{esc_keep_b(c)}</td>')
            else:
                cells.append(f"<td>{esc_keep_b(c)}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table></div></figure>")
    return "".join(out)


def svg_line_chart(labels, values, title, caption):
    """內聯 SVG 折線圖，無外部依賴。"""
    n = len(values)
    W, H = 720, 320
    PL, PR, PT, PB = 56, 16, 24, 40
    vmin, vmax = min(values), max(values)
    pad = max((vmax - vmin) * 0.12, 150)
    lo, hi = vmin - pad, vmax + pad
    iw, ih = W - PL - PR, H - PT - PB

    def x(i):
        return PL + iw * (i / (n - 1)) if n > 1 else PL + iw / 2

    def y(v):
        return PT + ih * (1 - (v - lo) / (hi - lo))

    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(values))
    area = f"{x(0):.1f},{H-PB} {pts} {x(n-1):.1f},{H-PB}"

    # 水平網格 + Y 軸標籤
    ys = []
    steps = 4
    for g in range(steps + 1):
        v = lo + (hi - lo) * g / steps
        yy = y(v)
        ys.append(f'<line x1="{PL}" y1="{yy:.1f}" x2="{W-PR}" y2="{yy:.1f}" stroke="{LINE}" stroke-width="1"/>'
                  f'<text x="{PL-8}" y="{yy+4:.1f}" text-anchor="end" font-size="12" fill="{INK3}">{v:,.0f}</text>')
    # X 軸標籤（稀疏顯示）
    xl = []
    idxs = sorted(set([0, max(1, n // 7), max(2, n * 2 // 7), max(3, n * 3 // 7), max(4, n * 4 // 7), max(5, n * 5 // 7), n - 1]))
    for i in idxs:
        if 0 <= i < n:
            xl.append(f'<text x="{x(i):.1f}" y="{H-PB+22}" text-anchor="middle" font-size="12" fill="{INK3}">{esc(labels[i])}</text>')
    # 關鍵點
    imax = values.index(max(values))
    imin = values.index(min(values))
    marks = (
        f'<circle cx="{x(imax):.1f}" cy="{y(max(values)):.1f}" r="4" fill="{UP}"/>'
        f'<text x="{x(imax):.1f}" y="{y(max(values))-10:.1f}" text-anchor="middle" font-size="12" fill="{UP}">{max(values):,.0f}</text>'
        f'<circle cx="{x(imin):.1f}" cy="{y(min(values)):.1f}" r="4" fill="{ACCENT}"/>'
        f'<text x="{x(imin):.1f}" y="{y(min(values))+20:.1f}" text-anchor="middle" font-size="12" fill="{ACCENT}">{min(values):,.0f}</text>'
    )
    svg = (
        f'<figure class="chart"><figcaption>{esc(title)}</figcaption>'
        f'<div class="chart-box"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">'
        + "".join(ys) + "".join(xl)
        + f'<path d="M {area} Z" fill="{ACCENT}" opacity="0.08" stroke="none"/>'
        + f'<polyline points="{pts}" fill="none" stroke="{ACCENT}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
        + marks
        + "</svg></div>"
        + (f'<p class="chart-cap">{esc(caption)}</p></figure>' if caption else "</figure>")
    )
    return svg


def svg_bar_chart(labels, datasets, y_label):
    """內聯 SVG 分組柱狀圖：正漲紅、負跌綠。"""
    W, H = 720, 320
    PL, PR, PT, PB = 56, 16, 24, 48
    iw, ih = W - PL - PR, H - PT - PB
    allv = [v for ds in datasets for v in ds["values"]]
    mx = max(max(allv), 0.5)
    mn = min(min(allv), -0.5)
    span = mx - mn
    zero_y = PT + ih * (mx / span)
    scale = ih / span

    def y(v):
        return zero_y - v * scale

    groups = len(labels)
    n_ds = len(datasets)
    gw = iw / groups
    bw = min(gw * 0.55 / n_ds, 34)
    total_w = bw * n_ds + (n_ds - 1) * 4
    colors = [ACCENT, INK2, UP]

    out = [f'<line x1="{PL}" y1="{zero_y:.1f}" x2="{W-PR}" y2="{zero_y:.1f}" stroke="{INK}" stroke-width="1"/>']
    # 網格
    for g in range(5):
        v = mn + span * g / 4
        yy = y(v)
        out.append(f'<line x1="{PL}" y1="{yy:.1f}" x2="{W-PR}" y2="{yy:.1f}" stroke="{LINE}" stroke-width="1"/>'
                   f'<text x="{PL-8}" y="{yy+4:.1f}" text-anchor="end" font-size="12" fill="{INK3}">{v:+.1f}</text>')
    for gi, lab in enumerate(labels):
        gx = PL + gw * gi + (gw - total_w) / 2
        for di, ds in enumerate(datasets):
            v = ds["values"][gi]
            bx = gx + di * (bw + 4)
            by = y(v)
            bh = abs(v) * scale
            col = UP if v >= 0 else DOWN
            out.append(f'<rect x="{bx:.1f}" y="{min(by, zero_y):.1f}" width="{bw:.1f}" height="{max(bh,1):.1f}" rx="2" fill="{col}" opacity="0.85"/>')
            out.append(f'<text x="{bx+bw/2:.1f}" y="{(by-6 if v>=0 else by+16):.1f}" text-anchor="middle" font-size="11" fill="{col}">{v:+.2f}</text>')
        out.append(f'<text x="{gx+total_w/2:.1f}" y="{H-PB+22}" text-anchor="middle" font-size="13" fill="{INK2}">{esc(lab)}</text>')
    # 圖例
    lx = PL
    for di, ds in enumerate(datasets):
        out.append(f'<rect x="{lx}" y="{PT-20}" width="12" height="12" rx="2" fill="{colors[di%len(colors)]}" opacity="0.85"/>'
                   f'<text x="{lx+18}" y="{PT-10}" font-size="13" fill="{INK2}">{esc(ds["label"])}</text>')
        lx += 24 + 24 + len(ds["label"]) * 15
    svg = (
        f'<svg viewBox="0 0 {W} {H}" role="img"><g>'
        + "".join(out)
        + "</g></svg>"
    )
    return svg


# ---------------------------------------------------------------- blocks render (10-10 / 10-11)
def render_blocks(blocks):
    out = []
    buf = []  # 連續 bullet 緩衝，遇非 bullet 時 flush 成一個 ul

    def flush():
        if buf:
            out.append("<ul>" + "".join(buf) + "</ul>")
            buf.clear()

    for b in blocks:
        t = b.get("type")
        if t == "bullet":
            buf.append(f"<li>{esc_keep_b(b['text'])}</li>")
            continue
        flush()
        if t == "h1":
            out.append(f'<h2 id="{esc(b["text"][:24])}">{esc(b["text"])}</h2>')
        elif t == "h2":
            out.append(f'<h3>{esc(b["text"])}</h3>')
        elif t == "body":
            out.append(f'<p>{esc_keep_b(b["text"])}</p>')
        elif t == "table":
            out.append(render_table(b.get("headers") or [], b.get("rows") or [], b.get("caption")))
        elif t == "chart" and b.get("chart_type") == "line":
            out.append(svg_line_chart(b.get("labels") or [], (b.get("datasets") or [{}])[0].get("values") or [],
                                      b.get("title") or "", b.get("caption") or ""))
        elif t == "callout":
            out.append(f'<div class="callout"><p>{esc_keep_b(b["text"])}</p></div>')
        elif t == "note":
            out.append(f'<p class="note">{esc_keep_b(b["text"])}</p>')
    flush()
    return "".join(out)


# ---------------------------------------------------------------- legacy render (10-08 / 10-09)
def item_list(items, classname="risk-item"):
    lis = "".join(f"<li>{esc_keep_b(i)}</li>" for i in items)
    return f'<ul class="{classname}">{lis}</ul>'


def render_legacy(d):
    out = []
    # 一、市場概覽
    out.append('<h2 id="overview">一、市場概覽</h2>')
    out.append(f'<p>{esc_keep_b(d["core"]["headline"])}</p>')
    out.append(f'<div class="callout k"><p><strong>核心判斷：</strong>{esc_keep_b(d["core"]["key_judgement"])}</p></div>')
    for feat in d["core"]["features"]:
        out.append(f"<p>{esc_keep_b(feat)}</p>")
    # 二、主要指數表現
    out.append('<h2 id="indices">二、主要指數表現</h2>')
    out.append(f'<p>{esc_keep_b(d["indices"]["intro"])}</p>')
    out.append(render_table(d["indices"]["table_headers"], d["indices"]["table_rows"], d["indices"]["table_caption"]))
    if d.get("chart") and d["chart"].get("chart_type") == "bar":
        ch = d["chart"]
        out.append(f'<figure class="chart"><figcaption>{esc(ch["title"])}</figcaption><div class="chart-box">')
        out.append(svg_bar_chart(ch["labels"], ch["datasets"], ch.get("y_label", "")))
        out.append(f'</div><p class="chart-cap">{esc(ch.get("caption", ""))}</p></figure>')
    out.append(f"<p>{esc_keep_b(d['indices']['analysis'])}</p>")
    # 羅素2000
    if d.get("russell2000") and d["russell2000"].get("analysis"):
        out.append(f'<h3>羅素2000小型股</h3><p>{esc_keep_b(d["russell2000"]["analysis"])}</p>')
    # 三、宏觀指標（10-08）/ 三、VIX與四、宏觀（10-09 按 key 存在順序）
    macro = d.get("macro", {})
    vix = d.get("vix", {})
    if vix:
        out.append('<h2 id="vix">三、VIX恐慌指數</h2>')
        if vix.get("table_headers"):
            out.append(render_table(vix["table_headers"], vix["table_rows"], vix.get("table_caption")))
        if vix.get("analysis"):
            out.append(f"<p>{esc_keep_b(vix['analysis'])}</p>")
    if macro:
        out.append('<h2 id="macro">四、宏觀指標與聯準會</h2>')
        if macro.get("fed_callout"):
            out.append(f'<div class="callout"><p>{esc_keep_b(macro["fed_callout"])}</p></div>')
        if macro.get("fed_analysis"):
            out.append(f"<p>{esc_keep_b(macro['fed_analysis'])}</p>")
        if macro.get("table_headers"):
            out.append(render_table(macro["table_headers"], macro["table_rows"], macro.get("table_caption")))
        if macro.get("summary"):
            out.append(f"<p>{esc_keep_b(macro['summary'])}</p>")
    # 市場情緒
    senti = d.get("sentiment", {})
    if senti:
        out.append('<h2 id="sentiment">五、市場情緒與資金流向</h2>')
        if senti.get("treasury"):
            out.append('<h3>國債與利率</h3>' + item_list(senti["treasury"], "flow-item"))
        if senti.get("capital_flows"):
            out.append('<h3>資金流向</h3>' + item_list(senti["capital_flows"], "flow-item"))
    # 板塊
    sec = d.get("sectors", {})
    if sec:
        out.append('<h2 id="sectors">六、板塊表現</h2>')
        if sec.get("table_headers"):
            out.append(render_table(sec["table_headers"], sec["table_rows"], sec.get("table_caption")))
        if sec.get("analysis"):
            out.append(f"<p>{esc_keep_b(sec['analysis'])}</p>")
    # 風險
    rk = d.get("risks", {})
    if rk:
        out.append('<h2 id="risks">七、風險提示與關注事項</h2>')
        if rk.get("items"):
            out.append('<h3>風險提示</h3>' + item_list(rk["items"], "risk-item"))
        if rk.get("watchlist"):
            out.append('<h3>關注清單</h3>' + item_list(rk["watchlist"], "watch-item"))
        if rk.get("summary"):
            out.append(f"<p>{esc_keep_b(rk['summary'])}</p>")
    # 來源
    if d.get("sources"):
        out.append('<h2 id="sources">數據來源</h2><ol class="src-list">')
        for s in d["sources"]:
            txt = esc_keep_b(s["text"])
            m = re.search(r"(https?://\S+)", txt)
            if m:
                url = m.group(1).rstrip("。)）")
                txt = txt.replace(m.group(1), f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(url)}</a>')
            out.append(f"<li>{txt}</li>")
        out.append("</ol>")
    return "".join(out)


# ---------------------------------------------------------------- page shell
def page_html(title, desc, body, back_link=True, css_href="../assets/style.css", brand_href="../index.html"):
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{esc(desc)}">
<title>{esc(title)}</title>
<link rel="stylesheet" href="{esc(css_href)}">
</head>
<body>
<header class="site-head">
  <div class="head-inner">
    <a class="brand" href="{esc(brand_href)}">美國大盤監測報告</a>
    {('<a class="back" href="' + esc(brand_href) + '">← 所有報告</a>' if back_link else '')}
  </div>
</header>
<main class="page">{body}</main>
<footer class="site-foot">
  <div class="foot-inner">
    <p>本內容由人工智能基於公開信息及相關數據生成，僅供研究與交流，不構成任何投資建議、收益承諾或交易依據。市場有風險，投資需謹慎。</p>
    <p class="meta">資料來源：新華社、東方財富、iFind、中國證券報等公開來源 · 每日自動生成</p>
  </div>
</footer>
</body>
</html>"""


def build_report(meta):
    with open(os.path.join(CONTENT_DIR, meta["file"]), encoding="utf-8") as f:
        data = json.load(f)
    if meta["kind"] == "blocks":
        body = render_blocks(data)
    else:
        body = render_legacy(data)
    # 報告頭部
    head = f"""
<article>
<header class="report-head">
  <p class="kicker">{esc(meta['data_date'])}</p>
  <h1>{esc(meta['date_label'])} · 美國大盤監測報告</h1>
  <p class="lede">{esc(meta['excerpt'])}</p>
</header>
{body}
"""
    html_body = head + "</article>"
    return page_html(f"{meta['date_label']} 美國大盤監測報告", meta["excerpt"], html_body)


def build_index():
    cards = []
    for m in REPORTS:
        tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in m["tags"])
        cards.append(f"""
<a class="card" href="reports/{esc(m['slug'])}.html">
  <div class="card-top">
    <span class="date">{esc(m['date_label'])}</span>
    <span class="data">{esc(m['data_date'])}</span>
  </div>
  <h2>{m['full_date']} · 美國大盤監測報告</h2>
  <p class="card-ex">{esc(m['excerpt'])}</p>
  <div class="tags">{tags}</div>
  <span class="read">閱讀全文 →</span>
</a>""")
    body = f"""
<section class="hero">
  <p class="kicker">US MARKET MONITOR</p>
  <h1>美國大盤監測報告</h1>
  <p class="lede">每日美股大盤監測彙整：指數、板塊、風險指標與關鍵個股動態。點擊任一報告展開閱讀，手機畫面優先排版。</p>
</section>
<section class="list">
  <h2 class="list-title">報告列表</h2>
  {''.join(cards)}
</section>
"""
    return page_html("美國大盤監測報告", "每日美股大盤監測報告彙整列表", body,
                     back_link=False, css_href="assets/style.css", brand_href="index.html")


CSS = f"""
:root {{
  --accent: {ACCENT}; --accent-soft: {ACCENT_SOFT};
  --up: {UP}; --down: {DOWN};
  --ink: {INK}; --ink-2: {INK2}; --ink-3: {INK3};
  --line: {LINE}; --canvas: {CANVAS}; --surface: {SURFACE}; --surface2: {SURFACE2};
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ -webkit-text-size-adjust: 100%; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", "Noto Sans TC", sans-serif;
  color: var(--ink); background: var(--surface);
  font-size: 16px; line-height: 1.75;
  -webkit-font-smoothing: antialiased;
}}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

/* header */
.site-head {{
  position: sticky; top: 0; z-index: 10;
  background: rgba(255,255,255,0.92); backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--line);
}}
.head-inner {{
  max-width: 1240px; margin: 0 auto; padding: 12px 20px;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}}
.brand {{ font-weight: 700; color: var(--ink); font-size: 16px; letter-spacing: .02em; }}
.brand:hover {{ text-decoration: none; }}
.back {{ font-size: 14px; color: var(--ink-2); white-space: nowrap; }}

/* layout */
.page {{ max-width: 1240px; margin: 0 auto; padding: 24px 20px 64px; }}
article {{ max-width: 760px; margin: 0 auto; }}
.hero {{ max-width: 760px; margin: 0 auto; padding: 40px 0 12px; }}
.hero h1 {{ font-size: 34px; line-height: 1.15; font-weight: 700; letter-spacing: .01em; }}
.hero .lede {{ margin-top: 12px; color: var(--ink-2); font-size: 16px; }}
.kicker {{ font-size: 12px; font-weight: 700; letter-spacing: .12em; color: var(--accent); text-transform: uppercase; }}

/* report head */
.report-head {{ padding: 12px 0 20px; border-bottom: 1px solid var(--line); margin-bottom: 8px; }}
.report-head h1 {{ font-size: 28px; line-height: 1.25; margin-top: 6px; }}
.report-head .lede {{ margin-top: 10px; color: var(--ink-2); font-size: 15px; }}

/* typography */
h2 {{ font-size: 22px; line-height: 1.35; margin: 40px 0 14px; padding-top: 8px; border-top: 3px solid var(--accent); }}
h3 {{ font-size: 18px; margin: 26px 0 10px; color: var(--ink); }}
p {{ margin: 12px 0; }}
ul, ol {{ margin: 10px 0 14px; padding-left: 22px; }}
li {{ margin: 6px 0; }}
strong {{ font-weight: 700; }}

/* tables */
.tbl {{ margin: 18px 0; }}
.tbl figcaption, .chart figcaption {{ font-size: 14px; font-weight: 600; color: var(--ink-2); margin-bottom: 8px; }}
.table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid var(--line); border-radius: 8px; }}
table {{ border-collapse: collapse; width: 100%; min-width: 520px; font-size: 14.5px; background: var(--canvas); }}
th {{ background: var(--surface2); font-weight: 600; text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; }}
td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }}
tbody tr:last-child td {{ border-bottom: none; }}
td.up {{ color: var(--up); font-weight: 600; white-space: nowrap; }}
td.down {{ color: var(--down); font-weight: 600; white-space: nowrap; }}

/* charts */
.chart {{ margin: 22px 0; }}
.chart-box {{ background: var(--canvas); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }}
.chart-box svg {{ display: block; width: 100%; height: auto; }}
.chart-cap {{ font-size: 12px; color: var(--ink-3); margin-top: 6px; }}

/* callout / lists */
.callout {{
  background: var(--accent-soft); border-left: 4px solid var(--accent);
  border-radius: 0 8px 8px 0; padding: 14px 16px; margin: 18px 0;
}}
.callout p {{ margin: 0; font-size: 14.5px; color: var(--ink); }}
.callout.k {{ border-left-color: var(--up); }}
.flow-item, .risk-item, .watch-item {{ line-height: 1.7; }}
.src-list {{ font-size: 13px; color: var(--ink-2); overflow-wrap: break-word; }}
.src-list li {{ margin: 8px 0; }}
.note {{ font-size: 13px; color: var(--ink-3); }}

/* index cards */
.list-title {{ font-size: 20px; margin: 32px 0 16px; border-top: none; }}
.list {{ max-width: 760px; margin: 0 auto; }}
.card {{
  display: block; background: var(--canvas); border: 1px solid var(--line);
  border-radius: 10px; padding: 20px; margin: 14px 0;
  transition: border-color .15s, box-shadow .15s, transform .15s;
}}
.card:hover {{ border-color: var(--accent); box-shadow: 0 4px 14px rgba(16,24,40,.08); transform: translateY(-1px); text-decoration: none; }}
.card-top {{ display: flex; align-items: baseline; justify-content: space-between; gap: 10px; flex-wrap: wrap; }}
.card .date {{ font-size: 20px; font-weight: 700; }}
.card .data {{ font-size: 12.5px; color: var(--ink-3); }}
.card h2 {{ font-size: 16px; margin: 8px 0 6px; border: none; padding: 0; color: var(--ink); }}
.card-ex {{ color: var(--ink-2); font-size: 14.5px; margin: 4px 0 10px; }}
.tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }}
.tag {{
  background: var(--surface2); color: var(--ink-2); border-radius: 999px;
  padding: 3px 10px; font-size: 12px;
}}
.read {{ font-size: 14px; font-weight: 600; color: var(--accent); }}

/* footer */
.site-foot {{ border-top: 1px solid var(--line); background: var(--canvas); }}
.foot-inner {{ max-width: 760px; margin: 0 auto; padding: 28px 20px 48px; }}
.foot-inner p {{ font-size: 12.5px; color: var(--ink-3); margin: 4px 0; }}
.foot-inner .meta {{ margin-top: 8px; }}

/* small screens */
@media (max-width: 480px) {{
  .page {{ padding: 16px 14px 56px; }}
  .head-inner {{ padding: 10px 14px; }}
  .hero h1 {{ font-size: 30px; }}
  .report-head h1 {{ font-size: 24px; }}
  h2 {{ font-size: 20px; margin-top: 32px; }}
  .card {{ padding: 16px; }}
}}
"""


def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)
    with open(os.path.join(ASSETS_DIR, "style.css"), "w", encoding="utf-8") as f:
        f.write(CSS)
    for m in REPORTS:
        page = build_report(m)
        with open(os.path.join(REPORTS_DIR, f"{m['slug']}.html"), "w", encoding="utf-8") as f:
            f.write(page)
        print(f"written reports/{m['slug']}.html ({len(page)} chars)")
    idx = build_index()
    with open(os.path.join(HUB, "index.html"), "w", encoding="utf-8") as f:
        f.write(idx)
    print(f"written index.html ({len(idx)} chars)")


if __name__ == "__main__":
    main()