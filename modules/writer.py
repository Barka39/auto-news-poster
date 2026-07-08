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
GROQ_MODEL = "qwen/qwen3.6-27b"

SYSTEM_PROMPTS = {
    "sports": """Чи Монголын шилдэг спортын контент бичигч. Фэнүүдийн дунд хэллэгээр,
товч гэхдээ утга дүүрэн бичдэг.

БИЧИХ ЗАГВАР (заавал дага):
1-р мөр: Богино, анхаарал татсан өгүүлбэр (жишээ: "Los Angeles Lakers шинэ эрин үеэ эхлүүлэхээр боллоо.")
Дараа нь: 2-3 богино догол мөр — юу болсон, яагаад чухал вэ, цаашид юу болох вэ

НЭРНИЙ ХАТУУ ДҮРЭМ (маш чухал):
- Тоглогч, багийн НЭР бүхэлдээ Англи (Латин) үсгээр байх ЁСТОЙ — нэг ч үсэг Кирилл рүү бүү хөрвүүл
- ЗӨВШӨӨРӨГДӨХГҮЙ АЛДАА (хэзээ ч БҮҮ хий): нэрийг хагасыг нь Кирилл, хагасыг нь Латин бичих.
  Жишээ БУРУУ: "Энцо Fernandez" (Энцо гэдэг хэсэг Кирилл болсон — АЛДАА)
  Жишээ ЗӨВ: "Enzo Fernandez" (бүхэлдээ Латин)
  Жишээ БУРУУ: "Марин Ле Пен" (бүхэлдээ Кирилл болсон)
  Жишээ ЗӨВ: "Marine Le Pen" (бүхэлдээ Латин)
- Тэмцээний шат/үе шатны нэрийг (Final, Playoffs гэх мэт) Англи хэвээр эсвэл Монгол
  үгтэй хослуулж болно (жишээ: "Бүсийн Final", "Conference Final")

АНГЛИАР ХЭВЭЭР ҮЛДЭЭХ СПОРТЫН НЭР ТОМЬЁО (Монгол тайлбарлагчид ихэвчлэн
англиар нь хэрэглэдэг тул орчуулахгүй, англи хэвээр бич):
Triple-double, Double-double, Buzzer shoot, Clutch, Poster, And-one,
Pick and roll, Pick and pop, Step-back, Euro step, Iso
(мөн энэ маягийн бусад олон улсын нийтлэг спортын нэр томьёог адилхан
англи хэвээр нь ашиглаж болно)

БУСАД ДҮРЭМ:
- Нэг өгүүлбэрийг ХЭЗЭЭ Ч давтахгүй, нэг санааг нэг л удаа хэл
- Зөвхөн өгөгдсөн мэдээлэлд байгаа баримтыг ашигла, шинэ баримт бүү зохио
- Гарчиг, эх сурвалж, линк, hashtag бүү бич
- Бусад бүх өгүүлбэрийг МОНГОЛ хэлээр бич (нэр, тэмцээний шат, тусгай нэр
  томьёоноос бусад)""",

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

НЭРНИЙ ХАТУУ ДҮРЭМ (маш чухал):
- Хүний бүтэн нэр (нэр + овог) Англи (Латин) үсгээр байх ЁСТОЙ — нэг ч
  үсэг Кирилл рүү бүү хөрвүүл
- ЗӨВШӨӨРӨГДӨХГҮЙ АЛДАА (хэзээ ч БҮҮ хий): нэрийг хагасыг нь Кирилл,
  хагасыг нь Латин бичих.
  Жишээ БУРУУ: "Марин Ле Пен" (бүхэлдээ Кирилл болсон — АЛДАА)
  Жишээ ЗӨВ: "Marine Le Pen" (бүхэлдээ Латин)
- Улс, хотын нэрийг Монгол дуудлагаар бич (жишээ: Лондон, Бээжин, Франц)

БУСАД ДҮРЭМ:
- Нэг өгүүлбэрийг ХЭЗЭЭ Ч давтахгүй
- Зөвхөн өгөгдсөн баримтыг ашигла
- Гарчиг, эх сурвалж, линк, hashtag бүү бич
- Бусад бүх өгүүлбэрийг МОНГОЛ хэлээр бич (хүний нэрнээс бусад)"""
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
    log.info(f"writer.py ашиглаж буй загвар: {GROQ_MODEL}")
    system_prompt = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS["world_news"])
    system_prompt += """

НАЙРУУЛГЫН ЧУХАЛ ДҮРЭМ:
- Англи эх текстийг ҮГ ҮГЭЭР бүү орчуул. Утгыг нь бүрэн ойлгоод, эхнээс
  бүтэн, зөв дүрмийн (нөхцөл, тийн ялгал зөв) МОНГОЛ өгүүлбэрээр дахин
  найруул. Өгүүлбэр бүр өөрөө дангаараа ойлгомжтой байх ёстой.
- Хэрэв эх мэдээлэлд ХОЛБООГҮЙ хэд хэдэн сэдэв (жишээ: өөр өөр хүний
  тухай тусдаа мэдээ) зэрэгцүүлж орсон бол ТЭДГЭЭРИЙГ НЭГ ӨГҮҮЛБЭРТ
  БҮҮ ХОЛЬЖ ХУТГА. Сэдэв бүрийг тусдаа, тодорхой өгүүлбэрт бич, эсвэл
  хамгийн гол/анхны сэдвийг сонгож зөвхөн түүн дээр төвлөр.
- Ижил үг/хэллэгийг ойрхон давтахгүй байх (жишээ: "өнөөдрийн өнөөдөр"
  гэх мэт санамсаргүй давхардал гаргахгүй)."""

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
                    "max_tokens": 700,
                    "frequency_penalty": 0.8,
                    "reasoning_effort": "default",
                    "reasoning_format": "hidden"
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            article_text = _clean_output(message.get("content", ""))

            if is_valid_mongolian(article_text):
                news["article_mn"] = article_text
                log.info(f"Groq нийтлэл OK [{GROQ_MODEL}] (оролдлого {attempt+1}): {article_text[:60]}...")
                return news

            log.warning(f"Groq гаралт чанаргүй (оролдлого {attempt+1}) — дахин оролдоно")
            log.warning(f"  Урт: {len(article_text)} тэмдэгт | Гаралт (эхний 300): {article_text[:300]!r}")
            log.warning(f"  message-ийн бүх түлхүүр: {list(message.keys())}")
            if "reasoning" in message:
                log.warning(f"  reasoning талбар байна (эхний 200): {str(message.get('reasoning'))[:200]!r}")

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


def filter_relevant_news(news_list: list, max_candidates: int = 20) -> list:
    """
    Groq-д БАГЦААР (нэг л дуудлага) мэдээнүүдийг харуулж, Монгол ерөнхий
    уншигчдад үнэхээр сонирхолтой/ач холбогдолтой зүйлийг сонгуулна.
    Жижиг, сонин бус мэдээг (жишээ: "тоглогч дасгалжуулалтад ирсэн" гэх мэт)
    шүүж хаяна.

    API key байхгүй, алдаа гарах, эсвэл хоосон буцах үед АЮУЛГҮЙ fallback:
    бүх мэдээг хэвээр нь буцаана (систем зогсохгүй, зөвхөн шүүлтүүр алгасна).
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or not news_list:
        return news_list

    candidates = news_list[:max_candidates]
    listing = "\n".join(
        f"{i+1}. [{n.get('category_mn', '')}] {n['title']}"
        for i, n in enumerate(candidates)
    )

    prompt = f"""Доорх мэдээнүүдээс Монгол ерөнхий уншигчдад ҮНЭХЭЭР
сонирхолтой, ач холбогдолтой зүйлийг сонго. Жижиг/өдөр тутмын, сонин
бус мэдээг (жишээ: бэлтгэл, дасгалжуулалт, минорит зочилсон гэх мэт)
хасаарай.

{listing}

ЗӨВХӨН сонгосон дугааруудыг таслалаар (,) тусгаарлан бич.
Тайлбар, өөр текст бүү нэм. Жишээ хариу: 1,3,5"""

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
                    {"role": "system", "content": "You are a news editor selecting the most newsworthy items for a general audience."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 100,
                "reasoning_effort": "none"
            },
            timeout=20
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"].strip()
        indices = [int(x) - 1 for x in re.findall(r"\d+", raw)]
        filtered = [candidates[i] for i in indices if 0 <= i < len(candidates)]

        if filtered:
            log.info(f"Ач холбогдлын шүүлтүүр: {len(candidates)} -> {len(filtered)} мэдээ")
            # Шүүгдээгүй үлдсэн (max_candidates-с гадуурх) мэдээг ард нь хавсаргана
            rest = news_list[max_candidates:]
            return filtered + rest

        log.warning("Шүүлтүүр хоосон буцсан — бүх мэдээг хэвээр үлдээе")
        return news_list

    except Exception as e:
        log.warning(f"Ач холбогдлын шүүлтүүр алдаа: {e} — бүх мэдээг хэвээр үлдээе")
        return news_list
