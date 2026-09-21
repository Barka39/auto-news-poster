"""
Давтагддаг NBA формат (S2): "Өглөөний NBA" (шөнийн бүх үр дүн нэг постонд) ба
долоо хоногийн бүсийн байрлал (standings).

ЯАГААД: уншигч хүлээдэг, хуваалцдаг давтамжтай контент; тоглолт олонтой шөнө
10 тусдаа recap-аар feed-ийг бөглөхийн оронд нэг карт + богино тайлбар.
Ганцаарчилсан recap зөвхөн онцгой тоглолтод (playoff, OT, 3 хүртэлх онооны
зөрүү) үлдэнэ — main.py-ийн should_post_recap().

Өгөгдөл: nba_scores (scoreboard), ESPN standings (site.web.api).
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import requests

from modules import nba_scores, cards, gemini_compare

log = logging.getLogger(__name__)

UB = timezone(timedelta(hours=8))
STANDINGS_URL = f"{nba_scores.ESPN_HOST}/apis/v2/sports/basketball/nba/standings"


# ============================================================
# ӨГЛӨӨНИЙ NBA
# ============================================================
def should_post_recap(news: dict) -> bool:
    """Ганцаарчилсан recap: playoff, OT, эсвэл 3 хүртэлх онооны зөрүү.
    Бусад нь өглөөний тоймд орно. NBA_RECAP_ALL=1 бол бүгд (хуучин зан)."""
    if os.environ.get("NBA_RECAP_ALL") == "1":
        return True
    card = news.get("card") or {}
    return bool(card.get("ot")) or card.get("season_type") == 3 or int(card.get("margin", 99)) <= 3


def _digest_rows(games: list) -> list:
    rows = []
    for g in games:
        c = g.get("card") or {}
        if not c:
            continue
        rows.append({"away": c["away"], "home": c["home"], "top": c.get("top", ""), "ot": bool(c.get("ot"))})
    return rows


def _digest_text(games: list, date_label: str) -> str:
    lines = []
    for g in games:
        c = g.get("card") or {}
        a, h = c.get("away", {}), c.get("home", {})
        w, l = (a, h) if a.get("winner") else (h, a)
        ot = " (OT)" if c.get("ot") else ""
        top = f" — {c['top']}" if c.get("top") else ""
        lines.append(f"🏀 {w['name']} {w['score']}:{l['score']} {l['name']}{ot}{top}")
    body = "\n".join(lines)
    intro = ""
    if gemini_compare.is_enabled():
        facts = "\n".join(f"{(g.get('card') or {}).get('away', {}).get('name')} {(g.get('card') or {}).get('away', {}).get('score')} - "
                          f"{(g.get('card') or {}).get('home', {}).get('name')} {(g.get('card') or {}).get('home', {}).get('score')}; "
                          f"top: {(g.get('card') or {}).get('top', '')}" for g in games)
        try:
            intro = gemini_compare.generate(
                "Чи Монголын спортын редактор. Зөвхөн өгөгдсөн баримтаар, 2 БОГИНО өгүүлбэрээр "
                "шөнийн NBA-ийн хамгийн сонирхолтой 1-2 зүйлийг Монголоор бич (нэрс Латинаар, тоо баримт хэвээр). "
                "Зохиож бүү нэм. Зөвхөн текст.",
                f"Огноо: {date_label}\nТоглолтууд:\n{facts}") or ""
            intro = intro.strip()
        except Exception as e:
            log.warning(f"Тоймын танилцуулга (Gemini) алдаа: {e}")
    head = f"ӨГЛӨӨНИЙ NBA · {date_label}\n"
    return (head + (intro + "\n\n" if intro else "\n") + body + "\n\n#NBA #ӨглөөнийNBA").strip()


def build_morning(posted_ids: set) -> dict | None:
    """Шөнийн бүх дууссан тоглолт → нэг постын dict (текст + карт). Тоглолт байхгүй бол None."""
    games = nba_scores.fetch_finished_games(set())
    games = [g for g in games if g.get("card")]
    if not games:
        return None
    date_label = datetime.now(UB).strftime("%Y.%m.%d")
    png = cards.digest_card(_digest_rows(games), date_label)
    post = {
        "id": "nba-digest-" + datetime.now(UB).strftime("%Y%m%d"),
        "kind": "digest",
        "category": "basketball",
        "category_mn": "NBA",
        "category_emoji": "🏀",
        "source_name": "ESPN Scoreboard",
        "title": f"Morning NBA {date_label}: {len(games)} games",
        "title_mn": f"Өглөөний NBA · {date_label}",
        "article_mn": _digest_text(games, date_label),
        "image_url": "",
        "image_bytes": png,
        "card_kind": "digest" if png else "",
        "game_ids": [g["id"] for g in games],
        "url": "",
    }
    log.info(f"🌅 Өглөөний NBA: {len(games)} тоглолт, карт {'OK' if png else 'АЛГА'}")
    return post


# ============================================================
# БҮСИЙН БАЙРЛАЛ
# ============================================================
def fetch_standings() -> list:
    """[{conf, rows:[{rank, logo, name, wl, pct, gb, streak}]}]"""
    params = {}
    if os.environ.get("NBA_STANDINGS_SEASON"):   # тест: 2026 = 2025-26 улирал
        params["season"] = os.environ["NBA_STANDINGS_SEASON"]
    resp = requests.get(STANDINGS_URL, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    out = []
    for conf in resp.json().get("children", []):
        rows = []
        for e in conf.get("standings", {}).get("entries", []):
            st = {s.get("name"): s.get("displayValue", "") for s in e.get("stats", [])}
            tm = e.get("team", {})
            logos = tm.get("logos") or [{}]
            try:
                seed = int(st.get("playoffSeed") or 0)
            except ValueError:
                seed = 0
            rows.append({"rank": seed, "logo": logos[0].get("href", ""), "name": tm.get("displayName", ""),
                         "wl": st.get("overall") or f"{st.get('wins', '')}-{st.get('losses', '')}",
                         "pct": st.get("winPercent", ""), "gb": st.get("gamesBehind", ""), "streak": st.get("streak", "")})
        rows.sort(key=lambda r: r["rank"] or 99)
        name_mn = {"Eastern Conference": "ЗҮҮН БҮС", "Western Conference": "БАРУУН БҮС"}.get(conf.get("name"), conf.get("name", ""))
        out.append({"conf": name_mn, "rows": rows})
    return out


def build_standings() -> list:
    """Бүс бүрд нэг постын dict (карт + богино текст)."""
    posts = []
    date_label = datetime.now(UB).strftime("%Y.%m.%d")
    try:
        confs = fetch_standings()
    except Exception as e:
        log.warning(f"standings алдаа: {e}")
        return posts
    for c in confs:
        if not c["rows"] or not any(r["rank"] for r in c["rows"]):
            continue
        png = cards.standings_card(c["conf"], c["rows"], date_label)
        top3 = ", ".join(f"{r['name']} ({r['wl']})" for r in c["rows"][:3])
        posts.append({
            "id": f"nba-standings-{c['conf'][:1]}-{datetime.now(UB).strftime('%Y%m%d')}",
            "kind": "standings", "category": "basketball", "category_mn": "NBA", "category_emoji": "🏀",
            "source_name": "ESPN", "title": f"NBA standings {c['conf']} {date_label}",
            "title_mn": f"NBA {c['conf'].title()} · {date_label}",
            "article_mn": f"NBA · {c['conf']} · {date_label}\nТэргүүлэгчид: {top3}.\nТодруулсан 6 баг шууд playoff, 7-10 play-in.\n\n#NBA #Standings",
            "image_url": "", "image_bytes": png, "card_kind": "standings" if png else "", "url": "",
        })
    return posts
