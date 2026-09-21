"""
NBA тоглолтын үр дүн — ESPN-ийн нээлттэй scoreboard JSON-оос.

ЯАГААД: Хуудасны редакцийн бодлогын №1 нь "ДӨНГӨЖ ДУУССАН тоглолтын үр
дүн" боловч RSS дээр тоглолтын recap хэдэн цагийн дараа, тэр ч байтугай
тойм хэлбэрээр л ирдэг. Scoreboard API тоглолт дуусмагц оноо, багуудын
амжилт, шилдэг тоглогчдын stat line-ийг ӨГӨГДЛӨӨР өгдөг тул нийтлэл
БАРИМТААР дүүрэн, хэн ч бичээгүй ШИНЭ агуулга болно (RSS-ийн 1 өгүүлбэр
summary-гаас орчуулсан постоос эрс ялгаатай).

Хэрэглээ (main.py): fetch_finished_games() → ердийн мэдээний dict-ийн
жагсаалт (id, title, summary, url, category ...). Эдгээр ач холбогдлын
шүүлтүүрийг ДАВАХГҮЙ — үр дүн үргэлж постлогдоно.

ESPN-ийн энэ endpoint GitHub Actions-оос ажилладаг (espn_api.py-тэй ижил
хост); Монголын IP-ээс 403 өгдөг тул локал тест хийхгүй, CI-д шалгана.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger(__name__)

# 2026-09-21 probe: site.api.espn.com болон cdn.nba.com GitHub Actions-оос 403,
# харин site.web.api.espn.com (ижил зам, ESPN-ийн вэб апп-ын хост) 200.
ESPN_HOST = os.environ.get("ESPN_API_HOST", "https://site.web.api.espn.com")
SCOREBOARD_URL = f"{ESPN_HOST}/apis/site/v2/sports/basketball/nba/scoreboard"
SOURCE_NAME = "ESPN Scoreboard"
SEASON_TYPE_MN = {1: "бэлтгэл (preseason)", 2: "улирлын", 3: "playoff", 4: "off-season"}
LEADER_MN = {"points": "оноо", "rebounds": "самбар", "assists": "дамжуулалт", "rating": ""}


def game_id(event_id: str) -> str:
    return f"espn-game-{event_id}"


def _dates_to_check() -> list:
    """ESPN-ийн dates параметр АНУ-ын Зүүн эргийн өдрөөр. Монголын өглөө
    (UTC 0-6) АНУ-д өмнөх орой хэвээр байдаг тул UTC-6 цагаар өнөөдөр
    болон өчигдрийг шалгана — дуусаад удаагүй тоглолт алдагдахгүй."""
    override = os.environ.get("NBA_SCORES_DATES", "").strip()  # тест: "20260315,20260316"
    if override:
        return [d.strip() for d in override.split(",") if d.strip()]
    us_now = datetime.now(timezone.utc) - timedelta(hours=6)
    return [(us_now - timedelta(days=1)).strftime("%Y%m%d"), us_now.strftime("%Y%m%d")]


def _leaders_text(competitor: dict) -> str:
    parts = []
    for cat in competitor.get("leaders", []):
        name = cat.get("name", "")
        if name not in LEADER_MN or name == "rating":
            continue
        top = (cat.get("leaders") or [{}])[0]
        athlete = (top.get("athlete") or {}).get("displayName", "")
        value = top.get("displayValue", "")
        if athlete and value:
            parts.append(f"{athlete} {value} {name}")
    return "; ".join(parts)


def _record(competitor: dict) -> str:
    for rec in competitor.get("records", []):
        if rec.get("type") in ("total", None) or rec.get("name") == "overall":
            return rec.get("summary", "")
    recs = competitor.get("records", [])
    return recs[0].get("summary", "") if recs else ""


def _event_to_news(event: dict) -> dict | None:
    status = (event.get("status") or {}).get("type") or {}
    if not status.get("completed"):
        return None
    season_type = int(((event.get("season") or {}).get("type")) or 0)
    if season_type == 1:
        return None  # бэлтгэл тоглолтын үр дүн постлохгүй (сонирхол бага)

    comp = (event.get("competitions") or [{}])[0]
    teams = comp.get("competitors") or []
    if len(teams) != 2:
        return None
    home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
    away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
    try:
        home_score, away_score = int(home.get("score", 0)), int(away.get("score", 0))
    except (TypeError, ValueError):
        return None
    if home_score == 0 and away_score == 0:
        return None

    winner, loser = (home, away) if home_score > away_score else (away, home)
    w_score, l_score = max(home_score, away_score), min(home_score, away_score)
    w_name, l_name = winner["team"]["displayName"], loser["team"]["displayName"]
    period = int((event.get("status") or {}).get("period") or 4)
    ot = f" ({period - 4}OT)" if period > 4 else ""

    headline = ""
    for h in comp.get("headlines", []):
        headline = h.get("description") or h.get("shortLinkText") or ""
        if headline:
            break
    venue = ((comp.get("venue") or {}).get("fullName")) or ""
    notes = "; ".join(n.get("headline", "") for n in comp.get("notes", []) if n.get("headline"))

    title = f"{w_name} beat {l_name} {w_score}-{l_score}{ot}"
    facts = [
        f"FINAL{ot}: {away['team']['displayName']} {away_score} - {home['team']['displayName']} {home_score}"
        + (f" (at {venue})" if venue else ""),
        f"Season stage: {SEASON_TYPE_MN.get(season_type, 'улирлын')}" + (f". {notes}" if notes else ""),
        f"Records after the game: {w_name} {_record(winner)}, {l_name} {_record(loser)}",
    ]
    lw, ll = _leaders_text(winner), _leaders_text(loser)
    if lw:
        facts.append(f"{w_name} leaders: {lw}")
    if ll:
        facts.append(f"{l_name} leaders: {ll}")
    if headline:
        facts.append(f"ESPN headline: {headline}")

    url = ""
    for link in event.get("links", []) or []:
        if link.get("href"):
            url = link["href"]
            break
    if not url:
        url = f"https://www.espn.com/nba/game/_/gameId/{event.get('id', '')}"

    return {
        "id": game_id(str(event.get("id", ""))),
        "category": "basketball",
        "category_mn": "NBA",
        "category_emoji": "🏀",
        "source_name": SOURCE_NAME,
        "title": title,
        "summary": ". ".join(facts) + ".",
        "url": url,
        "image_url": "",
        "published": event.get("date", ""),
        "published_ts": datetime.now(timezone.utc).timestamp(),  # дөнгөж дууссан → хамгийн эхэнд
        "kind": "game_recap",
        "lang": "en",
    }


NBA_CDN_URL = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"


def _nba_cdn_games() -> list:
    """NBA-ийн албан ёсны CDN JSON (өнөөдрийн тоглолтууд, АНУ-ын өдрөөр).
    ESPN datacenter IP-г хаах үед (2026-09-21: Actions-оос 403) нөөц.
    Бүтэц: scoreboard.games[] {gameId, gameStatus 3=final, period,
    homeTeam/awayTeam {teamCity, teamName, score, wins, losses},
    gameLeaders {homeLeaders/awayLeaders {name, points, rebounds, assists}}}."""
    resp = requests.get(NBA_CDN_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    games = []
    for g in resp.json().get("scoreboard", {}).get("games", []):
        if int(g.get("gameStatus", 0)) != 3:
            continue
        home, away = g.get("homeTeam", {}), g.get("awayTeam", {})
        hs, as_ = int(home.get("score", 0)), int(away.get("score", 0))
        if hs == 0 and as_ == 0:
            continue
        hn = f"{home.get('teamCity', '')} {home.get('teamName', '')}".strip()
        an = f"{away.get('teamCity', '')} {away.get('teamName', '')}".strip()
        winner_home = hs > as_
        w_name, l_name = (hn, an) if winner_home else (an, hn)
        w_score, l_score = max(hs, as_), min(hs, as_)
        period = int(g.get("period", 4) or 4)
        ot = f" ({period - 4}OT)" if period > 4 else ""
        leaders = g.get("gameLeaders", {}) or {}

        def _ld(key):
            l = leaders.get(key) or {}
            if not l.get("name"):
                return ""
            return f"{l['name']} {l.get('points', 0)} points, {l.get('rebounds', 0)} rebounds, {l.get('assists', 0)} assists"

        facts = [
            f"FINAL{ot}: {an} {as_} - {hn} {hs} (home: {hn})",
            f"Records after the game: {hn} {home.get('wins', '?')}-{home.get('losses', '?')}, "
            f"{an} {away.get('wins', '?')}-{away.get('losses', '?')}",
        ]
        if _ld("homeLeaders"):
            facts.append(f"{hn} top performer: {_ld('homeLeaders')}")
        if _ld("awayLeaders"):
            facts.append(f"{an} top performer: {_ld('awayLeaders')}")
        games.append({
            "id": game_id(str(g.get("gameId", ""))),
            "category": "basketball",
            "category_mn": "NBA",
            "category_emoji": "🏀",
            "source_name": "NBA.com Scoreboard",
            "title": f"{w_name} beat {l_name} {w_score}-{l_score}{ot}",
            "summary": ". ".join(facts) + ".",
            "url": f"https://www.nba.com/game/{g.get('gameId', '')}",
            "image_url": "",
            "published": g.get("gameTimeUTC", ""),
            "published_ts": datetime.now(timezone.utc).timestamp(),
            "kind": "game_recap",
            "lang": "en",
        })
    return games


def fetch_finished_games(posted_ids: set | None = None) -> list:
    """Дууссан (FINAL) NBA тоглолтуудыг мэдээний dict болгон буцаана.
    posted_ids өгвөл аль хэдийн постолсныг хасна. Алдаа гарвал хоосон
    жагсаалт — RSS урсгалыг хэзээ ч зогсоохгүй."""
    posted_ids = posted_ids or set()
    games = []
    espn_failed = False
    for date in _dates_to_check():
        try:
            resp = requests.get(SCOREBOARD_URL, params={"dates": date}, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            events = resp.json().get("events", [])
        except Exception as e:
            log.warning(f"[NBA SCORES] scoreboard {date} алдаа: {e}")
            espn_failed = True
            continue
        for event in events:
            try:
                news = _event_to_news(event)
            except Exception as e:
                log.warning(f"[NBA SCORES] event задлахад алдаа: {e}")
                continue
            if news and news["id"] not in posted_ids and all(g["id"] != news["id"] for g in games):
                games.append(news)
    if not games and espn_failed:
        # ESPN хаагдсан бол NBA-ийн CDN (ESPN хариулсан ч тоглолт байхгүй бол оролдохгүй)
        try:
            for news in _nba_cdn_games():
                if news["id"] not in posted_ids and all(g["id"] != news["id"] for g in games):
                    games.append(news)
            log.info("[NBA SCORES] NBA.com CDN шалгав")
        except Exception as e:
            log.warning(f"[NBA SCORES] NBA.com CDN алдаа: {e}")
    if games:
        log.info(f"[NBA SCORES] Дууссан, постлоогүй тоглолт: {len(games)} — " +
                 "; ".join(g["title"] for g in games[:4]))
    else:
        log.info("[NBA SCORES] Шинэ дууссан тоглолт алга")
    return games
