"""
Digest (тойм) пост — 12:00, 19:00 цагт ажиллана.

Тухайн үеийн хооронд ирсэн, ГЭХДЭЭ ганцаарчилсан постоор орж чадаагүй
мэдээнүүдийг НЭГ тойм постонд нэгтгэн оруулна. Ганцаарчилсан аль хэдийн
постолсон мэдээг давхардуулахгүй (posted_ids-аар шалгана).
"""

import logging
from modules.fetcher import fetch_all_news
from modules.writer import write_digest, filter_relevant_news, is_valid_mongolian
from modules.poster import post_to_all_platforms
from modules.storage import load_posted, save_posted
from modules import telegram_notify

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

    new_news = filter_relevant_news(new_news)
    to_digest = new_news[:MAX_DIGEST_ITEMS]
    log.info(f"Тоймд орох мэдээ: {len(to_digest)} ширхэг")
    for n in to_digest:
        log.info(f"  - [{n['category_mn']}] {n['title'][:60]}")

    digest_text = write_digest(to_digest)

    if not is_valid_mongolian(digest_text, min_len=60):
        log.error("Тойм бичвэр бүтэлгүйтлээ — дуусгалаа")
        return

    # Тоймын постыг хэвлэх (зураггүй, зөвхөн текст)
    digest_news = {
        "title_mn": "Өнөөдрийн мэдээний тойм",
        "article_mn": digest_text,
        "category_mn": "Тойм",
        "category_emoji": "📰",
        "image_url": "",
        "image_bytes": b"",
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
