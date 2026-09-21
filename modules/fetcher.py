"""
Мэдээ татах модуль
Эх сурвалж: RSS feed-үүд (үнэгүй, API key шаардахгүй)
Зохиогчийн эрх аюулгүй: гарчиг + дунд хэмжээний хураангуй (500 тэмдэгт) + линк авна
Зураг: RSS-ийн featured image байвал шууд ашиглана (media/enclosure)
"""

import os
import re
import hashlib
import html as html_module
import feedparser
import html
import requests
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

# Ийм цагаас хуучин мэдээг алгасна. ХУУДАСНЫ БОДЛОГО: зөвхөн хамгийн
# шинэ (дөнгөж дууссан тоглолт, дөнгөж зарлагдсан мэдээ) контент постлох
# тул хязгаар 10 цаг (өмнө нь 24 байсан)
MAX_ARTICLE_AGE_HOURS = int(os.environ.get("MAX_ARTICLE_AGE_HOURS", "24"))  # GitHub cron 1.5-5ц зайтай тул 10ц хэт богино байсан (2026-09-21)

# ============================================================
# ХУУДАСНЫ ЧИГЛЭЛ: зөвхөн Сагсан бөмбөг + Хөл бөмбөг + UFC/MMA.
# Хөгжим, Дэлхийн мэдээ зэрэг бусад чиглэлийг ТУСДАА хуудсуудад
# (өөр repo/config-оор) оруулна — энэ repo-с хасагдсан.
# Ажиллахгүй feed гарвал bozo-шалгалт аюулгүйгээр алгасдаг тул
# лог дээрх "RSS алдаа" анхааруулгаар шалгаж, URL-ийг нь солино.
# ============================================================
# МОНГОЛЫН САГСАН БӨМБӨГ. 2026-09-21-ний судалгаа: Монголын сайтуудаас жинхэнэ
# RSS зөвхөн ikon.mn-д (ерөнхий мэдээ → keywords), сагсны гол эх сурвалж
# 24tsag.mn RSS-гүй тул спортын ангиллын HTML жагсаалтаас (type="html")
# уншина. news.mn/gogo/eagle/montsame/mnb — feed байхгүй эсвэл 502.
# Google News-ийн хайлтын feed нь redirect линктэй, агуулгагүй тул авдаггүй.
MN_BASKETBALL_KEYWORDS = r"сагс|3х3|3x3|\bNBA\b|MNBA|\bMBA\b|The League"
MN_BASKETBALL_SOURCES = [
    {"name": "24tsag Спорт", "url": "https://24tsag.mn/as/sport", "lang": "mn",
     "type": "html", "base": "https://24tsag.mn", "link_re": r'href="(/a/\d+)"',
     "keywords": MN_BASKETBALL_KEYWORDS, "max_items": 8},
    {"name": "ikon.mn", "url": "https://ikon.mn/rss", "lang": "mn",
     "keywords": MN_BASKETBALL_KEYWORDS, "max_items": 30},
    # S4: Монголын лиг (MBL/The League) легионер, шигшээ — англи, зөвхөн Монголын хуудас
    {"name": "Asia-Basket Mongolia", "url": "https://www.asia-basket.com/Mongolia/basketball.aspx", "lang": "en",
     "type": "html", "base": "", "link_re": r'href="([^"]*?/Mongolia/news/\d+[^"]*)"', "max_items": 6},
]

# S4: Монгол тоглогч/багийн сэрэмжлүүлэг — дурдагдсан мэдээ шүүлтүүрийг давахгүй, 10 оноо.
# Хуудасны №1 давуу тал = Монголын сагс. Шинэ нэр олдох бүрд нэмнэ.
# Монгол хэлтэй эх сурвалжид: нэрс, шигшээ, лиг. Англи эх сурвалжид ЗӨВХӨН "Mongolia" гэсэн
# үгтэй хамт (2026-09-21: "The League" гэдэг нь англи podcast-ийн "the league"-тэй таарч
# 10 оноо өгч байсан алдаа).
MN_WATCHLIST_MN = re.compile(
    r"Монголын? (эрэгтэй|эмэгтэй|үндэсний|залуучуудын)? ?шигшээ|Монгол улсын шигшээ"
    r"|Болор-Эрдэнэ|Тэмүүлэн|Биндэръяа|Балжинням|Дэлгэрнямбуу|Дэлгэрням|Онолбаатар|Стив Сөр"
    r"|The League|MNBA|\bMBL\b|Хасын Хүлэгүүд|Хүлэгүүд|МСБХ|Үндэсний дээд лиг|3x3|3х3",
    re.IGNORECASE)
