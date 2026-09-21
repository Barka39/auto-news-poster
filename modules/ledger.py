"""
Постын дэвтэр (S3): постлогдсон зүйл бүрийн id, төрөл, оноо, эх сурвалж, цаг,
дараа нь Facebook insights (reach, reaction, share, comment, click).

ЯАГААД: аль төрлийн пост (recap / гэрээ / Монголын сагс / тойм), аль цагийн слот
уншигддагийг мэдэхгүй бол босго, слот, форматыг таамгаар тохируулна. Ledger =
хэмжилтийн гогцооны цорын ганц эх сурвалж; insights_report.py үүнийг уншиж
Telegram-д долоо хоногийн тайлан илгээнэ.

Файл: ledger.json (workflow-ийн commit алхамд posted_ids.json-тэй хамт орно).
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

LEDGER_FILE = "ledger.json"
MAX_ENTRIES = 600


def load() -> list:
    if not os.path.exists(LEDGER_FILE):
        return []
    try:
        with open(LEDGER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("posts", []) if isinstance(data, dict) else data
    except Exception as e:
        log.error(f"ledger ачааллахад алдаа: {e}")
        return []


def save(posts: list):
    try:
        posts = posts[-MAX_ENTRIES:]
        with open(LEDGER_FILE, "w", encoding="utf-8") as f:
            json.dump({"posts": posts}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        log.error(f"ledger хадгалахад алдаа: {e}")


def record(news: dict, result: dict, extra: dict | None = None):
    """Амжилттай постлосны дараа нэг бичлэг нэмнэ (draft горимд алгасна)."""
    if os.environ.get("AUTONEWS_DRAFT_DIR") or not result.get("success"):
        return
    platforms = result.get("platforms") or {}
    fb = platforms.get("facebook") or {}
    ig = platforms.get("instagram") or {}
    entry = {
        "ts": time.time(),
        "fb_id": fb.get("id", ""),
        "ig_id": ig.get("id", "") if ig.get("id") else "",
        "kind": news.get("kind") or ("mn" if news.get("category") == "mn_basketball" else "news"),
        "card": news.get("card_kind", ""),
        "video": bool(news.get("video_posted")),
        "score": news.get("score", 0),
        "category": news.get("category", ""),
        "source": news.get("source_name", ""),
        "title": (news.get("title") or "")[:120],
        "url": news.get("url", ""),
        "scheduled_for": news.get("scheduled_publish_time", 0),
        "slot": news.get("slot", ""),
        "chars": len(news.get("article_mn", "") or ""),
    }
    if extra:
        entry.update(extra)
    posts = load()
    posts.append(entry)
    save(posts)
    log.info(f"📒 ledger: {entry['kind']}/{entry['card'] or '-'} fb={entry['fb_id'] or '-'}")
