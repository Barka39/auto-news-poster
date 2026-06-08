"""
Орчуулах модуль — Google Translate (үнэгүй)
API key шаардахгүй, хязгааргүй ашиглах боломжтой
"""

import logging
from deep_translator import GoogleTranslator

log = logging.getLogger(__name__)


def google_translate(text: str) -> str:
    """Google Translate-ээр орчуулах"""
    if not text or not text.strip():
        return ""
    try:
        result = GoogleTranslator(source="en", target="mn").translate(text)
        return result or text
    except Exception as e:
        log.warning(f"Google Translate алдаа: {e} — эх текст ашиглана")
        return text


def translate_to_mongolian(news: dict) -> dict:
    """
    Мэдээг Монгол хэлрүү орчуулах
    Google Translate — үнэгүй, API key шаардахгүй
    """
    title_en = news.get("title", "")
    summary_en = news.get("summary", "")

    log.info(f"Орчуулж байна: {title_en[:60]}...")

    news["title_mn"] = google_translate(title_en)
    news["summary_mn"] = google_translate(summary_en)

    log.info(f"Дууслаа: {news['title_mn'][:60]}")
    return news
