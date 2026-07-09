"""
Auto News Poster - Монгол мэдээ автомат постлогч
Зохиогчийн эрх аюулгүй: зөвхөн хураангуй + эх линк постолно
"""

import logging
from modules.fetcher import fetch_all_news, extract_og_image
from modules.writer import write_article, is_valid_mongolian, filter_relevant_news
from modules.image_fallback import get_fallback_image
from modules.poster import post_to_all_platforms
from modules.storage import load_posted, save_posted
from modules import telegram_notify
from modules import quote_card
from modules import gemini_image
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
            log.info(f"  [ДИАГНОСТИК] Эх агуулга (эхний 100): {news.get('summary', '')[:100]!r}")

            written = write_article(news)

            # ЧАНАРЫН ХАМГААЛАЛТ: орчуулга/бичвэр бүтэлгүйтсэн бол
            # (англи хэвээр эсвэл хоосон) энэ мэдээг огт постлохгүй алгасна.
            if not is_valid_mongolian(written.get("article_mn", ""), min_len=40):
                log.warning(f"⏭️ Орчуулга/бичвэр чанаргүй тул алгаслаа: {news['title'][:40]}")
                posted_ids.add(news["id"])  # дахин оролдохгүйн тулд тэмдэглэнэ
                continue

            # ХАМГИЙН НАЙДВАРТАЙ ЗУРАГ: тухайн өгүүллийн бодит хуудаснаас
            # og:image унших (мэдээний сайтууд өөрсдөө Facebook/Twitter-д
            # зориулж тохируулдаг стандарт tag). RSS-ийн media tag-аас
            # хамаагүй зөв тул эхэлж үүгээр орлуулна.
            og_image = extract_og_image(news.get("url", ""))
            if og_image:
                written["image_url"] = og_image
                log.info(f"[ДИАГНОСТИК] og:image ашиглав: {og_image[:80]}")
            elif not written.get("image_url"):
                # og:image олдохгүй, RSS-д ч зураг байхгүй бол
                # Wikimedia/Unsplash/Gemini-с зураг хайж олно
                fallback = get_fallback_image(
                    written.get("category", "world_news"),
                    written.get("title", "")
                )
                written["image_url"] = fallback.get("url", "")
                written["image_bytes"] = fallback.get("bytes", b"")

            category_now = written.get("category", "")

            # Sports/Music: жинхэнэ фото байвал (RSS/Wikimedia/Unsplash-с)
            # Gemini-ээр illustration маягт хөрвүүлнэ. Эх мөч, поз хэвээр,
            # зөвхөн дүрслэлийн хэв маяг өөрчлөгдөнө (шинэ дүр зохиохгүй).
            log.info(f"[ДИАГНОСТИК] category={category_now!r}, image_url={'байна' if written.get('image_url') else 'ХООСОН'}")
            if category_now in ("sports", "music") and written.get("image_url"):
                log.info("[ДИАГНОСТИК] restyle_photo дуудаж байна...")
                restyled = gemini_image.restyle_photo(image_url=written["image_url"])
                if restyled:
                    written["image_bytes"] = restyled
                    written["image_url"] = ""
                    log.info("[ДИАГНОСТИК] restyle АМЖИЛТТАЙ")
                else:
                    log.info("[ДИАГНОСТИК] restyle БҮТЭЛГҮЙТЭВ — эх зураг хэвээр ашиглана")
            else:
                log.info("[ДИАГНОСТИК] restyle нөхцөл хангагдаагүй тул алгаслаа")

            # Давхарлах текст тодорхойлох: бодит ишлэл байвал түүнийг,
            # эсвэл (sports/music категорид) гарчгийг ашиглана.
            # Хөгжимд дууны нэрийг "ишлэл" гэж андуурахаас сэргийлж, тэнд
            # quote-хайлт хийхгүй.
            source_text = f"{news.get('title', '')} {news.get('summary', '')}"
            quote_en = quote_card.extract_quote(source_text) if category_now != "music" else ""
            if quote_en:
                log.info(f"  [ДИАГНОСТИК] Энэ мэдээ '{news['title'][:50]}' → ишлэл олдлоо: {quote_en[:80]!r} | эх сурвалж: {written.get('source_name', '?')}")

            overlay_text_en = quote_en
            if not overlay_text_en and category_now in ("sports", "music"):
                overlay_text_en = news.get("title", "")  # ишлэлгүй бол гарчгийг ашиглана

            if overlay_text_en and (written.get("image_url") or written.get("image_bytes")):
                if quote_en:
                    overlay_text_mn = google_translate(quote_en)
                else:
                    overlay_text_mn = written.get("title_mn", "") or google_translate(overlay_text_en)

                if overlay_text_mn:
                    card_bytes = quote_card.generate_quote_card(
                        quote_mn=overlay_text_mn,
                        source_name=written.get("source_name", "Эх сурвалж"),
                        image_url=written.get("image_url", ""),
                        image_bytes=written.get("image_bytes", b"")
                    )
                    if card_bytes:
                        written["image_bytes"] = card_bytes
                        written["image_url"] = ""
                        log.info(f"📇 Зурган давхарга ашиглав: {overlay_text_mn[:50]}...")

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
