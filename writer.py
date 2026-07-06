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

SYSTEM_PROMPT = """You are a professional English-to-Mongolian news translator.

STRICT RULES:
1. TRANSLATE the given news into natural Mongolian (Cyrillic). Do NOT invent facts that are not in the source.
2. Keep ALL person names, team names, band names, company names, league names in English/Latin script exactly as written (e.g. Embiid, Lakers, NBA, Taylor Swift, Reuters). NEVER transliterate names into Cyrillic.
3. Country and city names should be written in Mongolian (London -> Лондон, Beijing -> Бээжин).
4. Format the output as 2-4 short paragraphs or dash (-) bullet lines. No title/headline line.
5. Output ONLY the Mongolian translation. No preamble, no explanation, no quotes, no JSON, no markdown fences, no English sentences."""


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
    """
    Гаралт хангалттай сайн Монгол текст мөн үү?
    - 80+ тэмдэгт урттай
    - Үсгийн 50%+ нь кирилл (нэрс латин байж болох тул 50% хангалттай)
    """
    if len(text) < 80:
        return False
    if _cyrillic_ratio(text) < 0.5:
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

    user_prompt = f"""Translate this news into Mongolian following the rules.

TITLE: {news['title']}
CONTENT: {news.get('summary', '')}"""

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
    """Google Translate-ээр энгийн орчуулга"""
    from modules.translator import translate_to_mongolian
    translated = translate_to_mongolian(news)
    article = f"{translated.get('title_mn', '')}\n\n{translated.get('summary_mn', '')}"
    news["article_mn"] = article.strip()
    return news
