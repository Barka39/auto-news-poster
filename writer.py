"""
Нийтлэл бичих модуль — Groq API (үнэгүй)
Llama-д зохиомж бичүүлэхгүй — зөвхөн ОРЧУУЛГА + бага зэрэг найруулга хийлгэнэ.
Гаралтын чанарыг автоматаар шалгаж, муу бол Google Translate руу шилжинэ.
"""

import os
import re
import logging
import requests

log = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are a senior Mongolian journalist and professional English-to-Mongolian news translator.

Translate English news into natural Mongolian suitable for Telegram.

RULES:
1. Never invent facts.
2. Rewrite naturally instead of word-for-word.
3. Keep all person names, companies, teams, bands, products and organizations exactly in English.
4. Translate countries and cities into Mongolian.
5. If the source is short, improve flow only. Never add new facts.
6. Output 3-5 short paragraphs.
7. No title.
8. No markdown.
9. Output only Mongolian."""


def _cyrillic_ratio(text: str) -> float:
    """Текст доторх кирилл үсгийн харьцаа (латин нэрсийг тооцохгүй чанарын хэмжүүр)"""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    cyr = [c for c in letters if "\u0400" <= c <= "\u04FF"]
    return len(cyr) / len(letters)


def _clean_output(text: str) -> str:
    """Groq гаралтаас илүүдэл зүйлс арилгах"""
    text = text.strip()
    # Markdown fence арилгах
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        text = text.strip()
    # Эхний мөр нь "Орчуулга:", "Here is..." маягийн preamble бол хасна
    lines = text.split("\n")
    if lines and (lines[0].strip().endswith(":") or
                  re.match(r"^(here|орчуулга|нийтлэл|translation)", lines[0].strip(), re.IGNORECASE)):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _is_good_mongolian(text: str) -> bool:
    if len(text.split()) < 60:
        return False
    if _cyrillic_ratio(text) < 0.65:
        return False
    for bad in ["Here is","Translation","Орчуулга","Монгол орчуулга","Sure!","Certainly"]:
        if bad.lower() in text.lower():
            return False
    return True


def write_article(news: dict) -> dict:
    """
    Groq-оор мэдээг Монгол руу орчуулна (нэрсийг Англи хэвээр).
    Чанар хангалтгүй эсвэл алдаа гарвал Google Translate fallback.
    """
    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        log.warning("GROQ_API_KEY байхгүй — Google Translate ашиглана")
        return _fallback(news)

    user_prompt = f"""Translate the following news into fluent Mongolian.

Title:
{news['title']}

Content:
{news.get('summary','')}

Requirements:
- Natural Mongolian.
- No title.
- No explanation.
- Do not invent facts.
- Write 3-5 short paragraphs.
"""

    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 700
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        article_text = _clean_output(data["choices"][0]["message"]["content"])

        # ЧАНАРЫН ШАЛГАЛТ — муу бол Google Translate руу
        if not _is_good_mongolian(article_text):
            log.warning(f"Groq гаралт чанаргүй ({len(article_text)} тэмдэгт, "
                        f"кирилл {_cyrillic_ratio(article_text):.0%}) — Google Translate руу шилжлээ")
            return _fallback(news)

        news["article_mn"] = article_text
        log.info(f"Groq орчуулга OK: {article_text[:60]}...")
        return news

    except Exception as e:
        log.error(f"Groq API алдаа: {e} — Google Translate руу шилжлээ")
        return _fallback(news)


def _fallback(news: dict) -> dict:
    """Google Translate fallback"""
    from modules.translator import translate_to_mongolian
    translated = translate_to_mongolian(news)
    article = translated.get("summary_mn","").strip()
    if len(article.split()) < 40:
        article = (
            translated.get("title_mn","")
            + "\n\n"
            + translated.get("summary_mn","")
        )
    news["article_mn"] = article
    return news
