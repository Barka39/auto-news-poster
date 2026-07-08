"""
Зургийн нөөц эх сурвалж (3 давхарга):
1) Wikimedia Commons — үнэгүй, жинхэнэ хүн/багийн зураг (CC лицензтэй)
2) Unsplash — жинхэнэ stock зураг, сэдэвт ойролцоо
3) Pollinations AI — үнэгүй AI зураг үүсгэгч, ЗӨВХӨН ерөнхий (хүнгүй)
   дүрслэл үүсгэнэ — доорх анхааруулгыг үзнэ үү

⚠️ ЧУХАЛ ЗАРЧИМ: Pollinations AI-г бид ЗОРИУДЛАН тодорхой нэртэй жинхэнэ
хүний "фото шиг" дүрс үүсгэхэд АШИГЛАХГҮЙ. Учир нь:
- Уншигчид AI зохиомол дүрсийг жинхэнэ зураг гэж андуурч болзошгүй (мэхлэлт)
- Meta-гийн synthetic/AI-generated media policy зөрчиж Page хаагдах эрсдэлтэй
- Хүний дүр төрхийн эрхийг (right of publicity) зөрчиж болзошгүй
Тиймээс Pollinations-д зөвхөн ерөнхий сэдэв (талбай, цомго, арена, туг)
илгээж, аль ч хүний нэрийг prompt-д ОРУУЛАХГҮЙ.

Wikimedia/Unsplash-ийн зарим зураг CC-BY/CC-BY-SA лицензтэй тул хатуу
хэрэглээнд эх сурвалж дурдах шаардлагатай байж болно.
"""

import os
import re
import logging
import urllib.parse
import requests

log = logging.getLogger(__name__)

WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"
UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/"

CATEGORY_FALLBACK_TERMS = {
    "sports": "basketball game arena",
    "music": "concert stage lights",
    "world_news": "city skyline news",
}

# Pollinations-д зориулсан хүнгүй, ерөнхий сэдэвт зургийн prompt
CATEGORY_AI_PROMPTS = {
    "sports": "empty basketball arena, dramatic stadium lighting, court close-up, photorealistic, no people, no faces",
    "music": "concert stage with lights, empty venue, dramatic lighting, photorealistic, no people, no faces",
    "world_news": "city skyline at dusk, global news theme, photorealistic, no people, no faces",
}

_STOPWORDS = {
    "The", "A", "An", "In", "On", "At", "For", "With", "After", "Before",
    "How", "Why", "What", "When", "Who", "Sources", "Report", "Reports",
    "Breaking", "New", "His", "Her", "Their", "This", "That", "As", "But",
}


def _extract_keywords(title: str, max_words: int = 2) -> str:
    candidates = re.findall(r"\b[A-Z][a-zA-Z'-]+\b", title)
    keywords = [w for w in candidates if w not in _STOPWORDS]
    return " ".join(keywords[:max_words])


# Wikimedia файлын нэрэнд эдгээр үг байвал алгасна — учир нь ихэвчлэн
# broadcast graphic, meme, edit хийсэн зураг байдаг (жишээ: "GOAL" гэсэн
# текст overlay-той зураг мэргэжлийн бус харагдана)
_IMAGE_TITLE_BLACKLIST = re.compile(
    r"(edit|meme|banner|collage|montage|graphic|sticker|watermark|"
    r"promo|advert|screenshot|screen[\s_-]?shot|goal[\s_-]?graphic|"
    r"\bvs\b|\bversus\b|thumbnail|wallpaper|poster[\s_-]?art)",
    re.IGNORECASE
)


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
                "gsrlimit": 8,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|size",
                "iiurlwidth": 1920,  # Өндөр нягтралын thumbnail хүсэх
                "format": "json",
            },
            headers={"User-Agent": "AutoNewsPoster/1.0 (mongolnews auto-poster bot)"},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        pages = data.get("query", {}).get("pages", {})

        for page in pages.values():
            title = page.get("title", "")
            if _IMAGE_TITLE_BLACKLIST.search(title):
                log.info(f"Wikimedia үр дүн алгаслаа (graphic/meme магадлалтай): {title}")
                continue

            imageinfo = page.get("imageinfo", [])
            if not imageinfo:
                continue
            info = imageinfo[0]
            orig_width = info.get("width", 0)

            # Эх зураг 1920-с бага бол эх URL (хамгийн өндөр чанар), их бол thumbnail
            if orig_width and orig_width <= 1920:
                url = info.get("url", "") or info.get("thumburl", "")
            else:
                url = info.get("thumburl", "") or info.get("url", "")

            # SVG, лого зэрэг зохисгүй файлыг алгасах, хэт жижиг зургийг бас алгасах
            if url and not url.lower().endswith((".svg", ".pdf")) and orig_width >= 600:
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
            # "raw" URL дээр өөрсдийн хэмжээ/чанараа тохируулах (regular нь 1080px-д хязгаарлагддаг)
            raw_url = results[0].get("urls", {}).get("raw", "")
            if raw_url:
                return f"{raw_url}&w=1920&q=85&fm=jpg&fit=max"
            return results[0].get("urls", {}).get("regular", "")
        return ""
    except Exception as e:
        log.warning(f"Unsplash алдаа ({query}): {e}")
        return ""


