"""
Зургийн систем (S8): HTML/CSS темплэйт → headless Chromium (Playwright) → PNG.

ЯАГААД HTML: PIL-ээр gradient, blur, drop-shadow, жинхэнэ typography хийх нь
олон зуун мөр код; HTML/CSS-ээр нэг темплэйт. Бүх карт 4:5 (1080×1350) —
Facebook-ийн мобайл feed-д 16:9-өөс 60% их талбай, Instagram-д шууд тохирно.

Өгөгдөл: ESPN scoreboard (лого, багийн өнгө, тоглогчийн headshot), ESPN news
API (нийтлэлийн зураг, athleteId/teamId), эх нийтлэлийн og:image.

Playwright байхгүй/унасан бол бүх функц b"" буцаана → main.py хуучин PIL
картаа ашиглана (юу ч эвдрэхгүй).

Загварууд (tools/design/*.html — эзэн харж баталсан загварууд):
  recap   — тоглолтын үр дүн: хоёр багийн өнгөөр хуваасан фон, лого, оноо, W-L, шилдэг тоглогч
  deal    — гэрээ/трейд: headshot, багийн лого, том тоо ($, жил, дундаж)
  quote   — ишлэл: бүдэг фон зураг, том ишлэл, headshot
  news    — бусад мэдээ: эх зураг БҮТНЭЭРЭЭ (blur фон), badge, гарчиг, баримтын чип
  digest  — өглөөний NBA: бүх тоглолтын оноо нэг картанд
  standings — бүсийн байрлалын хүснэгт
"""

import atexit
import html
import logging
import os
import re

log = logging.getLogger(__name__)

CARD_W, CARD_H = 1080, 1350
BRAND = os.environ.get("CARD_BRAND", "МОНГОЛ МЭДЭЭ 🏀")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONT = os.path.join(_ROOT, "assets", "fonts", "Montserrat.ttf")
def _font_uri() -> str:
    """set_content() хуудас file:// ачаалж чадахгүй тул фонтыг base64 шигтгэнэ."""
    try:
        import base64
        with open(_FONT, "rb") as fh:
            return "data:font/ttf;base64," + base64.b64encode(fh.read()).decode("ascii")
    except Exception:
        return ""


_FONT_URI = _font_uri()

BASE_CSS = f"""
@font-face{{font-family:'Montserrat';src:url('{_FONT_URI}') format('truetype');font-weight:100 900}}
*{{box-sizing:border-box}}
body{{margin:0;background:#111;font-family:Montserrat,Arial,sans-serif;color:#fff}}
.card{{width:{CARD_W}px;height:{CARD_H}px;position:relative;overflow:hidden}}
.badge{{display:inline-block;background:#e63946;color:#fff;font-weight:900;font-size:26px;padding:8px 18px;border-radius:8px;letter-spacing:1px}}
.badge.light{{background:#fff;color:#111}}
.brand{{font-weight:900;font-size:28px;letter-spacing:2px}}
.foot{{position:absolute;bottom:44px;left:60px;right:60px;display:flex;justify-content:space-between;align-items:center;font-weight:600;font-size:24px;opacity:.95}}
.glass{{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);border-radius:24px}}
"""


def _e(s) -> str:
    return html.escape(str(s or ""))


def _wrap(body: str, css: str = "") -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{BASE_CSS}{css}</style></head><body>{body}</body></html>"


# ============================================================
# РЕНДЕР
# ============================================================
_pw = None
_browser = None


def _get_browser():
    global _pw, _browser
    if _browser is not None:
        return _browser
    from playwright.sync_api import sync_playwright  # noqa: WPS433
    _pw = sync_playwright().start()
    _browser = _pw.chromium.launch()
    atexit.register(_close)
    return _browser


def _close():
    global _pw, _browser
    try:
        if _browser:
            _browser.close()
        if _pw:
            _pw.stop()
    except Exception:
        pass
    _browser = _pw = None


