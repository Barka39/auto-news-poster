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

    URL-г зөвхөн БАРИХ биш, БОДИТООР ачаалж шалгана — эс бөгөөс
    амжилтгүй тохиолдолд дараагийн шат (Gemini/Wikimedia) руу зөв
    шилжиж чадахгүй (URL байгуулалт өөрөө бараг хэзээ ч алдаа гаргадаггүй,
    зөвхөн бодит ачаалахад л алдаа гарч болдог).
    """
    prompt = CATEGORY_AI_PROMPTS.get(category, "news theme, photorealistic, no people")
    encoded = urllib.parse.quote(prompt)
    url = f"{POLLINATIONS_URL}{encoded}?width=1600&height=900&nologo=true"
    try:
        resp = requests.get(url, timeout=25)
        resp.raise_for_status()
        if resp.headers.get("content-type", "").startswith("image/") and len(resp.content) > 5000:
            log.info(f"Pollinations AI зураг амжилттай үүсгэв ({category})")
            return url
        log.warning(f"Pollinations хариу зураг шиг биш байна (content-type: {resp.headers.get('content-type')})")
        return ""
    except Exception as e:
        log.warning(f"Pollinations алдаа: {e}")
        return ""


def get_fallback_image(category: str, title: str = "") -> dict:
    """
    Энэ функц зөвхөн og:image БОЛОН өөр сайтын зураг (main.py-д тусад нь
    оролдогддог) хоёул олдоогүй үед л дуудагдана. Дараалал:

    1) Pollinations AI — сэдэвчилсэн (хүнгүй) зураг ШУУД үүсгэнэ (хамгийн
       хурдан, найдвартай, үнэгүй хязгааргүй)
    2) Gemini — Pollinations боломжгүй бол
    3) Wikimedia Commons — нэрээр хайх (туршлагаас харахад тохироо султай)
    4) Unsplash — эцсийн нөөц

    Буцаах утга: {"url": str, "bytes": bytes} — зөвхөн нэг нь дүүрэн байна.
    """
    # 1) Pollinations AI — сэдэвчилсэн, хүнгүй зураг шууд үүсгэнэ
    img = _generate_pollinations(category)
    if img:
        log.info(f"Pollinations AI зураг ашиглав ({category})")
        return {"url": img, "bytes": b""}

    # 2) Gemini — Pollinations боломжгүй бол
    from modules import gemini_image
    if gemini_image.is_enabled():
        img_bytes = gemini_image.generate_image_bytes(category)
        if img_bytes:
            log.info(f"Gemini зураг ашиглав ({category})")
            return {"url": "", "bytes": img_bytes}

    # 3) Wikimedia / 4) Unsplash — эцсийн нөөц (тохироо султай туршлагатай)
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
            log.info(f"Wikimedia зураг олдлоо (эцсийн нөөц, хайлт: {wiki_query})")
            return {"url": img, "bytes": b""}

        unsplash_query = f"{keywords} {qualifier}".strip()
        img = _search_unsplash(unsplash_query)
        if img:
            log.info(f"Unsplash зураг олдлоо (эцсийн нөөц, хайлт: {unsplash_query})")
            return {"url": img, "bytes": b""}

    fallback_term = CATEGORY_FALLBACK_TERMS.get(category, "news")
    img = _search_unsplash(fallback_term)
    if img:
        log.info(f"Unsplash ерөнхий зураг ашиглав (эцсийн нөөц, {fallback_term})")
        return {"url": img, "bytes": b""}

    return {"url": "", "bytes": b""}
