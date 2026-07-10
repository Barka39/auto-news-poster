"""
Мэдээ татах модуль
Эх сурвалж: RSS feed-үүд (үнэгүй, API key шаардахгүй)
Зохиогчийн эрх аюулгүй: гарчиг + дунд хэмжээний хураангуй (500 тэмдэгт) + линк авна
Зураг: RSS-ийн featured image байвал шууд ашиглана (media/enclosure)
"""

import re
import hashlib
import html as html_module
import feedparser
import requests
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

# Ийм цагаас хуучин мэдээг алгасна (шинэ мэдээ л постлохын тулд)
MAX_ARTICLE_AGE_HOURS = 24

# ============================================================
# ЭХ СУРВАЛЖУУД - 3 чиглэл
# ============================================================
RSS_SOURCES = {
    "sports": [
        {"name": "ESPN NBA", "url": "https://www.espn.com/espn/rss/nba/news", "lang": "en"},
        {"name": "BBC Sport", "url": "https://feeds.bbci.co.uk/sport/rss.xml", "lang": "en"},
        {"name": "ESPN Top Headlines", "url": "https://www.espn.com/espn/rss/news", "lang": "en"},
        {"name": "Guardian Football", "url": "https://www.theguardian.com/football/rss", "lang": "en"},
        {"name": "Sky Sports", "url": "https://www.skysports.com/rss/12040", "lang": "en"},
    ],
    "music": [
        {"name": "Billboard", "url": "https://www.billboard.com/feed/", "lang": "en"},
        {"name": "Rolling Stone", "url": "https://www.rollingstone.com/feed/", "lang": "en"},
        {"name": "TMZ Entertainment", "url": "https://www.tmz.com/category/entertainment/feed/", "lang": "en"},
        {"name": "Guardian Music", "url": "https://www.theguardian.com/music/rss", "lang": "en"},
        {"name": "NME", "url": "https://www.nme.com/news/music/feed", "lang": "en"},
    ],
    "world_news": [
        {"name": "Reuters World", "url": "https://feeds.reuters.com/reuters/worldNews", "lang": "en"},
        {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "lang": "en"},
        {"name": "AP News", "url": "https://rsshub.app/apnews/topics/ap-top-news", "lang": "en"},
        {"name": "Guardian World", "url": "https://www.theguardian.com/world/rss", "lang": "en"},
        {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "lang": "en"},
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


# Постонд ашиглах зургийн доод өргөн (px). Үүнээс жижиг зургийг
# 1200px болгож томруулахад бүдэг, чанаргүй харагддаг байсан
# (RSS-ийн media_thumbnail ихэвчлэн 140-400px байдаг!)
MIN_IMAGE_WIDTH = 700


def interleave_by_category(news_list: list) -> list:
    """
    Категориор бөөнөөрөө ирсэн жагсаалтыг ЭЭЛЖЛЭН (round-robin) холино.

    АСУУДАЛ: fetch_all_news() Спорт→Хөгжим→Дэлхий дараалалтай жагсаалт
    буцаадаг тул filter_relevant_news()-ийн эхний 20 кандидатад Дэлхийн
    мэдээ бараг ордоггүй байсан (Спорт 14 + Хөгжимийн эхний 6-аар 20
    дүүрчихдэг). Үр дүнд нь тойм постонд Дэлхийн мэдээ 0 гарч байсан.

    Энэ функц ЭХЛЭЭД категори тус бүрээс 1-ийг ээлжлэн авснаар, ач
    холбогдлын шүүлтүүрт ГУРВАН категори адил тэгш өрсөлдөх боломж олгоно.
    """
    from collections import defaultdict, deque
    buckets = defaultdict(deque)
    order = []
    for n in news_list:
        cat = n.get("category", "")
        if cat not in buckets:
            order.append(cat)
        buckets[cat].append(n)

    result = []
    while any(buckets[c] for c in order):
        for c in order:
            if buckets[c]:
                result.append(buckets[c].popleft())
    return result


def get_image_width(url: str) -> int:
    """
    Зургийн БОДИТ өргөнийг шалгана (татаж үзэж). Алдаа гарвал 0.
    Зорилго: RSS-ийн жижиг thumbnail-ийг өндөр чанартай og:image-с
    ялгаж, чанаргүй зураг постлохоос сэргийлэх.
    """
    if not url:
        return 0
    try:
        from PIL import Image
        import io
        resp = requests.get(
            url, timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        log.info(f"[Зургийн хэмжээ] {img.width}x{img.height} — {url[:70]}")
        return img.width
    except Exception as e:
        log.warning(f"Зургийн хэмжээ шалгаж чадсангүй ({url[:60]}): {e}")
        return 0


def pick_best_image(candidates: list) -> str:
    """
    Хэд хэдэн зургийн URL-с ХАМГИЙН ТОХИРОМЖТОЙГ сонгоно:
    1. MIN_IMAGE_WIDTH-с том ЭХНИЙ зургийг шууд авна (дарааллын
       эрэмбэ хадгалагдана: RSS → og:image → өөр сайтын og:image)
    2. Аль нь ч босго давахгүй бол хамгийн томыг нь (хэрэв 400px+
       бол) авна — жинхэнэ фото нь AI зургаас дээр хэвээр
    3. Огт тохирохгүй бол хоосон буцаана (fallback pipeline руу)
    """
    best_url, best_w = "", 0
    for url in candidates:
        if not url:
            continue
        w = get_image_width(url)
        if w >= MIN_IMAGE_WIDTH:
            log.info(f"✅ Чанартай зураг сонгогдлоо ({w}px): {url[:70]}")
            return url
        if w > best_w:
            best_url, best_w = url, w

    if best_w >= 400:
        log.info(f"⚠️ Босго давсан зураг олдсонгүй — хамгийн томыг ({best_w}px) ашиглана")
        return best_url

    log.info("❌ Тохирох хэмжээний жинхэнэ зураг олдсонгүй — fallback руу шилжинэ")
    return ""


def extract_article_context(article_url: str) -> dict:
    """
    Өгүүллийн БОДИТ хуудаснаас og:image-тэй ХАМТ og:description болон
    үндсэн текстийн эхний хэсгийг НЭГ HTTP дуудлагаар цуглуулна.

    АСУУДАЛ: writer.py урьд нь ЗӨВХӨН RSS-ийн summary (500-900 тэмдэгт,
    заримдаа огт ХООСОН) дээр тулгуурлаж нийтлэл бичдэг байсан. "6 баг
    LeBron James-ийг элсүүлэхээр өрсөлдөж байна" гэх мэт олон нарийн
    баримт (баг нэрс, цалингийн тоо гэх мэт) агуулсан ШИНЖИЛГЭЭТ мэдээнд
    RSS teaser ердөө 1 өгүүлбэр байдаг тул Gemini юу ч тодорхой зүйл
    бичих материалгүй болж, "баримт зохиож болохгүй" дүрмээ мөрдөөд л
    ерөнхий, хоосон агуулгатай нийтлэл бичдэг байв.

    ШИЙДЭЛ: og:description (сайтууд өөрсдөө хамгийн чухал 1-3 өгүүлбэрийг
    энд тавьдаг) + эхний хэдэн <p> параграфын БОДИТ текстийг нэмж,
    Gemini-д илүү баялаг, БОДИТ материал өгнө. og:image-ийг ч мөн энд
    хамт татна — ингэснээр дараа дахин тусад нь HTTP дуудахгүй.
    """
    result = {"og_image": "", "og_description": "", "body_excerpt": ""}
    if not article_url:
        return result
    try:
        resp = requests.get(
            article_url,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        resp.raise_for_status()
        page_html = resp.text

        # og:image
        m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            page_html, re.IGNORECASE
        )
        if not m:
            m = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                page_html, re.IGNORECASE
            )
        if m:
            result["og_image"] = m.group(1)

        # og:description (эсвэл ердийн meta description)
        m = re.search(
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
            page_html, re.IGNORECASE
        )
        if not m:
            m = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
                page_html, re.IGNORECASE
            )
        if m:
            result["og_description"] = html_module.unescape(m.group(1)).strip()

        # Body excerpt: <article> дотроос (байхгүй бол бүх хуудаснаас)
        # эхний утга бүхий <p> параграфуудыг ~1800 тэмдэгт хүртэл цуглуулна
        body_source = page_html
        article_match = re.search(r'<article[^>]*>(.*?)</article>', page_html, re.IGNORECASE | re.DOTALL)
        if article_match:
            body_source = article_match.group(1)

        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', body_source, re.IGNORECASE | re.DOTALL)
        clean_parts, total_len = [], 0
        for p in paragraphs:
            text = re.sub(r'<[^>]+>', ' ', p)
            text = html_module.unescape(text)
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) < 40:  # навигаци/товч мөр магадлалтай — алгасна
                continue
            clean_parts.append(text)
            total_len += len(text)
            if total_len > 1800:
                break
        result["body_excerpt"] = " ".join(clean_parts)[:1800]

        log.info(
            f"[ДИАГНОСТИК context] {article_url[:60]} → "
            f"desc={len(result['og_description'])}ch, body={len(result['body_excerpt'])}ch"
        )
    except Exception as e:
        log.warning(f"Өгүүллийн context унших алдаа ({article_url[:60]}): {e}")

    return result


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
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        log.info(f"[ДИАГНОСТИК og] {article_url[:60]} → HTTP {resp.status_code}, {len(resp.text)} тэмдэгт")
        resp.raise_for_status()
        # Бүтэн HTML-г шалгана. Урьд нь зөвхөн эхний 80KB-г шалгадаг байсан
        # бол зарим сайтад (жишээ нь Billboard) og:image таг head-ийн
        # төгсгөл рүү шахагдаж 80KB-с хойш байрлах болсон тул тагийг
        # огт олдохгүй болж, зурган чанар муудах гол шалтгаан болж байсан
        # тул хязгаарлалтыг арилгав.
        html = resp.text

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

        # og:image байхгүй бол twitter:image (эсвэл twitter:image:src) мета
        # тагийг нөөц болгон шалгана — олон сайт хоёуланг нь зэрэг тавьдаг
        match = re.search(
            r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE
        )
        if not match:
            match = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
                html, re.IGNORECASE
            )
        if match:
            tw_url = match.group(1)
            log.info(f"twitter:image олдлоо (og:image байхгүй үед нөөц): {tw_url[:80]}")
            return tw_url

        # Олдоогүй бол шалтгааныг тодруулах: og:image гэдэг үг HTML дотор
        # огт байгаа эсэхийг шалгана (paywall/consent хуудас буцсан
        # эсэхийг тодорхойлоход тусална)
        has_og_string = "og:image" in html
        log.warning(f"[ДИАГНОСТИК og] tag олдсонгүй. 'og:image' үг HTML-д байгаа эсэх: {has_og_string} | HTML урт: {len(html)}")

        return ""
    except Exception as e:
        log.warning(f"og:image унших алдаа ({article_url[:60]}): {e}")
        return ""