def render(html_doc: str, width: int = CARD_W, height: int = CARD_H, wait_ms: int = 800) -> bytes:
    """HTML → PNG bytes. Алдаа гарвал b"" (дуудагч хуучин зам руугаа буцна)."""
    try:
        browser = _get_browser()
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        try:
            page.set_content(html_doc, wait_until="load")
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass  # зарим зураг удаан бол тэр чигээрээ авна
            page.wait_for_timeout(wait_ms)
            png = page.locator(".card").first.screenshot(type="png")
        finally:
            page.close()
        log.info(f"[CARDS] рендер OK ({len(png) // 1024} KB)")
        return png
    except Exception as e:
        log.warning(f"[CARDS] рендер алдаа: {e} — PIL карт руу буцна")
        return b""


# ============================================================
# ТЕМПЛЭЙТҮҮД
# ============================================================
_FOOT = "<div class='foot'><span class='brand'>{brand}</span><span>{right}</span></div>"


def _foot(right: str) -> str:
    return _FOOT.format(brand=_e(BRAND), right=_e(right))


def recap_card(card: dict) -> bytes:
    """card = {date, stage, home:{name,logo,color,record,score}, away:{...},
    leaders:[{name,headshot,team,stats:[(label,value),...]}], ot}"""
    h, a = card["home"], card["away"]
    css = f"""
.card{{background:linear-gradient(115deg,#{a['color']} 0 50%,#{h['color']} 50% 100%)}}
.card:before{{content:"";position:absolute;inset:0;background:
  radial-gradient(900px 500px at 20% 15%,rgba(255,255,255,.18),transparent 60%),
  radial-gradient(900px 500px at 80% 90%,rgba(255,255,255,.14),transparent 60%),
  linear-gradient(180deg,rgba(0,0,0,0) 55%,rgba(0,0,0,.55) 100%)}}
.top{{position:absolute;top:48px;left:60px;right:60px;display:flex;justify-content:space-between;align-items:center}}
.date{{font-weight:600;font-size:24px;opacity:.9}}
.teams{{position:absolute;top:170px;left:0;right:0;display:flex;justify-content:space-around;align-items:flex-start}}
.team{{display:flex;flex-direction:column;align-items:center;width:440px}}
.team img{{width:300px;height:300px;object-fit:contain;filter:drop-shadow(0 20px 30px rgba(0,0,0,.45))}}
.team .name{{font-weight:800;font-size:36px;margin-top:10px;text-align:center;line-height:1.1}}
.team .rec{{font-weight:600;font-size:26px;opacity:.85}}
.score{{position:absolute;top:560px;left:0;right:0;text-align:center;font-weight:900;font-size:170px;line-height:1;letter-spacing:-4px;text-shadow:0 12px 40px rgba(0,0,0,.4)}}
.final{{position:absolute;top:750px;left:0;right:0;text-align:center;font-weight:800;font-size:32px;letter-spacing:6px;opacity:.9}}
.stars{{position:absolute;top:840px;left:60px;right:60px;display:flex;gap:30px}}
.star{{flex:1;padding:22px;display:flex;align-items:center;gap:20px;min-height:280px;overflow:hidden}}
.star img{{width:150px;height:150px;border-radius:50%;object-fit:cover;object-position:top;background:#fff;flex:none}}
.star .n{{font-weight:800;font-size:32px;line-height:1.05}}
.star .t{{font-weight:600;font-size:20px;opacity:.8;margin-top:4px}}
.star .s{{font-weight:900;font-size:44px;margin-top:8px;line-height:1.1}}
.star .s small{{font-size:18px;font-weight:600;opacity:.85;margin-right:8px}} .star .s span{{white-space:nowrap;margin-right:14px}}
"""
    stars = ""
    for p in (card.get("leaders") or [])[:2]:
        stats = "".join(f"<span><small>{_e(l)}</small>{_e(v)}</span>" for l, v in p.get("stats", [])[:2])
        img = f"<img src='{_e(p['headshot'])}'>" if p.get("headshot") else ""
        stars += f"<div class='star glass'>{img}<div><div class='n'>{_e(p['name'])}</div><div class='t'>{_e(p.get('team',''))}</div><div class='s'>{stats}</div></div></div>"
    ot = f" · {card['ot']}" if card.get("ot") else ""
    body = f"""<div class='card'>
<div class='top'><span class='badge light'>NBA · {_e(card.get('stage', 'УЛИРЛЫН ТОГЛОЛТ'))}{_e(ot)}</span><span class='date'>{_e(card.get('date', ''))}</span></div>
<div class='teams'>
 <div class='team'><img src='{_e(a['logo'])}'><div class='name'>{_e(a['name'])}</div><div class='rec'>{_e(a.get('record', ''))}</div></div>
 <div class='team'><img src='{_e(h['logo'])}'><div class='name'>{_e(h['name'])}</div><div class='rec'>{_e(h.get('record', ''))}</div></div>
</div>
<div class='score'>{_e(a['score'])} : {_e(h['score'])}</div>
<div class='final'>ТОГЛОЛТ ДУУСЛАА</div>
<div class='stars'>{stars}</div>
{_foot('Эх сурвалж: ESPN')}
</div>"""
    return render(_wrap(body, css))


