"""
Нийтлэл бичих модуль — Groq API (үнэгүй, маш хурдан)
RSS-ийн гарчиг + хураангуйг авч, Монгол хэлээр дэлгэрэнгүй,
олон янзын өгүүлбэрийн бүтэцтэй нийтлэл болгон дахин бичнэ.

Groq: https://console.groq.com — үнэгүй API key авах боломжтой
Model: llama-3.3-70b-versatile (хүчирхэг, хурдан, үнэгүй tier-д багтдаг)
"""

import os
import random
import logging
import requests

log = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

# ============================================================
# ЗААВАР — категори тус бүрийн бичих стиль
# ============================================================
SYSTEM_PROMPTS = {
    "sports": """Чи спортын дэлгэрэнгүй анализ бичдэг Монгол тоймч. Reddit/фэн хэсгийн 
дотоод хэллэгээр, дүн шинжилгээтэй, тоо баримт дэлгэрэнгүй дурдаж бичдэг.

ЗААВАЛ дагах дүрэм:
- Тоглогч, багийн нэрийг ЗААВАЛ Англи хэвээр нь бич (жишээ: Embiid, Lakers, Ja Morant) — Монгол галиг хэрэглэхгүй
- Лиг, тэмцээний товчлолыг Англиар (NBA, MVP, All-Star гэх мэт)
- Гарчиг ХЭРЭГГҮЙ — шууд агуулгаараа эхэл
- 4-6 доод зураас (-) мөрөнд хуваа, мөр бүр өөр өнцгөөс өгүүл (тоглолтын явц, тоглогчийн гүйцэтгэл, багийн асуудал, дүгнэлт гэх мэт)
- Тоо баримт, оноо, статистик дурд (RSS-ийн эх мэдээллээс гаргаж болох бол)
- Дотоод хэллэг ашигла: "тоглолт хийх", "нөлөөгөө үзүүлэх", "гараагаа алдах" гэх мэт""",

    "music": """Чи хөгжим, шоу бизнесийн мэдээллийг сонирхолтой хэлбэрээр дамжуулдаг 
Монгол контент бичигч. Залуучуудын хэллэгээр, follow хийхэд таатай байдлаар бичдэг.

ЗААВАЛ дагах дүрэм:
- Дуучин, жүжигчдийн нэрийг ЗААВАЛ Англи хэвээр нь бич — Монгол галиг хэрэглэхгүй
- Дууны нэр, киноны нэрийг "" хашилтад Англи хэвээр бич
- Гарчиг ХЭРЭГГҮЙ — шууд агуулгаараа эхэл
- 3-5 доод зураас (-) мөрөнд хуваа
- Хөнгөн, яриа шиг байдлаар бич""",

    "world_news": """Чи олон улсын мэдээллийг дэлгэрэнгүй тайлбарладаг Монгол сэтгүүлч. 
Нейтрал боловч контекст, дэвсгэр мэдээлэл нэмж бичдэг.

ЗААВАЛ дагах дүрэм:
- Хүний нэр, байгууллагын нэрийг Англи хэвээр нь бич (жишээ: Trump, NATO, Reuters)
- Улс, хотын нэрийг Монгол дуудлагаар бич (жишээ: Лондон, Бээжин)
- Гарчиг ХЭРЭГГҮЙ — шууд агуулгаараа эхэл
- 3-5 доод зураас (-) мөрөнд хуваа, дэвсгэр контекст нэмж тайлбарла"""
}

# Хувилбар нэмэх зорилготой "өнцөг" саналууд — ижил загвар давтагдахгүйн тулд
OPENING_STYLES = [
    "шууд гол үйл явдлаас эхэл",
    "хамгийн гайхалтай/сонирхолтой дэлгэрэнгүй мэдээллээс эхэл",
    "асуулт хэлбэрээр эхэл",
    "харьцуулалт хийж эхэл (өмнөх тоглолт/үйл явдалтай)",
    "тоо баримтаас эхэл",
]


def write_article(news: dict) -> dict:
    """
    RSS мэдээг Groq API ашиглан дэлгэрэнгүй Монгол нийтлэл болгож дахин бичнэ.
    Амжилтгүй бол энгийн орчуулгад буцаж ажиллана (fallback).
    """
    api_key = os.environ.get("GROQ_API_KEY")
    category = news.get("category", "world_news")

    if not api_key:
        log.warning("GROQ_API_KEY байхгүй — энгийн орчуулга ашиглана")
        return _fallback(news)

    system_prompt = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS["world_news"])
    opening_style = random.choice(OPENING_STYLES)

    user_prompt = f"""Дараах Англи хэл дээрх мэдээллийг ашиглаж Монгол хэлээр дэлгэрэнгүй нийтлэл бич.

ГАРЧИГ (эх): {news['title']}
ХУРААНГУЙ (эх): {news.get('summary', '')}
ЭХ СУРВАЛЖ: {news['source_name']}

Энэ удаагийн нийтлэлээ ингэж {opening_style}.

ЧУХАЛ: Зөвхөн нийтлэлийн бүтэн текстийг шууд бич. JSON, markdown code block,
хашилт, өөр ямар ч нэмэлт форматгүйгээр — зөвхөн цэвэр текст."""

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
                "temperature": 0.8,
                "max_tokens": 800
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        article_text = data["choices"][0]["message"]["content"].strip()

        # Хэрэв санамсаргүй markdown code fence ирвэл цэвэрлэнэ
        if article_text.startswith("```"):
            article_text = article_text.strip("`").strip()
            if article_text.lower().startswith("json") or article_text.lower().startswith("text"):
                article_text = article_text.split("\n", 1)[1] if "\n" in article_text else article_text

        news["article_mn"] = article_text
        log.info(f"Groq нийтлэл бичигдлээ: {news['article_mn'][:60]}...")
        return news

    except Exception as e:
        log.error(f"Groq API алдаа: {e} — энгийн орчуулгад шилжлээ")
        return _fallback(news)


def _fallback(news: dict) -> dict:
    """Groq байхгүй/алдаатай үед Google Translate-ээр энгийн орчуулга хийх"""
    from modules.translator import translate_to_mongolian
    translated = translate_to_mongolian(news)
    article = f"{translated.get('title_mn', '')}\n\n{translated.get('summary_mn', '')}"
    news["article_mn"] = article
    return news
