"""
Auto News Poster - Монгол мэдээ автомат постлогч
Зохиогчийн эрх аюулгүй: зөвхөн хураангуй + эх линк постолно
"""

import logging
from modules.fetcher import fetch_all_news
from modules.writer import write_article, is_valid_mongolian, filter_relevant_news
from modules.image_fallback import get_fallback_image
from modules.poster import post_to_all_platforms
from modules.storage import load_posted, save_posted
from modules import telegram_notify
from modules import quote_card
from modules.translator import google_translate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

MAX_POSTS_PER_RUN = 2


def run():
    log.info("=== Auto News Poster эхэллээ ===")

    posted_ids = load_posted()
    log.info(f"Өмнө постолсон мэдээ: {len(posted_ids)} ширхэг")

    all_news = fetch_all_news()
    log.info(f"Нийт татсан мэдээ: {len(all_news)} ширхэг")

    new_news = [n for n in all_news if n["id"] not in posted_ids]
    log.info(f"Шинэ мэдээ: {len(new_news)} ширхэг")

    if not new_news:
        log.info("Шинэ мэдээ байхгүй. Дуусгалаа.")
        return

    # Ач холбогдлын шүүлтүүр — Монгол уншигчдад сонирхолгүй жижиг мэдээг хасна
    new_news = filter_relevant_news(new_news)

    to_post = new_news[:MAX_POSTS_PER_RUN]
    log.info(f"Постолох мэдээ: {len(to_post)} ширхэг")

    success_count = 0
    for news in to_post:
        try:
            log.info(f"Боловсруулж байна: {news['title'][:60]}...")

            written = write_article(news)

            # ЧАНАРЫН ХАМГААЛАЛТ: орчуулга/бичвэр бүтэлгүйтсэн бол
            # (англи хэвээр эсвэл хоосон) энэ мэдээг огт постлохгүй алгасна.
            if not is_valid_mongolian(written.get("article_mn", ""), min_len=40):
                log.warning(f"⏭️ Орчуулга/бичвэр чанаргүй тул алгаслаа: {news['title'][:40]}")
                posted_ids.add(news["id"])  # дахин оролдохгүйн тулд тэмдэглэнэ
                continue

            # RSS-д зураг байхгүй бол Wikimedia/Unsplash/Gemini-с зураг хайж олно
            if not written.get("image_url"):
                fallback = get_fallback_image(
                    written.get("category", "world_news"),
                    written.get("title", "")
                )
                written["image_url"] = fallback.get("url", "")
                written["image_bytes"] = fallback.get("bytes", b"")

            # Quote card: эх сурвалжид БОДИТ ишлэл байвал (жинхэнэ зургийг
            # хэвээр нь ашиглаад), Pulse Sports загварын quote card үүсгэнэ.
            source_text = f"{news.get('title', '')} {news.get('summary', '')}"
            quote_en = quote_card.extract_quote(source_text)
            if quote_en and (written.get("image_url") or written.get("image_bytes")):
                quote_mn = google_translate(quote_en)
                if quote_mn:
                    card_bytes = quote_card.generate_quote_card(
                        quote_mn=quote_mn,
                        source_name=written.get("source_name", "Эх сурвалж"),
                        image_url=written.get("image_url", ""),
                        image_bytes=written.get("image_bytes", b"")
                    )
                    if card_bytes:
                        written["image_bytes"] = card_bytes
                        written["image_url"] = ""
                        log.info(f"📇 Quote card ашиглав: {quote_mn[:50]}...")

            result = post_to_all_platforms(written)

            if result["success"]:
                posted_ids.add(news["id"])
                success_count += 1
                log.info(f"✅ Амжилттай: {news['title'][:40]}")
            else:
                log.warning(f"⚠️ Алдаа: {result['error']}")

            # Telegram мэдэгдэл (хүлээхгүй, зөвхөн FYI)
            telegram_notify.notify_posted(written, result["success"])

            import time
            time.sleep(3)

        except Exception as e:
            log.error(f"❌ Алдаа гарлаа [{news.get('title','?')[:40]}]: {e}")
            continue

    save_posted(posted_ids)
    log.info(f"=== Дууслаа: {success_count}/{len(to_post)} амжилттай ===")


if __name__ == "__main__":
    run()
