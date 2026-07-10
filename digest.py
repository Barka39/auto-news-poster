"""
Digest (тойм) пост — 12:00, 19:00 цагт ажиллана.

Тухайн үеийн хооронд ирсэн, ГЭХДЭЭ ганцаарчилсан постоор орж чадаагүй
мэдээнүүдийг НЭГ тойм постонд нэгтгэн оруулна. Ганцаарчилсан аль хэдийн
постолсон мэдээг давхардуулахгүй (posted_ids-аар шалгана).
"""

import logging
from modules.fetcher import (
    fetch_all_news, extract_og_image, pick_best_image, interleave_by_category
)
from modules.writer import write_digest, filter_relevant_news, is_valid_mongolian
from modules.poster import post_to_all_platforms
from modules.storage import load_posted, save_posted
from modules import telegram_notify
from modules import quote_card

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

MAX_DIGEST_ITEMS = 6  # Нэг тоймд дээд тал нь оруулах мэдээний тоо


def run():
    log.info("=== Digest (тойм) пост эхэллээ ===")

    posted_ids = load_posted()
    log.info(f"Өмнө постолсон мэдээ: {len(posted_ids)} ширхэг")

    all_news = fetch_all_news()
    log.info(f"Нийт татсан мэдээ: {len(all_news)} ширхэг")

    # Зөвхөн ганцаарчилсан постоор орж ЧАДААГҮЙ (posted_ids-д байхгүй) мэдээ
    new_news = [n for n in all_news if n["id"] not in posted_ids]
    log.info(f"Тоймд орох боломжтой мэдээ: {len(new_news)} ширхэг")

    if not new_news:
        log.info("Тоймд оруулах шинэ мэдээ байхгүй. Дуусгалаа.")
        return

    # КАТЕГОРИЙН ТЭНЦВЭР: fetch_all_news() Спорт→Хөгжим→Дэлхий дараалалтай
    # буцаадаг тул шүүлтүүрийн эхний 20 кандидатад Дэлхийн мэдээ бараг
    # ордоггүй байсан (жишээ: тойм 6/6-с Дэлхийн мэдээ 0 гарч байсан).
    # Ээлжлэн холихоор 3 категори тэгш өрсөлдөнө.
    new_news = interleave_by_category(new_news)
    new_news = filter_relevant_news(new_news)
    to_digest = new_news[:MAX_DIGEST_ITEMS]
    log.info(f"Тоймд орох мэдээ: {len(to_digest)} ширхэг")
    for n in to_digest:
        log.info(f"  - [{n['category_mn']}] {n['title'][:60]}")

    digest_text = write_digest(to_digest)

    if not is_valid_mongolian(digest_text, min_len=60):
        log.error("Тойм бичвэр бүтэлгүйтлээ — дуусгалаа")
        return

    # Тоймын COVER зураг: сонгогдсон мэдээ бүрийн зургаас коллаж үүсгэнэ.
    # УРЬД НЬ: digest пост огт зурагтгүй (image_url="", image_bytes=b"")
    # байсан тул FB/IG дээр текст ганцаараа, дүрс мэдээлэлгүй харагдаж
    # байсан. ОДОО: мэдээ бүрийн og:image-с хамгийн чанартайг сонгож,
    # 2 багана grid-т байрлуулна.
    cover_items = []
    for n in to_digest:
        candidates = [n.get("image_url", "")]
        if n.get("url"):
            candidates.append(extract_og_image(n["url"]))
        best = pick_best_image(candidates)
        if best:
            cover_items.append({"image_url": best, "category_mn": n.get("category_mn", "")})

    cover_bytes = quote_card.generate_digest_cover(cover_items) if cover_items else b""
    if cover_bytes:
        log.info(f"📇 Тоймын cover зураг ашиглав ({len(cover_items)} зурагтай коллаж)")
    else:
        log.warning("Тоймын cover зураг үүсгэж чадсангүй — зурагтгүй постлоно")

    # Тоймын постыг хэвлэх
    digest_news = {
        "title_mn": "Өнөөдрийн мэдээний тойм",
        "article_mn": digest_text,
        "category_mn": "Тойм",
        "category_emoji": "📰",
        "image_url": "",
        "image_bytes": cover_bytes,
    }

    result = post_to_all_platforms(digest_news)

    if result["success"]:
        # Тоймд орсон бүх мэдээг postolson гэж тэмдэглэнэ — ингэснээр
        # ганцаарчилсан постонд дахин давхардаж орохгүй
        for n in to_digest:
            posted_ids.add(n["id"])
        save_posted(posted_ids)
        log.info(f"✅ Тойм амжилттай постлогдлоо ({len(to_digest)} мэдээ)")
    else:
        log.warning(f"⚠️ Тойм постлоход алдаа: {result['error']}")

    telegram_notify.notify_posted(digest_news, result["success"])
    log.info("=== Дууслаа ===")


if __name__ == "__main__":
    run()
