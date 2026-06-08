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


def save_posted(posted_ids: set):
    """Постолсон ID-уудыг хадгалах"""
    try:
        # Хэт олон болвол хуучнийг хасах (сүүлийн MAX_IDS-г хадгалах)
        ids_list = list(posted_ids)
        if len(ids_list) > MAX_IDS:
            ids_list = ids_list[-MAX_IDS:]
            log.info(f"ID жагсаалтыг {MAX_IDS}-д хязгаарлалаа")

        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump({"posted_ids": ids_list}, f, ensure_ascii=False, indent=2)

        log.info(f"{len(ids_list)} ID хадгалагдлаа")

    except Exception as e:
        log.error(f"ID хадгалахад алдаа: {e}")
