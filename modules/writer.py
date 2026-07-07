"""
Нийтлэл бичих модуль — Groq API (үнэгүй)
Хэрэглэгчийн загварын дагуу: анхаарал татсан эхлэл + 2-3 догол мөр.
Давталт илрүүлэгч + кирилл шалгалттай. Муу гаралт постлогдохгүй.
"""

import os
import re
import logging
import requests

log = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPTS = {
    "sports": """Чи Монголын шилдэг спортын контент бичигч. Фэнүүдийн дунд хэллэгээр,
товч гэхдээ утга дүүрэн бичдэг.

БИЧИХ ЗАГВАР (заавал дага):
1-р мөр: Богино, анхаарал татсан өгүүлбэр (жишээ: "Los Angeles Lakers шинэ эрин үеэ эхлүүлэхээр боллоо.")
Дараа нь: 2-3 богино догол мөр — юу болсон, яагаад чухал вэ, цаашид юу болох вэ

ХАТУУ ДҮРЭМ:
- Нэг өгүүлбэрийг ХЭЗЭЭ Ч давтахгүй, нэг санааг нэг л удаа хэл
- Тоглогч, багийн нэрийг Англи үсгээр (Embiid, Lakers, NBA)
- Зөвхөн өгөгдсөн мэдээлэлд байгаа баримтыг ашигла, шинэ баримт бүү зохио
- Гарчиг, эх сурвалж, линк, hashtag бүү бич
- Бүх өгүүлбэр МОНГОЛ хэлээр (нэрсээс бусад)""",

    "music": """Чи Монголын хөгжим/шоу бизнесийн контент бичигч. Залуучуудын
хэллэгээр товч, сонирхолтой бичдэг.

БИЧИХ ЗАГВАР (заавал дага):
1-р мөр: Богино, анхаарал татсан өгүүлбэр
Дараа нь: 2-3 богино догол мөр

ХАТУУ ДҮРЭМ:
- Нэг өгүүлбэрийг ХЭЗЭЭ Ч давтахгүй
- Дуучин, жүжигчний нэрийг Англи үсгээр, дуу/киноны нэрийг "" хашилтад
- Зөвхөн өгөгдсөн баримтыг ашигла
- Гарчиг, эх сурвалж, линк, hashtag бүү бич
- Бүх өгүүлбэр МОНГОЛ хэлээр (нэрсээс бусад)""",

    "world_news": """Чи Монголын олон улсын мэдээний контент бичигч. Нейтрал,
ойлгомжтой, дэвсгэр тайлбартай бичдэг.

БИЧИХ ЗАГВАР (заавал дага):
1-р мөр: Богино, анхаарал татсан өгүүлбэр
Дараа нь: 2-3 богино догол мөр

ХАТУУ ДҮРЭМ:
- Нэг өгүүлбэрийг ХЭЗЭЭ Ч давтахгүй
- Хүний нэрийг Англи үсгээр, улс/хотын нэрийг Монгол дуудлагаар
- Зөвхөн өгөгдсөн баримтыг ашигла
- Гарчиг, эх сурвалж, линк, hashtag бүү бич
- Бүх өгүүлбэр МОНГОЛ хэлээр (нэрсээс бусад)"""
}

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


def _has_repetition(text: str) -> bool:
    """
    Llama-гийн давталтын алдааг илрүүлэх:
    - Ижил өгүүлбэр 2+ удаа (яг таарсан)
    - Ижил 6 үгийн хэлц 2+ удаа
    - Утгын давхардал: өөр үгээр ижил санааг 2+ удаа хэлсэн
      (жишээ: "Х өөрчлөгдөж байна" / "Х-ийн өөрчлөлтийг онцолж байна")
    """
    sentences = [s.strip().lower() for s in re.split(r"[.!?]\s+", text) if len(s.strip()) > 20]
    if len(sentences) != len(set(sentences)):
        return True

    words = text.lower().split()
    seen = set()
    for i in range(len(words) - 5):
        gram = " ".join(words[i:i + 6])
        if gram in seen:
            return True
        seen.add(gram)

    # Утгын давхардал — өгүүлбэр хоорондын үгийн давхцлыг шалгах (Jaccard)
    STOP = {"нь", "нэг", "энэ", "тэр", "бол", "гэж", "гэдэг", "болно", "байна",
            "байгаа", "хэрэг", "явдал", "хийж", "болж", "их", "бас"}
    sentence_word_sets = []
    for s in sentences:
        sig_words = {w for w in re.findall(r"[а-яөүёА-ЯӨҮЁ]{4,}", s) if w not in STOP}
        if len(sig_words) >= 2:
            sentence_word_sets.append(sig_words)

    for i in range(len(sentence_word_sets)):
        for j in range(i + 1, len(sentence_word_sets)):
            a, b = sentence_word_sets[i], sentence_word_sets[j]
            overlap = len(a & b) / len(a | b)
            if overlap >= 0.35:
                return True

    return False


def is_valid_mongolian(text: str, min_len: int = 120) -> bool:
    """Кирилл харьцаа + давталтын шалгалт"""
    if not text or len(text) < min_len:
        return False

    text_no_names = _PROPER_NOUN_RE.sub("", text)
    letters = [c for c in text_no_names if c.isalpha()]
    if not letters:
        return False
    cyr = [c for c in letters if "\u0400" <= c <= "\u04FF"]
    if len(cyr) / len(letters) < 0.85:
        return False

    if _has_repetition(text):
        log.warning("Давталт илэрлээ — гаралтыг хаялаа")
        return False

    return True


def write_article(news: dict) -> dict:
    """
    Groq-оор дэлгэрэнгүй Монгол нийтлэл бичих.
    2 удаа оролдож, бүтэлгүйтвэл Google Translate, эцэст нь алгасна.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    category = news.get("category", "world_news")
    system_prompt = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS["world_news"])

    user_prompt = f"""МЭДЭЭЛЭЛ:
Гарчиг: {news['title']}
Агуулга: {news.get('summary', '')}

Дээрх мэдээллээр Монгол нийтлэл бич. Зөвхөн нийтлэлийн текстийг бич,
өөр юу ч бүү нэм."""

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
                    "temperature": 0.7,
                    "max_tokens": 600,
                    "frequency_penalty": 0.8
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

            log.warning(f"Groq гаралт чанаргүй (оролдлого {attempt+1}) — дахин оролдоно")

        except Exception as e:
            log.error(f"Groq API алдаа (оролдлого {attempt+1}): {e}")

    log.warning("Groq 2 оролдлого бүтэлгүйтлээ — Google Translate руу шилжлээ")
    return _fallback(news)


def _fallback(news: dict) -> dict:
    from modules.translator import translate_to_mongolian
    translated = translate_to_mongolian(news)

    title_mn = translated.get("title_mn", "")
    summary_mn = translated.get("summary_mn", "")
    article = f"{title_mn}\n\n{summary_mn}".strip()

    if is_valid_mongolian(article, min_len=40):
        news["article_mn"] = article
    else:
        log.error("Орчуулга бүрэн бүтэлгүйтлээ — энэ мэдээг алгасна")
        news["article_mn"] = ""

    return news
