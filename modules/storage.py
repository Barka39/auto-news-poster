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

        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump({"posted_ids": ids_list, "posted_topics": topics},
                      f, ensure_ascii=False, indent=2)

        log.info(f"{len(ids_list)} ID хадгалагдлаа")

    except Exception as e:
        log.error(f"ID хадгалахад алдаа: {e}")