def _generate_pollinations(category: str) -> str:
    """
    Pollinations AI-аар ерөнхий (хүнгүй) сэдэвчилсэн зураг үүсгэх.
    Энэ функц ЗӨВХӨН category-ийн ерөнхий prompt ашиглана — хүний нэр
    ОРУУЛАХГҮЙ (дээрх модулийн docstring-ийн зарчмыг үз).
    """
    prompt = CATEGORY_AI_PROMPTS.get(category, "news theme, photorealistic, no people")
    encoded = urllib.parse.quote(prompt)
    url = f"{POLLINATIONS_URL}{encoded}?width=1600&height=900&nologo=true"
    log.info(f"Pollinations AI зураг үүсгэв (ерөнхий, хүнгүй): {category}")
    return url


def get_fallback_image(category: str, title: str = "") -> dict:
    """
    1) Wikimedia Commons-с нэрээр хайх (жинхэнэ хүн/багийн зураг)
    2) Unsplash-с нэрээр хайх (жинхэнэ stock зураг)
    3) Unsplash-с категорийн ерөнхий зураг
    4) Gemini-ээр ерөнхий (хүнгүй) illustration зураг үүсгэх
    5) Pollinations AI — Gemini боломжгүй/бүтэлгүйтвэл эцсийн нөөц

    Буцаах утга: {"url": str, "bytes": bytes} — зөвхөн нэг нь дүүрэн байна.

    Анхаар: нэр дангаараа (жишээ: "Bad Bunny") хайхад "bunny" гэдэг үг
    амьтны зурагтай санамсаргүй таарч болдог тул ЭХНЭЭСЭЭ категорийн
    тодруулагч үг (singer, athlete гэх мэт) хамт, бүхэл хэллэг (quoted
    phrase) байдлаар хайна.
    """
    keywords = _extract_keywords(title)
    qualifier = {
        "sports": "athlete",
        "music": "singer musician",
        "world_news": "portrait",
    }.get(category, "")

    if keywords:
        wiki_query = f'"{keywords}" {qualifier}'.strip()
        img = _search_wikimedia(wiki_query)
        if img:
            log.info(f"Wikimedia зураг олдлоо (хайлт: {wiki_query})")
            return {"url": img, "bytes": b""}

        unsplash_query = f"{keywords} {qualifier}".strip()
        img = _search_unsplash(unsplash_query)
        if img:
            log.info(f"Unsplash зураг олдлоо (хайлт: {unsplash_query})")
            return {"url": img, "bytes": b""}

    fallback_term = CATEGORY_FALLBACK_TERMS.get(category, "news")
    img = _search_unsplash(fallback_term)
    if img:
        log.info(f"Unsplash ерөнхий зураг ашиглав ({fallback_term})")
        return {"url": img, "bytes": b""}

    # Gemini — тогтмол illustration маягтай, хүнгүй зураг
    from modules import gemini_image
    if gemini_image.is_enabled():
        img_bytes = gemini_image.generate_image_bytes(category)
        if img_bytes:
            return {"url": "", "bytes": img_bytes}

    # Эцсийн нөөц: Pollinations
    img = _generate_pollinations(category)
    return {"url": img, "bytes": b""}