def news_card(photo: str, badge: str, headline: str, subtitle: str = "", chips: list | None = None,
              source: str = "", date: str = "", accent: str = "#e63946", base: str = "#0b1a33") -> bytes:
    css = f"""
.card{{background:{base}}}
.bg{{position:absolute;inset:0;background:url('{_e(photo)}') center/cover;filter:blur(40px) brightness(.45);transform:scale(1.15)}}
.photo{{position:absolute;top:60px;left:60px;width:960px;height:640px;border-radius:24px;object-fit:cover;box-shadow:0 30px 60px rgba(0,0,0,.5);background:#000}}
.body{{position:absolute;top:740px;left:60px;right:60px;bottom:110px;overflow:hidden}}
.badge{{background:{accent}}}
h1{{font-weight:900;font-size:{54 if len(headline) < 70 else 46}px;line-height:1.15;margin:22px 0 18px}}
p{{font-weight:500;font-size:29px;line-height:1.4;opacity:.9;margin:0}}
.facts{{display:flex;gap:16px;margin-top:24px;flex-wrap:wrap}}
.fact{{padding:12px 22px;font-weight:800;font-size:28px;border-radius:14px}}
"""
    chips_html = "".join(f"<div class='fact glass'>{_e(c)}</div>" for c in (chips or [])[:3])
    right = " · ".join(x for x in (f"Эх сурвалж: {source}" if source else "", date) if x)
    body = f"""<div class='card'>
<div class='bg'></div><img class='photo' src='{_e(photo)}'>
<div class='body'><span class='badge'>{_e(badge)}</span><h1>{_e(headline)}</h1><p>{_e(subtitle)}</p><div class='facts'>{chips_html}</div></div>
{_foot(right)}
</div>"""
    return render(_wrap(body, css))


def deal_card(name: str, role: str, headshot: str, team_logo: str, nums: list, line: str,
              badge: str = "ГЭРЭЭ", source: str = "ESPN", color1: str = "#1d428a", color2: str = "#c8102e") -> bytes:
    css = f"""
.card{{background:linear-gradient(160deg,{color1} 0%,#0b1a33 60%,{color2} 140%)}}
.logo{{position:absolute;right:-120px;top:-80px;width:700px;opacity:.14}}
.head{{position:absolute;top:60px;left:60px}}
.player{{position:absolute;top:170px;left:60px;width:520px;height:520px;border-radius:32px;background:#fff;object-fit:cover;object-position:top;box-shadow:0 30px 60px rgba(0,0,0,.5)}}
.teamlogo{{position:absolute;top:170px;right:60px;width:380px}}
.name{{position:absolute;top:720px;left:60px;right:60px;font-weight:900;font-size:{68 if len(name) < 18 else 54}px;line-height:1}}
.role{{position:absolute;top:800px;left:60px;font-weight:600;font-size:30px;opacity:.85}}
.nums{{position:absolute;top:880px;left:60px;right:60px;display:flex;gap:24px}}
.num{{flex:1;padding:28px 30px}}
.num b{{display:block;font-weight:900;font-size:78px;line-height:1}}
.num span{{font-weight:600;font-size:24px;opacity:.85;letter-spacing:1px}}
.line{{position:absolute;top:1150px;left:60px;right:60px;font-weight:600;font-size:30px;line-height:1.35}}
"""
    nums_html = "".join(f"<div class='num glass'><b>{_e(v)}</b><span>{_e(l)}</span></div>" for v, l in nums[:3])
    body = f"""<div class='card'>
<img class='logo' src='{_e(team_logo)}'>
<div class='head'><span class='badge'>{_e(badge)}</span></div>
<img class='player' src='{_e(headshot)}'><img class='teamlogo' src='{_e(team_logo)}'>
<div class='name'>{_e(name)}</div><div class='role'>{_e(role)}</div>
<div class='nums'>{nums_html}</div><div class='line'>{_e(line)}</div>
{_foot('Эх сурвалж: ' + source)}
</div>"""
    return render(_wrap(body, css))