MN_WATCHLIST_EN = re.compile(
    r"\bMongolia(n)?\b.*\b(national team|3x3|FIBA|Asia Cup|Asian Games|qualif|MBL|The League|league)"
    r"|\b(national team|3x3|FIBA|Asia Cup|Asian Games|MBL|The League)\b.*\bMongolia(n)?\b"
    r"|Team Mongolia|Xac Broncos|Zaisan Broncos|Bishrelt Metal|Khuleguud",
    re.IGNORECASE)


def is_mn_watch(title: str, summary: str = "", lang: str = "") -> bool:
    text = f"{title} {summary}"
    if lang == "mn" or re.search(r"[А-Яа-яӨөҮү]{3,}", title or ""):
        return bool(MN_WATCHLIST_MN.search(text))
    return bool(MN_WATCHLIST_EN.search(text))

RSS_SOURCES = {
    "basketball": [  # NBA
        # ESPN-ийн news API: RSS-д ордоггүй "HeadlineNews" (гэрээ, сунгалт, трейд, томилгоо) энд ирдэг
        {"name": "ESPN NBA API", "type": "espn_api", "lang": "en",
         "url": "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/news?limit=30"},
        {"name": "ESPN NBA", "url": "https://www.espn.com/espn/rss/nba/news", "lang": "en"},
        {"name": "Yahoo NBA", "url": "https://sports.yahoo.com/nba/rss.xml", "lang": "en"},
        {"name": "CBS Sports NBA", "url": "https://www.cbssports.com/rss/headlines/nba/", "lang": "en"},
        # RealGM Wiretap: трейдийн яриа, гэрээ, цуурхал — улирал хоорондын үед ч бодит мэдээ
        {"name": "RealGM Wiretap", "url": "https://basketball.realgm.com/rss/wiretap/0/0.xml", "lang": "en", "max_items": 15},
    ],
    # Монголын сагсан бөмбөг: Монгол хэлтэй эх сурвалж. Ерөнхий спортын
    # feed бол "keywords"-ээр зөвхөн сагсны мэдээг үлдээнэ.
    "mn_basketball": MN_BASKETBALL_SOURCES,
}

CATEGORY_EMOJI = {
    "basketball": "🏀", "mn_basketball": "🇲🇳🏀", "football": "⚽", "ufc": "🥊",
    # Хуучин түлхүүрүүд — өөр хуудасны config дахин ашиглах үед эвдрэхгүйн тулд
    "sports": "⚽", "music": "🎵", "world_news": "🌍",
}
CATEGORY_MN = {
    "basketball": "NBA", "mn_basketball": "Монголын сагс", "football": "Хөл бөмбөг", "ufc": "UFC/MMA",
    "sports": "Спорт", "music": "Хөгжим & Холливүүд", "world_news": "Дэлхийн мэдээ",
}


def make_id(url: str) -> str:
    """URL-аас давтагдашгүй ID үүсгэх"""
    return hashlib.md5(url.encode()).hexdigest()


