"""
Орчуулах модуль — Claude API ашиглан Монгол орчуулга
Anthropic API key шаардана (GitHub Secrets-д хадгална)
"""

import os
import json
import logging
import anthropic

log = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Категори тус бүрийн орчуулгын заавар
SYSTEM_PROMPTS = {
    "sports": """Та спортын мэдээний мэргэжлийн Монгол орчуулагч. 
Дүрэм:
- Гарчигийг товч, сонирхолтой Монгол хэлээр орчуул
- Хураангуйг 2-3 өгүүлбэрт багтааж орчуул  
- Спортын нэр томьёог зөв ашигла (NBA=НБА, FIFA=ФИФА гэх мэт)
- Тоглогчийн нэрийг латин үсгээр хэвээр үлдээ
- Зөвхөн JSON форматаар хариул""",

    "music": """Та хөгжим, шоу бизнесийн мэдээний мэргэжлийн Монгол орчуулагч.
Дүрэм:
- Дуучин, жүжигчдийн нэрийг латин үсгээр хэвээр үлдээ
- Залуу үзэгчдэд ойлгомжтой, хөнгөн хэлээр орчуул
- Дууны нэр, киноны нэрийг "" хашилтад бичиж хэвээр үлдээ
- Зөвхөн JSON форматаар хариул""",

    "world_news": """Та олон улсын мэдээний мэргэжлийн Монгол орчуулагч.
Дүрэм:
- Мэдээг нейтрал, объектив байдлаар орчуул
- Газарзүйн нэр, хүний нэрийг Монгол дуудлагаар бич
- Нарийн техник нэр томьёог тайлбарла
- Зөвхөн JSON форматаар хариул"""
}

def translate_to_mongolian(news: dict) -> dict:
    """
    Нэг мэдээг Монгол хэлрүү орчуулах
    Claude API ашиглана
    """
    category = news.get("category", "world_news")
    system_prompt = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS["world_news"])

    user_prompt = f"""Дараах мэдээний гарчиг болон хураангуйг Монгол хэлрүү орчуул.

ГАРЧИГ: {news['title']}
ХУРААНГУЙ: {news.get('summary', '')}
ЭХ СУРВАЛЖ: {news['source_name']}

Дараах JSON форматаар ЗӨВХӨН JSON хариул (өөр текст бичихгүй):
{{
  "title_mn": "Монгол гарчиг энд",
  "summary_mn": "Монгол хураангуй энд (2-3 өгүүлбэр)"
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        raw = response.content[0].text.strip()
        
        # JSON цэвэрлэх
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        
        translated = json.loads(raw)

        # Орчуулга нэмэх
        news["title_mn"] = translated.get("title_mn", news["title"])
        news["summary_mn"] = translated.get("summary_mn", "")
        
        log.info(f"Орчуулагдлаа: {news['title_mn'][:50]}")
        return news

    except json.JSONDecodeError as e:
        log.error(f"JSON алдаа: {e} | raw: {raw[:100]}")
        # Fallback: орчуулаагүй хэлбэрээр үлдээх
        news["title_mn"] = news["title"]
        news["summary_mn"] = news.get("summary", "")
        return news

    except Exception as e:
        log.error(f"Орчуулгын алдаа: {e}")
        news["title_mn"] = news["title"]
        news["summary_mn"] = news.get("summary", "")
        return news