def find_context_from_other_sources(title: str, min_content_len: int = 150) -> dict:
    """
    Тухайн эх сурвалж (жишээ: ESPN) bot-хамгаалалтаар хаагдаж, зөвхөн
    хоосон/бяцхан stub хуудас буцаах үед (og:description, body_excerpt
    хоосон гарна) ИЖИЛ СЭДВИЙГ бичсэн ӨӨР сайтуудаас (Google News RSS-ээр
    хайж) агуулгыг нь оролддог.

    БОДИТ КЕЙС: ESPN-ийн LeBron James мэдээнд энэ функц байхгүй үед
    espn.com HTTP 202 (bot-хамгаалалтын түр хуудас, ердөө ~2000 тэмдэгт)
    буцаасан тул og:description/body_excerpt огт хоосон гарч, Gemini
    ерөнхий, тоо баримтгүй нийтлэл бичсэн. Google News-ээр ижил мэдээг
    бичсэн өөр сайт (жишээ: NBC Sports, Yahoo Sports) олж, тэднээс
    агуулга татаж энэ дутууг нөхнө.
    """
    result = {"og_image": "", "og_description": "", "body_excerpt": ""}
    if not title:
        return result
    try:
        import urllib.parse
        query = urllib.parse.quote(title[:100])
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)

        for entry in feed.entries[:5]:
            article_url = entry.get("link", "")
            if not article_url:
                continue
            ctx = extract_article_context(article_url)
            content_len = len(ctx.get("og_description", "")) + len(ctx.get("body_excerpt", ""))
            if content_len >= min_content_len:
                log.info(
                    f"Өөр сайтаас ижил сэдвийн АГУУЛГА олдлоо ({content_len}ch): "
                    f"{entry.get('title', '')[:50]}"
                )
                return ctx

        log.info("Google News-с ижил сэдвийн хангалттай агуулга олдсонгүй")
    except Exception as e:
        log.warning(f"Google News context хайлтын алдаа: {e}")
    return result


