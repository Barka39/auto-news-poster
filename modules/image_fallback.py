"""
Зургийн нөөц эх сурвалж — Unsplash API (үнэгүй)
RSS-д зураг байхгүй үед мэдээний сэдэвтэй холбоотой зураг хайж олно.

Unsplash Developer: https://unsplash.com/developers — үнэгүй "Demo" key
Үнэгүй tier: цагт 50 хүсэлт (бидний хэрэгцээнд хангалттай)
"""

import os
import logging
import requests

log = logging.getLogger(__name__)

UNSPLASH_API_URL = "https://api.unsplash.com/photos/random"

# Категори тус бүрийн хайлтын түлхүүр үг (сэдэвтэй тохирсон зураг олоход тусална)
CATEGORY_SEARCH_TERMS = {
    "sports": "basketball action sports",
    "music": "concert music stage",
    "world_news": "news world city",
}


def get_fallback_image(category: str, title: str = "") -> str:
    """
    Unsplash-с категорит тохирсон санамсаргүй зураг олох.
    Гарчигт тодорхой түлхүүр үг байвал (жиш нь баг/тоглогчийн нэр) тэрийг
    хайлтад нэмж илүү тохирсон зураг олох боломж нэмнэ.
    """
    access_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not access_key:
        log.warning("UNSPLASH_ACCESS_KEY байхгүй — зурагны нөөц эх ашиглагдахгүй")
        return ""

    query = CATEGORY_SEARCH_TERMS.get(category, "news")

    try:
        response = requests.get(
            UNSPLASH_API_URL,
            params={
                "query": query,
                "orientation": "landscape",
                "content_filter": "high",
            },
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        image_url = data.get("urls", {}).get("regular", "")
        if image_url:
            log.info(f"Unsplash-с нөөц зураг олдлоо ({query})")
        return image_url

    except Exception as e:
        log.warning(f"Unsplash алдаа: {e}")
        return ""