# ТОЙМ/LIVE BLOG ТӨРЛИЙН НИЙТЛЭЛИЙГ ТАНИХ ЗАГВАРУУД.
# Ийм эх сурвалж НЭГ мэдээ биш, олон холбоогүй сэдвийн цуглуулга байдаг
# тул нийтлэл бичихэд "4 өөр сэдэв нэг постонд" гэсэн замбараагүй үр дүн
# гаргадаг (бодит кейс: Summer League + Kawhi + WNBA нэг постонд орсон).
# Хуудасны бодлого: зөвхөн ГАНЦ тодорхой үйл явдлын мэдээ постлоно.
ROUNDUP_TITLE_RE = re.compile(
    r"\blive\b|liveblog|live updates?|livestream|live stream"
    r"|how to watch|what to watch|what we're hearing|what we are hearing"
    r"|what's next for|\bintel on\b|\broundup\b|round-up|\btakeaways\b"
    r"|\bmailbag\b|\bq&a\b|power rankings|winners and losers|\bstorylines\b"
    r"|\b\d+ things\b|five things|key questions|talking points|\bnotebook\b"
    r"|\bbuzz:|everything you need|biggest questions|\btop \d+\b|\bday \d+\b"
    r"|\bpodcast\b|\bepisode\b|dunc'd on|\boutlook\b|season preview|player previews?|\bpreview:|\bprevie?wing\b"
    r"|\bforecast\b|\brankings?\b|\bpredictions?\b|\bmock draft\b|\bnewsletter\b|\bgrades\b",
    re.IGNORECASE,
)


