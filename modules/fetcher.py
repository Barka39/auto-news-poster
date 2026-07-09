"""
Мэдээ татах модуль
Эх сурвалж: RSS feed-үүд (үнэгүй, API key шаардахгүй)
Зохиогчийн эрх аюулгүй: гарчиг + дунд хэмжээний хураангуй (500 тэмдэгт) + линк авна
Зураг: RSS-ийн featured image байвал шууд ашиглана (media/enclosure)
"""

import re
import hashlib
import feedparser
import requests
import logging
from datetime import datetime

log = logging.getLogger(__name__)

# ============================================================
# ЭХ СУРВАЛЖУУД - 3 чиглэл
# ============================================================
RSS_SOURCES = {
    "sports": [
        {"name": "ESPN NBA", "url": "https://www.espn.com/espn/rss/nba/news", "lang": "en"},
        {"name": "BBC Sport", "url": "https://feeds.bbci.co.uk/sport/rss.xml", "lang": "en"},
        {"name": "ESPN Top Headlines", "url": "https://www.espn.com/espn/rss/news", "lang": "en"},
    ],
    "music": [
        {"name": "Billboard", "url": "https://www.billboard.com/feed/", "lang": "en"},
        {"name": "Rolling Stone", "url": "https://www.rollingstone.com/feed/", "lang": "en"},
        {"name": "TMZ Entertainment", "url": "https://www.tmz.com/category/entertainment/feed/", "lang": "en"},
    ],
    "world_news": [
        {"name": "Reuters World", "url": "https://feeds.reuters.com/reuters/worldNews", "lang": "en"},
        {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "lang": "en"},
        {"name": "AP News", "url": "https://rsshub.app/apnews/topics/ap-top-news", "lang": "en"},
    ]
}

CATEGORY_EMOJI = {"sports": "⚽", "music": "🎵", "world_news": "🌍"}
CATEGORY_MN = {"sports": "Спорт", "music": "Хөгжим & Холливүүд", "world_news": "Дэлхийн мэдээ"}


def make_id(url: str) -> str:
    """URL-аас давтагдашгүй ID үүсгэх"""
    return hashlib.md5(url.encode()).hexdigest()


def clean_summary(text: str, max_chars: int = 500) -> str:
    """
    Хураангуйг цэвэрлэж, хэмжээг хязгаарлах
    Зохиогчийн эрх аюулгүй: дунд хэмжээний хэсэг авна (500 тэмдэгт)
    """
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)  # HTML таг хасах
    text = re.sub(r"\s+", " ", text).strip()  # Илүү зайг цэвэрлэх
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "..."
    return text


def extract_image(entry) -> str:
    """
    RSS entry-с featured image URL олох.
    Дараах дарааллаар шалгана:
    1. media_content / media_thumbnail (Media RSS namespace)
    2. enclosures (audio/video/image attachment)
    3. summary/description дотор орсон эхний <img> tag
    """
    # 1. Media RSS namespace
    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            url = media.get("url")
            if url and _looks_like_image(url):
                return url

    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        for thumb in entry.media_thumbnail:
            url = thumb.get("url")
            if url:
                return url

    # 2. Enclosures
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            url = enc.get("href") or enc.get("url")
            enc_type = enc.get("type", "")
            if url and ("image" in enc_type or _looks_like_image(url)):
                return url

    # 3. HTML дотроос <img> олох
    html_source = entry.get("summary", "") or entry.get("description", "")
    match = re.search(r'<img[^>]+src="([^"]+)"', html_source)
    if match:
        return match.group(1)

    return ""


def _looks_like_image(url: str) -> bool:
    return bool(re.search(r"\.(jpg|jpeg|png|webp|gif)(\?.*)?$", url, re.IGNORECASE))


def extract_og_image(article_url: str) -> str:
    """
    Өгүүллийн БОДИТ хуудаснаас og:image meta tag-ийг унших.

    Энэ бол мэдээний сайтууд (BBC, ESPN, Reuters г.м.) өөрсдийн Facebook/
    Twitter-д зориулж ТУХАЙН ӨГҮҮЛЭЛД тусгайлан тохируулсан зургаа
    зааж өгдөг стандарт HTML tag. RSS-ийн media tag-аас хамаагүй
    найдвартай — учир нь RSS дэх media tag ихэвчлэн ерөнхий/буруу байдаг,
    харин og:image болбол яг тухайн өгүүллийн зургийг зөв заана.
    """
    try:
        resp = requests.get(
            article_url,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AutoNewsPoster/1.0)"}
        )
        resp.raise_for_status()
        # Зөвхөн эхний ~50KB-г шалгах (og tag ихэвчлэн <head> дотор, эхэнд байдаг)
        html = resp.text[:50000]

        match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE
        )
        if not match:
            # property, content дараалал эсрэгээр байж болзошгүй
            match = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                html, re.IGNORECASE
            )
        if match:
            og_url = match.group(1)
            log.info(f"og:image олдлоо: {og_url[:80]}")
            return og_url

        return ""
    except Exception as e:
        log.warning(f"og:image унших алдаа ({article_url[:60]}): {e}")
        return ""


def fetch_category(category: str, sources: list) -> list:
    """Нэг категорийн бүх эх сурвалжаас мэдээ татах"""
    results = []

    for source in sources:
        try:
            log.info(f"Татаж байна: {source['name']}")
            feed = feedparser.parse(source["url"])

            if feed.bozo:
                log.warning(f"RSS алдаа: {source['name']}")
                continue

            for entry in feed.entries[:5]:  # Эх сурвалж бүрээс 5 мэдээ
                url = entry.get("link", "")
                if not url:
                    continue

                summary_raw = entry.get("summary", "") or entry.get("description", "") or ""
                summary = clean_summary(summary_raw, max_chars=900)
                image_url = extract_image(entry)
                published = entry.get("published", "тодорхойгүй")
                log.info(f"[ДИАГНОСТИК RSS] '{entry.get('title', '')[:50]}' → зураг: {image_url[:80] if image_url else 'БАЙХГҮЙ'} | нийтлэгдсэн: {published}")

                news_item = {
                    "id": make_id(url),
                    "category": category,
                    "category_mn": CATEGORY_MN[category],
                    "category_emoji": CATEGORY_EMOJI[category],
                    "source_name": source["name"],
                    "title": entry.get("title", "").strip(),
                    "summary": summary,
                    "url": url,
                    "image_url": image_url,
                    "published": entry.get("published", str(datetime.now())),
                }
                results.append(news_item)

        except Exception as e:
            log.error(f"Татахад алдаа [{source['name']}]: {e}")
            continue

    return results


def fetch_all_news() -> list:
    """Бүх категорийн мэдээ татах"""
    all_news = []

    for category, sources in RSS_SOURCES.items():
        log.info(f"--- {CATEGORY_MN[category]} татаж байна ---")
        items = fetch_category(category, sources)
        all_news.extend(items)
        with_image = sum(1 for n in items if n["image_url"])
        log.info(f"{CATEGORY_MN[category]}: {len(items)} мэдээ татлаа ({with_image} зурагтай)")

    return all_news