def quote_card(quote: str, name: str, subline: str, photo: str = "", headshot: str = "", source: str = "ESPN") -> bytes:
    size = 58 if len(quote) < 110 else (48 if len(quote) < 180 else 40)
    css = f"""
.card{{background:#111}}
.bg{{position:absolute;inset:0;background:{('url(' + chr(39) + _e(photo) + chr(39) + ') center/cover') if photo else '#1b1b1b'};filter:brightness(.35) saturate(.8)}}
.fade{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.1) 0%,rgba(0,0,0,.85) 70%)}}
.mark{{position:absolute;top:120px;left:60px;font-size:300px;font-weight:900;line-height:.6;color:#e63946;opacity:.9}}
.text{{position:absolute;top:400px;left:60px;right:60px;font-weight:800;font-size:{size}px;line-height:1.25;max-height:580px;overflow:hidden}}
.who{{position:absolute;top:1010px;left:60px;right:60px;display:flex;align-items:center;gap:26px}}
.who img{{width:150px;height:150px;border-radius:50%;object-fit:cover;object-position:top;background:#fff;border:4px solid #e63946;flex:none}}
.who b{{display:block;font-weight:900;font-size:40px}}
.who span{{font-weight:600;font-size:26px;opacity:.85}}
"""
    hs = f"<img src='{_e(headshot)}'>" if headshot else ""
    body = f"""<div class='card'>
<div class='bg'></div><div class='fade'></div><div class='mark'>“</div>
<div class='text'>{_e(quote)}</div>
<div class='who'>{hs}<div><b>{_e(name)}</b><span>{_e(subline)}</span></div></div>
{_foot('Эх сурвалж: ' + source)}
</div>"""
    return render(_wrap(body, css))


