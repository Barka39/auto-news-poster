"""
ESPN-ийн албан бус нээлттэй JSON API-аас нийтлэлийн зургийг авах.

ЯАГААД ХЭРЭГТЭЙ ВЭ: espn.com-ийн HTML хуудсыг GitHub Actions-ийн
datacenter IP-ээс requests-ээр татахад Akamai bot protection 403 өгдөг
тул og:image давхарга ESPN мэдээн дээр байнга унадаг (бодит кейс:
2026-07-11-ний Wemby $252M + Trae Young хоёр пост хоёул generic арена
зурагтай гарсан). Харин site.api.espn.com нь ESPN-ийн апп-ууддаа
зориулсан нээлттэй JSON endpoint тул блок хийдэггүй, нийтлэл бүрд
өндөр нягтралын images массив дагалддаг.

Хэрэглээ (main.py-д):
    from modules import espn_api
    ...
    candidates = [
        written.get("image_url", ""),
        context.get("og_image", ""),
        espn_api.get_image(link),   # <-- ESPN бол API-аас
    ]
"""

import re
import logging
import requests

log = logging.getLogger(__name__)

# espn.com/{section}/story/_/id/{id}/... URL-ийн section →
# site.api.espn.com/apis/site/v2/sports/{sport}/{league}/news зам
_SECTION_TO_API = {
    "nba": "basketball/nba",
    "wnba": "basketball/wnba",
    "mens-college-basketball": "basketball/mens-college-basketball",
    "womens-college-basketball": "basketball/womens-college-basketball",
    "nba-summer-league": "basketball/nba",
    "nfl": "football/nfl",
    "college-football": "football/college-football",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
    "mma": "mma/ufc",
    "boxing": "boxing/boxing",
    "golf": "golf/pga",
    "tennis": "tennis/atp",
    "f1": "racing/f1",
    "soccer": "soccer/all",  # soccer нь лигээ URL-с мэдэхгүй тул all
}

_URL_RE = re.compile(
    r"espn\.com/([a-z0-9-]+)(?:/[a-z0-9-]+)*?/story/_/id/(\d+)",
    re.IGNORECASE,
)


def _find_article(article_url: str) -> dict | None:
    """URL-аас story ID-г салгаж, лигийн news API-аас ижил ID-тай
    нийтлэлийн бүтэн JSON объектыг олно. Олдохгүй бол None."""
    m = _URL_RE.search(article_url or "")
    if not m:
        return None

    section, story_id = m.group(1).lower(), m.group(2)
    api_path = _SECTION_TO_API.get(section)
    if not api_path:
        log.info(f"[ESPN API] '{section}' section-ий mapping алга — алгасав")
        return None

    try:
        resp = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/{api_path}/news",
            params={"limit": 50},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
    except Exception as e:
        log.warning(f"[ESPN API] news endpoint алдаа ({api_path}): {e}")
        return None

    for art in articles:
        links = art.get("links", {}).get("web", {}).get("href", "")
        # links.web.href дотор мөн /id/49328757/ хэлбэрээр ID байдаг
        if f"/id/{story_id}" in links:
            return art

    log.info(f"[ESPN API] ID {story_id} сүүлийн 50 мэдээнд олдсонгүй")
    return None


def get_context(article_url: str) -> dict:
    """
    ESPN API-аас нийтлэлийн ТЕКСТЭН агуулгыг авна — espn.com-ийн HTML
    хуудас GitHub Actions-с 403 өгдөг тул og:description/body_excerpt
    хоосон гардаг дутууг энэ нөхнө (headline + description).
    """
    result = {"og_image": "", "og_description": "", "body_excerpt": ""}
    art = _find_article(article_url)
    if not art:
        return result

    headline = (art.get("headline") or "").strip()
    desc = (art.get("description") or "").strip()
    result["og_description"] = desc or headline
    if headline and desc and headline.lower() not in desc.lower():
        result["body_excerpt"] = f"{headline}. {desc}"
    else:
        result["body_excerpt"] = desc

    for img in art.get("images", []):
        if img.get("url"):
            result["og_image"] = img["url"]
            break

    if result["og_description"]:
        log.info(f"[ESPN API] 📝 Текст агуулга олдлоо ({len(result['body_excerpt'])}ch)")
    return result


def get_image(article_url: str, min_width: int = 600) -> str:
    """
    ESPN нийтлэлийн зургийг API-аас авна. Олдохгүй бол хоосон буцаана
    (дараагийн давхарга руу шилжинэ) — БУРУУ нийтлэлийн зураг хэзээ ч
    буцаахгүй.
    """
    art = _find_article(article_url)
    if art:

        # Хамгийн өргөн, min_width-с том зургийг сонгоно
        best_url, best_w = "", 0
        for img in art.get("images", []):
            w = img.get("width", 0) or 0
            url = img.get("url", "")
            if url and w > best_w:
                best_url, best_w = url, w

        if best_url and best_w >= min_width:
            log.info(f"[ESPN API] ✅ Зураг олдлоо ({best_w}px): {best_url[:70]}")
            return best_url
        if best_url:
            # Өргөн нь тодорхойгүй/жижиг ч ESPN-ийн жинхэнэ editorial
            # фото тул AI fallback-с дээр — гэхдээ log-д тэмдэглэнэ
            log.info(f"[ESPN API] ⚠️ Жижиг/тодорхойгүй хэмжээтэй зураг ({best_w}px) ашиглав")
            return best_url

    return ""
