"""
Зургийн нөөц эх сурвалж:
1) Wikimedia Commons — үнэгүй, API key шаардахгүй, жинхэнэ хүн/багийн
   зураг байх магадлал өндөр (CC лицензтэй)
2) Unsplash — Wikimedia олдохгүй бол ерөнхий сэдэвт зураг

Анхаар: Wikimedia Commons-ийн зарим зураг CC-BY / CC-BY-SA лицензтэй тул
хатуу хэрэглээнд зохиогчийг дурдах шаардлагатай байж болно. Бид энд зөвхөн
нээлттэй ашиглалттай (public domain/CC0 давамгайлсан) зургийг эрэмбэлж
ашигладаг ч 100% баталгаа биш — байгууллагын хэмжээнд ашиглахаасаа өмнө
эрх зүйн зөвлөгөө авахыг зөвлөж байна.
"""

import os
import re
import logging
import requests

log = logging.getLogger(__name__)

WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"
UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"

CATEGORY_FALLBACK_TERMS = {
    "sports": "basketball game arena",
    "music": "concert stage lights",
    "world_news": "city skyline news",
}

_STOPWORDS = {
    "The", "A", "An", "In", "On", "At", "For", "With", "After", "Before",
    "How", "Why", "What", "When", "Who", "Sources", "Report", "Reports",
    "Breaking", "New", "His", "Her", "Their", "This", "That", "As", "But",
}


def _extract_keywords(title: str, max_words: int = 3) -> str:
    candidates = re.findall(r"\b[A-Z][a-zA-Z'-]+\b", title)
    keywords = [w for w in candidates if w not in _STOPWORDS]
    return " ".join(keywords[:max_words])


def _search_wikimedia(query: str) -> str:
    """Wikimedia Commons-с зураг хайх — жинхэнэ хүн/багийн зураг олох магадлал өндөр"""
    try:
        response = requests.get(
            WIKIMEDIA_API_URL,
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"{query} filetype:bitmap",
                "gsrnamespace": 6,  # File namespace
                "gsrlimit": 5,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": 1200,
                "format": "json",
            },
            headers={"User-Agent": "AutoNewsPoster/1.0 (mongolnews auto-poster bot)"},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        pages = data.get("query", {}).get("pages", {})

        for page in pages.values():
            imageinfo = page.get("imageinfo", [])
            if not imageinfo:
                continue
            info = imageinfo[0]
            url = info.get("thumburl") or info.get("url", "")
            # SVG, лого зэрэг зохисгүй файлыг алгасах
            if url and not url.lower().endswith((".svg", ".pdf")):
                return url

        return ""
    except Exception as e:
        log.warning(f"Wikimedia алдаа ({query}): {e}")
        return ""


def _search_unsplash(query: str) -> str:
    access_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not access_key:
        return ""
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
        results = response.json().get("results", [])
        if results:
            return results[0].get("urls", {}).get("regular", "")
        return ""
    except Exception as e:
        log.warning(f"Unsplash алдаа ({query}): {e}")
        return ""


def get_fallback_image(category: str, title: str = "") -> str:
    """
    1) Wikimedia Commons-с нэрээр хайх (жинхэнэ хүн/багийн зураг олох боломжтой)
    2) Unsplash-с нэрээр хайх
    3) Unsplash-с категорийн ерөнхий зурагт шилжих
    """
    keywords = _extract_keywords(title)

    if keywords:
        img = _search_wikimedia(keywords)
        if img:
            log.info(f"Wikimedia зураг олдлоо (хайлт: {keywords})")
            return img

        base = {"sports": "basketball", "music": "concert", "world_news": ""}.get(category, "")
        img = _search_unsplash(f"{keywords} {base}".strip())
        if img:
            log.info(f"Unsplash зураг олдлоо (хайлт: {keywords})")
            return img

    fallback_term = CATEGORY_FALLBACK_TERMS.get(category, "news")
    img = _search_unsplash(fallback_term)
    if img:
        log.info(f"Unsplash ерөнхий зураг ашиглав ({fallback_term})")
    return img
