"""
Зургийн нөөц эх сурвалж — Unsplash API (үнэгүй)
Мэдээний гарчигнаас нэр/түлхүүр үгсийг ялгаж, сэдэвт аль болох
ойр зураг хайна. Олдохгүй бол категороос хамгийн тохиромжтой зурагт шилжинэ.

Тайлбар: Unsplash бол чөлөөт стok зургийн сан тул тамирчид, дуучдын
жинхэнэ editorial зураг ховор — сэдэвт ойролцоо зураг л олдоно.
"""

import os
import re
import logging
import requests

log = logging.getLogger(__name__)

UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"

CATEGORY_FALLBACK_TERMS = {
    "sports": "basketball game arena",
    "music": "concert stage lights",
    "world_news": "city skyline news",
}

# Гарчигнаас хасах нийтлэг үгс (нэр биш)
_STOPWORDS = {
    "The", "A", "An", "In", "On", "At", "For", "With", "After", "Before",
    "How", "Why", "What", "When", "Who", "Sources", "Report", "Reports",
    "Breaking", "New", "His", "Her", "Their", "This", "That", "As", "But",
}


def _extract_keywords(title: str, max_words: int = 3) -> str:
    """
    Гарчигнаас нэр/байгууллага магадлалтай том үсэгтэй үгсийг ялгах.
    Жишээ: "LeBron James leaves Lakers after 8 years" -> "LeBron James Lakers"
    """
    candidates = re.findall(r"\b[A-Z][a-zA-Z'-]+\b", title)
    keywords = [w for w in candidates if w not in _STOPWORDS]
    return " ".join(keywords[:max_words])


def get_fallback_image(category: str, title: str = "") -> str:
    """
    1) Гарчигны түлхүүр үгсээр (нэрс) хайна — сэдэвт хамгийн ойр
    2) Олдохгүй бол категорийн ерөнхий зураг
    """
    access_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not access_key:
        log.warning("UNSPLASH_ACCESS_KEY байхгүй")
        return ""

    queries = []
    keywords = _extract_keywords(title)
    if keywords:
        # Нэрс + категорийн үндсэн үг хослуулах (жишээ: "LeBron James Lakers basketball")
        base = {"sports": "basketball", "music": "music", "world_news": ""}.get(category, "")
        queries.append(f"{keywords} {base}".strip())
    queries.append(CATEGORY_FALLBACK_TERMS.get(category, "news"))

    for query in queries:
        try:
            response = requests.get(
                UNSPLASH_API_URL,
                params={
                    "query": query,
                    "per_page": 1,
                    "orientation": "landscape",
                    "content_filter": "high",
                },
                headers={"Authorization": f"Client-ID {access_key}"},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])

            if results:
                image_url = results[0].get("urls", {}).get("regular", "")
                if image_url:
                    log.info(f"Unsplash зураг олдлоо (хайлт: {query})")
                    return image_url

            log.info(f"Unsplash: '{query}' хайлтад зураг олдсонгүй")

        except Exception as e:
            log.warning(f"Unsplash алдаа ({query}): {e}")

    return ""