def digest_card(games: list, date_label: str, title: str = "ӨГЛӨӨНИЙ NBA") -> bytes:
    """games = [{away:{abbr,logo,score,winner}, home:{...}, top:'Name 34 PTS', ot:bool}]"""
    n = max(len(games), 1)
    row_h = min(84, (1350 - 300) // n)
    css = f"""
.card{{background:linear-gradient(160deg,#0b1a33 0%,#16213e 60%,#1d428a 140%)}}
.head{{position:absolute;top:50px;left:60px;right:60px;display:flex;justify-content:space-between;align-items:center}}
.title{{font-weight:900;font-size:54px;letter-spacing:1px}}
.date{{font-weight:600;font-size:26px;opacity:.9}}
.rows{{position:absolute;top:150px;left:60px;right:60px}}
.row{{display:flex;align-items:center;height:{row_h}px;border-bottom:1px solid rgba(255,255,255,.12)}}
.row img{{width:{min(56, row_h - 20)}px;height:{min(56, row_h - 20)}px;object-fit:contain}}
.t{{width:110px;font-weight:800;font-size:30px;text-align:center}}
.sc{{width:100px;font-weight:900;font-size:36px;text-align:center}}
.sc.l{{opacity:.55;font-weight:600}}
.mid{{width:30px;text-align:center;opacity:.6;font-weight:600}}
.top{{flex:1;font-weight:600;font-size:22px;opacity:.85;padding-left:22px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.ot{{font-size:18px;font-weight:800;color:#ffd166;margin-left:8px}}
"""
    rows = ""
    for g in games[:14]:
        a, h = g["away"], g["home"]
        rows += (f"<div class='row'><img src='{_e(a['logo'])}'><div class='t'>{_e(a['abbr'])}</div>"
                 f"<div class='sc {'' if a.get('winner') else 'l'}'>{_e(a['score'])}</div><div class='mid'>:</div>"
                 f"<div class='sc {'' if h.get('winner') else 'l'}'>{_e(h['score'])}</div><div class='t'>{_e(h['abbr'])}</div>"
                 f"<img src='{_e(h['logo'])}'><div class='top'>{_e(g.get('top', ''))}{'<span class=ot>OT</span>' if g.get('ot') else ''}</div></div>")
    body = f"""<div class='card'>
<div class='head'><span class='title'>{_e(title)}</span><span class='date'>{_e(date_label)}</span></div>
<div class='rows'>{rows}</div>
{_foot('Эх сурвалж: ESPN')}
</div>"""
    return render(_wrap(body, css))


def standings_card(conf_name: str, rows: list, date_label: str) -> bytes:
    """rows = [{rank, logo, name, wl, pct, gb, streak}]"""
    css = """
.card{background:linear-gradient(160deg,#0b1a33 0%,#16213e 60%,#1d428a 140%)}
.head{position:absolute;top:50px;left:60px;right:60px;display:flex;justify-content:space-between;align-items:center}
.title{font-weight:900;font-size:46px}
.date{font-weight:600;font-size:24px;opacity:.9}
table{position:absolute;top:140px;left:60px;right:60px;width:960px;border-collapse:collapse}
th{font-weight:600;font-size:20px;opacity:.7;text-align:left;padding:8px 10px;letter-spacing:1px}
td{padding:6px 10px;border-top:1px solid rgba(255,255,255,.12);font-weight:700;font-size:26px;height:68px}
td img{width:46px;height:46px;object-fit:contain;vertical-align:middle;margin-right:14px}
tr.po td{background:rgba(255,255,255,.06)}
td.r{opacity:.7;width:50px}td.n{width:420px}td.c{text-align:center}
.legend{position:absolute;bottom:110px;left:60px;font-size:20px;opacity:.7;font-weight:600}
"""
    trs = ""
    for r in rows[:15]:
        cls = "po" if r["rank"] <= 6 else ""
        trs += (f"<tr class='{cls}'><td class='r'>{r['rank']}</td><td class='n'><img src='{_e(r['logo'])}'>{_e(r['name'])}</td>"
                f"<td class='c'>{_e(r['wl'])}</td><td class='c'>{_e(r['pct'])}</td><td class='c'>{_e(r['gb'])}</td><td class='c'>{_e(r.get('streak', ''))}</td></tr>")
    body = f"""<div class='card'>
<div class='head'><span class='title'>{_e(conf_name)}</span><span class='date'>{_e(date_label)}</span></div>
<table><tr><th></th><th>БАГ</th><th style='text-align:center'>W-L</th><th style='text-align:center'>PCT</th><th style='text-align:center'>GB</th><th style='text-align:center'>СҮҮЛ</th></tr>{trs}</table>
<div class='legend'>Тодруулсан 6 баг — шууд playoff; 7-10 — play-in</div>
{_foot('Эх сурвалж: ESPN')}
</div>"""
    return render(_wrap(body, css))


# ============================================================
# МЭДЭЭНИЙ ТӨРӨЛ → ЗАГВАР
# ============================================================
_KIND_RES = [
    ("ТРЕЙД", re.compile(r"\btrade[ds]?\b|\bacquire[sd]?\b|\bswap\b", re.I)),
    ("ГЭРЭЭ", re.compile(r"\bcontract\b|\bextension\b|\bagree[sd]? to\b|\bsign(s|ed|ing)?\b|\bdeal\b|\bre-sign|\bwaive[sd]?\b|\brelease[sd]?\b", re.I)),
    ("ГЭМТЭЛ", re.compile(r"\binjur|\bout for\b|\bsidelined\b|\bsurgery\b|\btorn\b|\bsprain|\bfracture|\bmiss(es)? .*(game|week|season)", re.I)),
    ("ШИЙТГЭЛ", re.compile(r"\bsuspend|\bfine[sd]?\b|\bban(ned)?\b|\bejected\b", re.I)),
    ("РЕКОРД", re.compile(r"\brecord\b|\bfirst (player|time) (ever|in)|\bhistory\b|\bmilestone\b|\bcareer.high", re.I)),
]


def detect_badge(title: str, summary: str = "", category: str = "") -> str:
    if category == "mn_basketball":
        return "МОНГОЛЫН САГС"
    text = f"{title} {summary}"
    for badge, rx in _KIND_RES:
        if rx.search(text):
            return badge
    return "NBA МЭДЭЭ"


def extract_deal_numbers(text: str) -> list:
    """'5-year, $155M' → [('$155M','НИЙТ ДҮН'),('5','ЖИЛ'),('$31M','ЖИЛД ДУНДЖААР')]"""
    nums = []
    m = re.search(r"\$\s?(\d+(?:\.\d+)?)\s*(million|M\b|billion|B\b)", text, re.I)
    total = None
    if m:
        val = float(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("b"):
            val *= 1000
        total = val
        nums.append((f"${val:g}M" if val < 1000 else f"${val / 1000:g}B", "НИЙТ ДҮН"))
    y = re.search(r"(\d+)[- ]year", text, re.I)
    years = int(y.group(1)) if y else None
    if years:
        nums.append((str(years), "ЖИЛ"))
    if total and years and years > 0:
        nums.append((f"${total / years:.1f}M".replace(".0M", "M"), "ЖИЛД ДУНДЖААР"))
    return nums


def extract_chips(text: str) -> list:
    chips = []
    for v, l in extract_deal_numbers(text)[:2]:
        chips.append(f"{v} {l.lower()}" if l != "НИЙТ ДҮН" else v)
    m = re.search(r"(\d{2})-year-old", text)
    if m:
        chips.append(f"{m.group(1)} нас")
    m = re.search(r"(\d+)\s*(?:points|pts)\b", text, re.I)
    if m and len(chips) < 3:
        chips.append(f"{m.group(1)} оноо")
    return chips[:3]


def build_for_news(news: dict, written: dict, headline_mn: str, quote_mn: str = "",
                   entities: dict | None = None, photo: str = "") -> tuple:
    """Мэдээний төрлөөр загвар сонгож рендерлэнэ. (bytes, kind) эсвэл (b"", "").
    Өгөгдөл дутвал нэг шат доош: deal → news, quote → news."""
    entities = entities or {}
    src_text = f"{news.get('title', '')} {news.get('summary', '')} {news.get('og_description', '')} {news.get('body_excerpt', '')}"
    badge = detect_badge(news.get("title", ""), news.get("summary", ""), news.get("category", ""))
    source = news.get("source_name", "")
    date = news.get("published", "")[:10].replace("-", ".")
    accent = "#c8102e" if news.get("category") == "mn_basketball" else "#e63946"

    # 1) Гэрээ/трейд: тоглогч + баг + тоо бүгд байвал
    if badge in ("ГЭРЭЭ", "ТРЕЙД") and entities.get("athlete_id") and entities.get("team_id"):
        nums = extract_deal_numbers(src_text)
        if len(nums) >= 2:
            png = deal_card(
                name=entities.get("athlete_name", ""),
                role=entities.get("team_name", ""),
                headshot=f"https://a.espncdn.com/i/headshots/nba/players/full/{entities['athlete_id']}.png",
                team_logo=f"https://a.espncdn.com/i/teamlogos/nba/500/{entities['team_id']}.png",
                nums=nums, line=headline_mn, badge=badge, source=source or "ESPN")
            if png:
                return png, "deal"

    # 2) Ишлэл: бодит ишлэл (Монголоор) байвал
    if quote_mn and len(quote_mn) >= 40:
        who = entities.get("athlete_name") or ""
        if who:
            png = quote_card(quote_mn, who, entities.get("team_name", ""), photo=photo,
                             headshot=f"https://a.espncdn.com/i/headshots/nba/players/full/{entities['athlete_id']}.png" if entities.get("athlete_id") else "",
                             source=source or "ESPN")
            if png:
                return png, "quote"

    # 3) Мэдээ (эх зурагтай)
    if photo and headline_mn:
        article = written.get("article_mn", "")
        first = re.split(r"(?<=[.!?])\s+", article.strip())[0] if article else ""
        if first.strip() == headline_mn.strip():
            first = ""
        png = news_card(photo, badge, headline_mn, subtitle=first[:180], chips=extract_chips(src_text),
                        source=source, date=date, accent=accent)
        if png:
            return png, "news"
    return b"", ""
