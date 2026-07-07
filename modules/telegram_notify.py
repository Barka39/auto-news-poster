"""
Telegram мэдэгдлийн модуль (сонголт, backward compatible).

TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID тохируулсан үед л идэвхжинэ.
ХҮЛЭЭХГҮЙ, ХАРИУ ШААРДАХГҮЙ — постолсны дараа зөвхөн "ийм пост орлоо"
гэсэн мэдэгдэл илгээгээд шууд үргэлжилнэ. Тохируулаагүй бол энэ давхарга
бүрэн алгасагдана.
"""

import os
import logging
import requests

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def is_enabled() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def notify_posted(news: dict, success: bool):
    """
    Постолсны дараа Telegram-руу товч мэдэгдэл илгээнэ.
    Алдаа гарвал зөвхөн лог хийгээд өнгөрнө — үндсэн ажиллагааг
    хэзээ ч зогсоохгүй, хэзээ ч хүлээхгүй.
    """
    if not is_enabled():
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    title = news.get("title_mn") or news.get("title", "")
    category = news.get("category_mn", "")
    status_emoji = "✅" if success else "⚠️"
    status_text = "Постлогдлоо" if success else "Постлоход алдаа гарлаа"

    text = f"{status_emoji} {status_text} [{category}]\n{title[:150]}"

    try:
        url = TELEGRAM_API.format(token=token, method="sendMessage")
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        log.warning(f"Telegram мэдэгдэл илгээхэд алдаа (үл тоомсорлов): {e}")