def find_image_from_other_sources(title: str) -> str:
    """
    Тухайн өгүүлэлд og:image олдоогүй үед, ИЖИЛ СЭДВИЙГ бичсэн ӨӨР
    сайтуудыг Google News RSS-ээр хайж, тэдгээрийн og:image-г эрэлхийлнэ.

    Энэ нь үнэгүй, API key шаардахгүй, олон сайтын мэдээг нэг дор хайдаг
    Google News-ийн нээлттэй RSS хайлтын функцийг ашигладаг.
    """
    if not title:
        return ""
    try:
        import urllib.parse
        query = urllib.parse.quote(title[:100])
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)

        for entry in feed.entries[:5]:
            article_url = entry.get("link", "")
            if not article_url:
                continue
            img = extract_og_image(article_url)
            if img:
                log.info(f"Өөр сайтаас ижил сэдвийн зураг олдлоо: {entry.get('title', '')[:50]}")
                return img

        log.info("Google News-с ижил сэдвийн зураг олдсонгүй")
        return ""
    except Exception as e:
        log.warning(f"Google News хайлтын алдаа: {e}")
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

                # Хуучин мэдээг алгасах — зөвхөн сүүлийн MAX_ARTICLE_AGE_HOURS
                # цагийн дотор нийтлэгдсэн мэдээг л авна
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    age = datetime.now(timezone.utc) - published_dt
                    if age > timedelta(hours=MAX_ARTICLE_AGE_HOURS):
                        log.info(f"[ХУУЧИН] Алгаслаа ({age.total_seconds()/3600:.0f} цагийн өмнөх): {entry.get('title', '')[:50]}")
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
