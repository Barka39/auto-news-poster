"""
Постын цагийн товлолт (S1): run хэзээ ажилласнаас үл хамааран пост Монголын
уншигчийн идэвхтэй цагт гарна.

ЯАГААД: GitHub cron шахагддаг (өдөрт 8–10 run, 1.5–5 цагийн зайтай) тул постууд
бөөгнөрч, шөнө дунд гарч байсан. Facebook Graph API `published=false` +
`scheduled_publish_time` (10 минутаас 75 хоногийн хооронд)-аар постыг
урьдчилан товлож болно.

Дүрэм:
- Тоглолтын үр дүн (kind=game_recap) болон 10 оноотой мэдээ → ШУУД.
- Бусад → дараагийн ЧӨЛӨӨТЭЙ слот (POST_SLOTS, УБ цаг). Нэг слотод нэг пост.
  Бүх слот дүүрсэн бол маргаашийн эхний слот; 36 цагаас хол бол шууд постолно
  (хуучирна).
- Ашигласан слотууд posted_ids.json-ийн "slots" талбарт: {"2026-09-22": ["08:00", ...]}.
- SCHEDULE_POSTS=0 бол бүгд шууд (хуучин зан).
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

UB = timezone(timedelta(hours=8))
STORAGE_FILE = "posted_ids.json"
DEFAULT_SLOTS = "08:00,11:00,13:00,16:00,19:00,21:30"
MIN_LEAD_MIN = 12          # FB доод хязгаар 10 минут; жаахан нөөц
MAX_AHEAD_H = 36           # үүнээс хол слот бол мэдээ хуучирна → шууд


def enabled() -> bool:
    return os.environ.get("SCHEDULE_POSTS", "1") != "0"


def slots() -> list:
    out = []
    for s in os.environ.get("POST_SLOTS", DEFAULT_SLOTS).split(","):
        s = s.strip()
        if s and ":" in s:
            hh, mm = s.split(":")
            out.append((int(hh), int(mm)))
    return sorted(out)


def _load_used() -> dict:
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("slots", {}) or {}
    except Exception:
        return {}


def _save_used(used: dict):
    try:
        data = {}
        if os.path.exists(STORAGE_FILE):
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        # хуучин өдрүүдийг цэвэрлэнэ
        keep_from = (datetime.now(UB) - timedelta(days=2)).strftime("%Y-%m-%d")
        data["slots"] = {d: v for d, v in used.items() if d >= keep_from}
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"slots хадгалахад алдаа: {e}")


def immediate(news: dict) -> bool:
    return news.get("kind") in ("game_recap", "digest", "standings") or float(news.get("score", 0) or 0) >= 10


def next_slot(now: datetime | None = None) -> tuple:
    """(unix_ts, label) — дараагийн чөлөөтэй слот; байхгүй/хол бол (0, '')."""
    now = now or datetime.now(UB)
    used = _load_used()
    for day_offset in (0, 1):
        day = (now + timedelta(days=day_offset)).date()
        key = day.strftime("%Y-%m-%d")
        for hh, mm in slots():
            label = f"{hh:02d}:{mm:02d}"
            if label in used.get(key, []):
                continue
            when = datetime(day.year, day.month, day.day, hh, mm, tzinfo=UB)
            if when < now + timedelta(minutes=MIN_LEAD_MIN):
                continue
            if when > now + timedelta(hours=MAX_AHEAD_H):
                return 0, ""
            used.setdefault(key, []).append(label)
            _save_used(used)
            return int(when.timestamp()), f"{key} {label}"
    return 0, ""


def assign(news: dict) -> dict:
    """news-д scheduled_publish_time / slot талбар нэмнэ (шууд бол нэмэхгүй)."""
    if not enabled() or immediate(news) or os.environ.get("AUTONEWS_DRAFT_DIR"):
        return news
    ts, label = next_slot()
    if ts:
        news["scheduled_publish_time"] = ts
        news["slot"] = label
        log.info(f"🕒 Товлов: {label} (УБ) — {news.get('title', '')[:50]}")
    else:
        log.info("🕒 Тохирох слот алга — шууд постолно")
    return news
