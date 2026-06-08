"""
Auto News Poster - Монгол мэдээ автомат постлогч
Зохиогчийн эрх аюулгүй: зөвхөн хураангуй + эх линк постолно
"""

import os
import json
import time
import logging
from datetime import datetime
from modules.fetcher import fetch_all_news
from modules.translator import translate_to_mongolian
from modules.poster import post_to_all_platforms
from modules.storage import load_posted, save_posted

# Лог тохиргоо
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# Нэг удаад хэдэн мэдээ постолох (лимит хамгаалалт)
MAX_POSTS_PER_RUN = 5  # GitHub Actions дуудалт бүрт 5 мэдээ

def run():
    log.info("=== Auto News Poster эхэллээ ===")
    
    # Өмнө постолсон мэдээний ID-уудыг ачаална (давхардал хамгаалалт)
    posted_ids = load_posted()
    log.info(f"Өмнө постолсон мэдээ: {len(posted_ids)} ширхэг")

    # 1. Мэдээ татах
    all_news = fetch_all_news()
    log.info(f"Нийт татсан мэдээ: {len(all_news)} ширхэг")

    # 2. Шинэ мэдээ шүүх (давхардахгүй)
    new_news = [n for n in all_news if n["id"] not in posted_ids]
    log.info(f"Шинэ мэдээ: {len(new_news)} ширхэг")

    if not new_news:
        log.info("Шинэ мэдээ байхгүй. Дуусгалаа.")
        return

    # 3. Лимит тохируулах
    to_post = new_news[:MAX_POSTS_PER_RUN]
    log.info(f"Постолох мэдээ: {len(to_post)} ширхэг")

    success_count = 0
    for news in to_post:
        try:
            log.info(f"Боловсруулж байна: {news['title'][:60]}...")
            
            # 4. Монгол орчуулга
            translated = translate_to_mongolian(news)
            
            # 5. Бүх платформд постлох
            result = post_to_all_platforms(translated)
            
            if result["success"]:
                posted_ids.add(news["id"])
                success_count += 1
                log.info(f"✅ Амжилттай: {news['title'][:40]}")
            else:
                log.warning(f"⚠️ Алдаа: {result['error']}")

            # Платформын API rate limit хамгаалалт
            time.sleep(3)

        except Exception as e:
            log.error(f"❌ Алдаа гарлаа [{news.get('title','?')[:40]}]: {e}")
            continue

    # 6. Постолсон мэдээний ID хадгалах
    save_posted(posted_ids)
    log.info(f"=== Дууслаа: {success_count}/{len(to_post)} амжилттай ===")

if __name__ == "__main__":
    run()
