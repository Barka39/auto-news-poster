"""
Нийтлэл бичих модуль — Groq API (үнэгүй)
RSS-ийн товч мэдээллийг Монгол хэлээр дэлгэрэнгүй, өргөжүүлсэн
нийтлэл болгож дахин бичнэ (эх сурвалж/линк дурдахгүй).
Гаралтын чанарыг автоматаар шалгаж, англи хэл холилдсон бол
дахин оролдож, эцэст нь бүрэн бүтэлгүйтвэл алгасна (муу пост гарахгүй).
"""

import os
import re
import logging
import requests

log = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPTS = {
    "sports": """Чи Монгол спортын сонирхолтой контент бичигч. Reddit/фэн хэсгийн
дотоод хэллэгээр, дэлгэрэнгүй дүн шинжилгээтэй бичдэг.

ДҮРЭМ:
- Өгөгдсөн мэдээллийг ашиглаж, ДЭЛГЭРЭНГҮЙ, өргөжүүлсэн 3-5 догол мөр/зураас бич
- ШИНЭ баримт, тоо статистик БҮҮ зохио — зөвхөн өгөгдсөн мэдээлэлд байгаа зүйлийг өргөжүүлж тайлбарла
- Тоглогч, багийн нэрийг ЗААВАЛ Англи үсгээр бич (жишээ: Embiid, Lakers, NBA) — Монгол галиг хэрэглэхгүй
- Гарчиг, эх сурвалж, линк БҮҮ дурд
- Бүх өгүүлбэрийг МОНГОЛ хэлээр бич (нэрсээс бусад)
- Хөнгөн, ярианы хэллэгээр, шаардлагатай бол emoji хэрэглэ""",

    "music": """Чи Монгол хөгжим/шоу бизнесийн контент бичигч. Залуучуудын
хэллэгээр, сонирхолтой байдлаар бичдэг.

ДҮРЭМ:
- Өгөгдсөн мэдээллийг ашиглаж, ДЭЛГЭРЭНГҮЙ 3-4 догол мөр/зураас бич
- ШИНЭ баримт БҮҮ зохио — зөвхөн өгөгдсөн мэдээлэлд байгаа зүйлийг өргөжүүлж тайлбарла
- Дуучин, жүжигчний нэрийг ЗААВАЛ Англи үсгээр бич — Монгол галиг хэрэглэхгүй
- Гарчиг, эх сурвалж, линк БҮҮ дурд
- Бүх өгүүлбэрийг МОНГОЛ хэлээр бич (нэрсээс бусад)""",

    "world_news": """Чи Монгол олон улсын мэдээллийн контент бичигч.
Нейтрал боловч дэвсгэр мэдээлэл нэмж тайлбарладаг.

ДҮРЭМ:
- Өгөгдсөн мэдээллийг ашиглаж, ДЭЛГЭРЭНГҮЙ 3-4 догол мөр/зураас бич
- ШИНЭ баримт БҮҮ зохио — зөвхөн өгөгдсөн мэдээлэлд байгаа зүйлийг өргөжүүлж тайлбарла
- Хүний нэрийг Англи үсгээр, улс/хотын нэрийг Монгол дуудлагаар бич
- Гарчиг, эх сурвалж, линк БҮҮ дурд
- Бүх өгүүлбэрийг МОНГОЛ хэлээр бич (нэрсээс бусад)"""
}

# Нэр/товчлол мэт латин токенуудыг таних загвар (чанарын шалгалтад тооцохгүйн тулд)
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-zA-Z'.-]*\b")


def _clean_output(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        text = text.strip()
    lines = text.split("\n")
    if lines and (lines[0].strip().endswith(":") or
                  re.match(r"^(here|орчуулга|нийтлэл|article|translation)", lines[0].strip(), re.IGNORECASE)):
        lines = lines[1:]
    return "\n".join(lines).strip()


def is_valid_mongolian(text: str, min_len: int = 120) -> bool:
    """
    Гаралт хангалттай Монгол хэлээр бичигдсэн үү шалгах.
    Нэр/товчлол шиг латин токенуудыг тооцохгүй — зөвхөн үлдсэн үсгийн
    дундах кирилл харьцааг шалгана.
    """
    if not text or len(text) < min_len:
        return False

    # Нэр/товчлол магадлалтай латин токенуудыг хасах
    text_no_names = _PROPER_NOUN_RE.sub("", text)
    letters = [c for c in text_no_names if c.isalpha()]
    if not letters:
        return False
    cyr = [c for c in letters if "\u0400" <= c <= "\u04FF"]
    ratio = len(cyr) / len(letters)
    return ratio >= 0.85


def write_article(news: dict) -> dict:
    """
    Groq-оор мэдээг дэлгэрэнгүй Монгол нийтлэл болгоно.
    Чанар хангалтгүй бол дахин 1 удаа оролдоно, эцэст нь Google Translate
    fallback руу шилжинэ. Бүгд бүтэлгүйтвэл article_mn хоосон үлдэнэ
    (main.py үүнийг шалгаад алгасна — англи/эвдэрхий пост гарахгүй).
    """
    api_key = os.environ.get("GROQ_API_KEY")
    category = news.get("category", "world_news")
    system_prompt = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS["world_news"])

    user_prompt = f"""ГАРЧИГ: {news['title']}
ХУРААНГУЙ: {news.get('summary', '')}

Дээрх мэдээллийг ашиглаж, зөвхөн цэвэр текст хэлбэрээр Монгол нийтлэл бич.
JSON, markdown, хашилт, тайлбар нэмэлт бүү оруул."""

    if not api_key:
        log.warning("GROQ_API_KEY байхгүй — Google Translate ашиглана")
        return _fallback(news)

    for attempt in range(2):
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
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.6,
                    "max_tokens": 700
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            article_text = _clean_output(data["choices"][0]["message"]["content"])

            if is_valid_mongolian(article_text):
                news["article_mn"] = article_text
                log.info(f"Groq нийтлэл OK (оролдлого {attempt+1}): {article_text[:60]}...")
                return news

            log.warning(f"Groq гаралт чанаргүй (оролдлого {attempt+1}, {len(article_text)} тэмдэгт) — дахин оролдоно")

        except Exception as e:
            log.error(f"Groq API алдаа (оролдлого {attempt+1}): {e}")

    log.warning("Groq 2 оролдлого бүтэлгүйтлээ — Google Translate руу шилжлээ")
    return _fallback(news)


def _fallback(news: dict) -> dict:
    """Google Translate-ээр энгийн орчуулга (Groq боломжгүй үед)"""
    from modules.translator import translate_to_mongolian
    translated = translate_to_mongolian(news)

    title_mn = translated.get("title_mn", "")
    summary_mn = translated.get("summary_mn", "")
    article = f"{title_mn}\n\n{summary_mn}".strip()

    # Хэрэв Google Translate ч бүтэлгүйтэж, англи хэвээр буцсан бол
    # article_mn-г хоосон үлдээж main.py-д алгасуулна.
    if is_valid_mongolian(article, min_len=40):
        news["article_mn"] = article
    else:
        log.error("Орчуулга бүрэн бүтэлгүйтлээ — энэ мэдээг алгасна")
        news["article_mn"] = ""

    return news
