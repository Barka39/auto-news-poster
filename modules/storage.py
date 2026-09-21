"""
Хадгалах модуль — постолсон мэдээний ID-уудыг хадгалах
GitHub Actions-д файл системд хадгалдаг (run тус бүрт reset хийгдэнэ)
Тиймээс GitHub repository-н posted_ids.json файлд хадгална
"""

import os
import json
import logging

log = logging.getLogger(__name__)

STORAGE_FILE = "posted_ids.json"
MAX_IDS = 500  # Хуучин ID-уудыг цэвэрлэх хязгаар
TOPIC_TTL_HOURS = 48  # Сэдвийн давхардлыг шалгах хугацааны цонх


def load_posted_topics() -> list:
    """
    Сүүлийн 48 цагт постолсон мэдээний ЭХ ГАРЧГУУДЫГ ачаална.
    Зорилго: ӨӨР сайтаас ирсэн ИЖИЛ сэдвийн мэдээг (URL нь өөр тул
    ID давхардал барьж чадахгүй) сэдвийн түвшинд таньж алгасах.
    Буцаах утга: [{"title": str, "ts": float}, ...]
    """
    import time
    if not os.path.exists(STORAGE_FILE):
        return []
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        now = time.time()
        topics = [
            t for t in data.get("posted_topics", [])
            if now - t.get("ts", 0) < TOPIC_TTL_HOURS * 3600
        ]
        log.info(f"{len(topics)} сэдвийн гарчиг ачааллаа (сүүлийн {TOPIC_TTL_HOURS}ц)")
        return topics
    except Exception as e:
        log.error(f"Сэдэв ачааллахад алдаа: {e}")
        return []


def load_posted() -> set:
    """Өмнө постолсон мэдээний ID-уудыг ачаалах"""
    if not os.path.exists(STORAGE_FILE):
        log.info(f"{STORAGE_FILE} байхгүй — шинэ эхлэж байна")
        return set()

    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            ids = set(data.get("posted_ids", []))
            log.info(f"{len(ids)} ID ачааллаа")
            return ids
    except Exception as e:
        log.error(f"ID ачааллахад алдаа: {e}")
        return set()


def save_posted(posted_ids: set, posted_topics: list = None):
    """Постолсон ID болон сэдвийн гарчгуудыг хадгалах.

    Хоёуланг НЭГ posted_ids.json файлд хадгална — workflow-ийн
    `git add posted_ids.json` алхмыг өөрчлөх шаардлагагүй."""
    import time
    try:
        # Хэт олон болвол хуучнийг хасах (сүүлийн MAX_IDS-г хадгалах)
        ids_list = list(posted_ids)
        if len(ids_list) > MAX_IDS:
            ids_list = ids_list[-MAX_IDS:]
            log.info(f"ID жагсаалтыг {MAX_IDS}-д хязгаарлалаа")

        now = time.time()
        topics = [
            t for t in (posted_topics or [])
            if now - t.get("ts", 0) < TOPIC_TTL_HOURS * 3600
        ]

        # Бусад талбарыг (slots — S1 товлолт, alerts — Telegram хаалт) ХАДГАЛНА.
        # Урьд нь бүхэлд нь дарж бичдэг байсан тул слот бүр run бүрд мартагдаж,
        # нэг слотод хоёр пост товлогдох эрсдэлтэй байв (2026-09-21).
        extra = {}
        try:
            if os.path.exists(STORAGE_FILE):
                with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                    old = json.load(f)
                extra = {k: v for k, v in old.items() if k not in ("posted_ids", "posted_topics")}
        except Exception:
            extra = {}
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump({**extra, "posted_ids": ids_list, "posted_topics": topics},
                      f, ensure_ascii=False, indent=2)

        log.info(f"{len(ids_list)} ID хадгалагдлаа")

    except Exception as e:
        log.error(f"ID хадгалахад алдаа: {e}")


ALERT_INTERVAL_HOURS = 12  # Нэг шалтгааны 🛑 мэдэгдлийг хамгийн олондоо 12 цаг тутам


def alert_due(key: str) -> bool:
    """Зогсолтын мэдэгдлийг (жишээ нь token дууссан) 5-15 минут тутмын run
    бүр дээр давтахгүй — сүүлд илгээснээс ALERT_INTERVAL_HOURS өнгөрсөн
    бол True буцааж, цагийг posted_ids.json-ийн "alerts" талбарт бичнэ
    (ижил файл тул workflow-ийн git add алхам өөрчлөгдөхгүй)."""
    import time
    data = {}
    try:
        if os.path.exists(STORAGE_FILE):
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception as e:
        log.error(f"alert_due ачааллахад алдаа: {e}")
        return True
    alerts = data.get("alerts", {})
    now = time.time()
    if now - alerts.get(key, 0) < ALERT_INTERVAL_HOURS * 3600:
        return False
    alerts[key] = now
    data["alerts"] = alerts
    try:
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"alert_due хадгалахад алдаа: {e}")
    return True
