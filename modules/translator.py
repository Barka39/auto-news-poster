"""
Орчуулах модуль — Google Translate (үнэгүй)
API key шаардахгүй. Алдаа гарвал 2 удаа дахин оролдож,
бүрэн бүтэлгүйтвэл ХООСОН буцаана (англи текст чимээгүй
дамжуулахгүйн тулд — энэ нь буруу постын гол шалтгаан байсан).
"""

import time
import logging
from deep_translator import GoogleTranslator

log = logging.getLogger(__name__)


def google_translate(text: str, retries: int = 2) -> str:
    """Google Translate-ээр орчуулах, алдаа гарвал дахин оролдоно"""
    if not text or not text.strip():
        return ""

    for attempt in range(retries):
        try:
            result = GoogleTranslator(source="en", target="mn").translate(text)
            if result and result.strip():
                return result
        except Exception as e:
            log.warning(f"Google Translate алдаа (оролдлого {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2)

    log.error(f"Google Translate бүрэн бүтэлгүйтлээ: {text[:40]}...")
    return ""  # Англи текст буцаахгүй — хоосон буцааж дуудагч талд мэдэгдэнэ


def translate_to_mongolian(news: dict) -> dict:
    """Мэдээг Монгол хэлрүү орчуулах (Groq боломжгүй үеийн fallback)"""
    title_en = news.get("title", "")
    summary_en = news.get("summary", "")

    log.info(f"Орчуулж байна: {title_en[:60]}...")

    news["title_mn"] = google_translate(title_en)
    news["summary_mn"] = google_translate(summary_en)

    if news["title_mn"]:
        log.info(f"Дууслаа: {news['title_mn'][:60]}")
    else:
        log.error("Орчуулга бүтэлгүйтлээ")

    return news