def is_roundup_title(title: str) -> bool:
    """Гарчиг тойм/live-blog/listicle төрлийн эсэхийг шалгана."""
    return bool(ROUNDUP_TITLE_RE.search(title or ""))


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

    АНХААР: news.google.com/rss/articles/... холбоосууд Google-ийн ӨӨРИЙН
    JS-аар render хийдэг redirect хуудас руу ордог тул статик HTML
    татахад ихэвчлэн зөвхөн Google-ийн ерөнхий stub (og:description~98
    тэмдэгт, body 0) ирдэг — жинхэнэ нийтлэлийн текст биш. Тиймээс
    дараалан 2 удаа хоосон body ирвэл (structural pattern), үлдсэн
    кандидатуудыг дэмий оролдохгүй эрт зогсооно.
    """
    result = {"og_image": "", "og_description": "", "body_excerpt": ""}
    if not title:
        return result
    try:
        import urllib.parse
        query = urllib.parse.quote(title[:100])
        # Bing News RSS — Google News-ээс ялгаатай нь entry.link нь
        # publisher-ийн ШУУД URL байдаг (Google-ийнх JS шаарддаг
        # redirect тул og:image/текст хэзээ ч гардаггүй байсан)
        rss_url = f"https://www.bing.com/news/search?q={query}&format=rss"
        feed = feedparser.parse(rss_url)

        zero_body_streak = 0
        for entry in feed.entries[:5]:
            article_url = entry.get("link", "")
            if not article_url:
                continue
            # Bing-ийн дотоод redirect холбоос таарвал алгасна
            if "bing.com" in article_url:
                continue
            # Tracking параметрүүдийг цэвэрлэнэ
            article_url = article_url.split("?")[0] if "?ocid=" in article_url else article_url
            ctx = extract_article_context(article_url)
            content_len = len(ctx.get("og_description", "")) + len(ctx.get("body_excerpt", ""))
            if content_len >= min_content_len:
                log.info(
                    f"Өөр сайтаас ижил сэдвийн АГУУЛГА олдлоо ({content_len}ch): "
                    f"{entry.get('title', '')[:50]}"
                )
                return ctx

            if not ctx.get("body_excerpt"):
                zero_body_streak += 1
                if zero_body_streak >= 2:
                    log.info(
                        "Хайлтын үр дүнгийн хуудаснууд тогтмол хоосон тул эрт зогсоов"
                    )
                    break
            else:
                zero_body_streak = 0

        log.info("Bing News-с ижил сэдвийн хангалттай агуулга олдсонгүй")
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


_PUBLISHED_META_RE = re.compile(
    r'<meta[^>]+(?:published_time|datePublished|pubdate)[^>]+content="([^"]+)"|'
    r'"datePublished"\s*:\s*"([^"]+)"|'
    r'<time[^>]+datetime="([^"]+)"', re.IGNORECASE)
# Текстэн огноо: "2026-09-21 14:05", "2026.09.21", "Sep 19, 2026" (asia-basket)
_PUBLISHED_TEXT_RE = re.compile(
    r"\b(20\d{2})[-./](\d{1,2})[-./](\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?"
    r"|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? (\d{1,2}), (20\d{2})")
_MONTHS = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def fetch_published_ts(article_url: str) -> float:
    """Нийтлэлийн хуудасны meta-аас (og:article:published_time г.м.)
    нийтлэгдсэн цагийг уншина. Олдохгүй бол 0. HTML жагсаалтын эх
    сурвалжид огноо байдаггүй тул хуучин мэдээ "өнөөдөр" гэж орохоос
    сэргийлнэ (2026-09-21 ноорог: 9-р сарын 10-ны мэдээ 21-нд орох гэж байсан)."""
    try:
        resp = requests.get(article_url, timeout=12,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128"})
        m = _PUBLISHED_META_RE.search(resp.text[:60000])
        if not m:
            # Meta байхгүй бол хуудасны текстэн дэх эхний огноо (title-ийн ойролцоо)
            body = re.sub(r"<[^>]+>", " ", resp.text[:80000])
            t = _PUBLISHED_TEXT_RE.search(body)
            if not t:
                return 0.0
            if t.group(1):
                dt = datetime(int(t.group(1)), int(t.group(2)), int(t.group(3)),
                              int(t.group(4) or 0), int(t.group(5) or 0), tzinfo=timezone(timedelta(hours=8)))
            else:
                dt = datetime(int(t.group(8)), _MONTHS[t.group(6)], int(t.group(7)), tzinfo=timezone.utc)
            return dt.timestamp()
        raw = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        raw = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", raw)  # +0800 → +08:00
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception as e:
        log.info(f"Нийтлэлийн огноо уншиж чадсангүй ({article_url[:50]}): {e}")
        return 0.0


def fetch_html_list(category: str, source: dict) -> list:
    """RSS-гүй сайтын ангиллын хуудаснаас (гарчиг, линк) хосыг уншина.
    Агуулга, зураг нь дараа нь extract_article_context()-оор нийтлэлийн
    хуудаснаас ирнэ (og:description + body). Огноо мэдэгдэхгүй тул
    published_ts=0; шинэ линк л posted_ids-д байхгүй тул нэг л удаа орно."""
    results = []
    try:
        resp = requests.get(source["url"], timeout=15,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128"})
        resp.raise_for_status()
    except Exception as e:
        log.warning(f"HTML жагсаалт татахад алдаа [{source['name']}]: {e}")
        return results
    link_re = re.compile(source["link_re"])
    kw = source.get("keywords")
    seen = set()
    scanned = 0
    scan_limit = source.get("scan_limit", 12)   # хуудасны дээд хэсэг = шинэ; илүүг огноогоор шалгахгүй (HTTP хэмнэнэ)
    for href, inner in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', resp.text, re.S):
        if scanned >= scan_limit:
            break
        if not link_re.search(f'href="{href}"'):
            continue
        title = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", inner)).strip())
        if len(title) < 25 or href in seen:
            continue
        seen.add(href)
        if kw and not re.search(kw, title, re.IGNORECASE):
            continue
        url = href if href.startswith("http") else source.get("base", "") + href
        scanned += 1
        published_ts = fetch_published_ts(url)
        if published_ts:
            age_h = (datetime.now(timezone.utc).timestamp() - published_ts) / 3600
            if age_h > MAX_ARTICLE_AGE_HOURS:
                log.info(f"[ХУУЧИН] Алгаслаа ({age_h:.0f} цагийн өмнөх): {title[:50]}")
                continue
        else:
            log.info(f"[ОГНООГҮЙ] Алгаслаа (огноо олдсонгүй, эрсдэлтэй): {title[:50]}")
            continue
        results.append({
            "id": make_id(url),
            "category": category,
            "category_mn": CATEGORY_MN[category],
            "category_emoji": CATEGORY_EMOJI[category],
            "source_name": source["name"],
            "title": title,
            "summary": "",
            "url": url,
            "image_url": "",
            "published": datetime.fromtimestamp(published_ts, tz=timezone.utc).isoformat(),
            "published_ts": published_ts,
            "lang": source.get("lang", "mn"),
        })
        if len(results) >= source.get("max_items", 8):
            break
    log.info(f"{source['name']}: HTML жагсаалтаас {len(results)} сагсны мэдээ")
    return results


def fetch_espn_api(category: str, source: dict) -> list:
    """ESPN news JSON API (site.web.api.espn.com). Story + HeadlineNews төрлийг авна,
    Media (видео клип), podcast, тойм зэргийг алгасна. Огноо, зураг, тайлбар бэлэн."""
    results = []
    try:
        resp = requests.get(source["url"], timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
    except Exception as e:
        log.warning(f"ESPN API татахад алдаа [{source['name']}]: {e}")
        return results
    now = datetime.now(timezone.utc)
    for art in articles:
        if art.get("type") not in ("Story", "HeadlineNews"):
            continue
        title = (art.get("headline") or "").strip()
        url = ((art.get("links") or {}).get("web") or {}).get("href", "")
        if not title or not url or is_roundup_title(title):
            continue
        published_ts = 0.0
        try:
            dt = datetime.fromisoformat((art.get("published") or "").replace("Z", "+00:00"))
            published_ts = dt.timestamp()
            if now - dt > timedelta(hours=MAX_ARTICLE_AGE_HOURS):
                continue
        except Exception:
            pass
        imgs = art.get("images") or []
        results.append({
            "id": make_id(url),
            "category": category,
            "category_mn": CATEGORY_MN[category],
            "category_emoji": CATEGORY_EMOJI[category],
            "source_name": "ESPN",
            "title": title,
            "summary": clean_summary(art.get("description") or "", max_chars=900),
            "url": url,
            "image_url": (imgs[0].get("url") if imgs else "") or "",
            "published": art.get("published", ""),
            "published_ts": published_ts,
            "lang": "en",
        })
    log.info(f"{source['name']}: API-аас {len(results)} мэдээ (48ц дотор, Story/HeadlineNews)")
    return results


def fetch_category(category: str, sources: list) -> list:
    """Нэг категорийн бүх эх сурвалжаас мэдээ татах"""
    results = []

    for source in sources:
        try:
            log.info(f"Татаж байна: {source['name']}")
            if source.get("type") == "html":
                results.extend(fetch_html_list(category, source))
                continue
            if source.get("type") == "espn_api":
                results.extend(fetch_espn_api(category, source))
                continue
            feed = feedparser.parse(source["url"])

            if feed.bozo:
                log.warning(f"RSS алдаа: {source['name']}")
                continue

            for entry in feed.entries[:source.get("max_items", 12)]:  # 48ц-ийн шүүлтүүр байгаа тул 12 хүртэл
                url = entry.get("link", "")
                if not url:
                    continue

                # Тойм/live blog/listicle-ийг алгасна — нэг тодорхой
                # үйл явдлын мэдээ биш тул постонд тохирохгүй
                if is_roundup_title(entry.get("title", "")):
                    log.info(f"[ТОЙМ] Алгаслаа (roundup/live төрөл): {entry.get('title', '')[:50]}")
                    continue

                # Ерөнхий спортын feed-ээс зөвхөн сагсны мэдээг үлдээх
                kw = source.get("keywords")
                if kw:
                    haystack = f"{entry.get('title', '')} {entry.get('summary', '')}"
                    if not re.search(kw, haystack, re.IGNORECASE):
                        continue

                # Хуучин мэдээг алгасах — зөвхөн сүүлийн MAX_ARTICLE_AGE_HOURS
                # цагийн дотор нийтлэгдсэн мэдээг л авна
                published_ts = 0.0
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    published_ts = published_dt.timestamp()
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
                    # Шинэлэг байдлаар эрэмбэлэхэд ашиглана (0 = тодорхойгүй)
                    "published_ts": published_ts,
                    "lang": source.get("lang", "en"),
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
