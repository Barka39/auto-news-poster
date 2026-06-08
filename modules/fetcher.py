"""
Мэдээ татах модуль
Эх сурвалж: RSS feed-үүд (үнэгүй, API key шаардахгүй)
Зохиогчийн эрх аюулгүй: зөвхөн гарчиг + хураангуй (200 тэмдэгт) + линк авна
"""

import hashlib
import feedparser
import logging
from datetime import datetime

log = logging.getLogger(__name__)

# ============================================================
# ЭХ СУРВАЛЖУУД - 3 чиглэл
# ============================================================
RSS_SOURCES = {
    "sports": [
        {
            "name": "ESPN NBA",
            "url": "https://www.espn.com/espn/rss/nba/news",
            "lang": "en"
        },
        {
            "name": "BBC Sport",
            "url": "https://feeds.bbci.co.uk/sport/rss.xml",
            "lang": "en"
        },
        {
            "name": "ESPN Top Headlines",
            "url": "https://www.espn.com/espn/rss/news",
            "lang": "en"
        },
    ],
    "music": [
        {
            "name": "Billboard",
            "url": "https://www.billboard.com/feed/",
            "lang": "en"
        },
        {
            "name": "Rolling Stone",
            "url": "https://www.rollingstone.com/feed/",
            "lang": "en"
        },
        {
            "name": "TMZ Entertainment",
            "url": "https://www.tmz.com/category/entertainment/feed/",
            "lang": "en"
        },
    ],
    "world_news": [
        {
            "name": "Reuters World",
            "url": "https://feeds.reuters.com/reuters/worldNews",
            "lang": "en"
        },
        {
            "name": "BBC World",
            "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
            "lang": "en"
        },
        {
            "name": "AP News",
            "url": "https://rsshub.app/apnews/topics/ap-top-news",
            "lang": "en"
        },
    ]
}

# Категори emoji
CATEGORY_EMOJI = {
    "sports": "⚽",
    "music": "🎵",
    "world_news": "🌍"
}

# Категори Монгол нэр
CATEGORY_MN = {
    "sports": "Спорт",
    "music": "Хөгжим & Холливүүд",
    "world_news": "Дэлхийн мэдээ"
}

def make_id(url: str) -> str:
    """URL-аас давтагдашгүй ID үүсгэх"""
    return hashlib.md5(url.encode()).hexdigest()

def clean_summary(text: str, max_chars: int = 300) -> str:
    """
    Хураангуйг цэвэрлэж, хэмжээг хязгаарлах
    Зохиогчийн эрх аюулгүй: зөвхөн богино хэсэг авна
    """
    if not text:
        return ""
    # HTML тагуудыг хасах
    import re
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip()
    # 300 тэмдэгтээс хэтрэхгүй (зохиогчийн эрх хамгаалалт)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "..."
    return text

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

                # Хураангуй авах (зохиогчийн эрх аюулгүй хэмжээнд)
                summary_raw = (
                    entry.get("summary", "") or
                    entry.get("description", "") or
                    ""
                )
                summary = clean_summary(summary_raw, max_chars=300)

                news_item = {
                    "id": make_id(url),
                    "category": category,
                    "category_mn": CATEGORY_MN[category],
                    "category_emoji": CATEGORY_EMOJI[category],
                    "source_name": source["name"],
                    "title": entry.get("title", "").strip(),
                    "summary": summary,
                    "url": url,
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
        log.info(f"{CATEGORY_MN[category]}: {len(items)} мэдээ татлаа")

    return all_news
