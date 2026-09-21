"""
Auto News Poster - Монгол мэдээ автомат постлогч
Зохиогчийн эрх аюулгүй: зөвхөн хураангуй + эх линк постолно
"""

import logging
import os
import sys
from modules.fetcher import (
    fetch_all_news, find_image_from_other_sources,
    pick_best_image, extract_article_context, find_context_from_other_sources
)
from modules.writer import write_article, is_valid_mongolian, filter_relevant_news, polish_article
from modules.image_fallback import get_fallback_image
from modules.poster import post_to_all_platforms, check_facebook_token
from modules.storage import load_posted, save_posted, load_posted_topics, alert_due
from modules.dedup import is_duplicate_topic
from modules import telegram_notify
from modules import quote_card
from modules import gemini_image
from modules.translator import google_translate
from modules import espn_api
from modules import nba_scores
from modules import nba_digest
from modules import cards
from modules import scheduler
from modules import ledger
from modules import lint_mn
from modules import stat_card

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

MAX_POSTS_PER_RUN = int(os.environ.get("MAX_POSTS_PER_RUN", "2"))


def _translate_overlay(text_en: str) -> str:
    """
    Quote card дээр давхарлах богино текстийг (ишлэл/гарчиг) Gemini-ээр
    Монгол руу орчуулна. Богино текстэнд Google Translate утга эвддэг
    ("Rice ill" → "Райс алдаатай өвчтэй") тул үндсэн бичигчтэй ижил
    чанарын загвар ашиглана. Бүтэлгүйтвэл хоосон буцаана (дуудагч тал
    Google Translate руу өөрөө шилжинэ).
    """
    from modules import gemini_compare
    if not text_en or not gemini_compare.is_enabled():
        return ""
    system = (
        "Чи Монголын спортын мэдээний гарчиг орчуулагч. Өгөгдсөн богино "
        "Англи текстийг байгалийн, утга зөв Монгол хэл рүү орчуул. "
        "Хүн, багийн нэрийг БҮХЭЛДЭЭ Латин үсгээр үлдээ. "
        "Зөвхөн орчуулгыг бич — тайлбар, хашилт, өөр юу ч бүү нэм."
    )
    result = gemini_compare.generate(system, text_en)
    result = (result or "").strip().strip('"\u201c\u201d')
    # Богино гарчиг 200 тэмдэгтээс хэтрэхгүй байх ёстой — хэтэрвэл
    # загвар тайлбар нэмсэн байх магадлалтай тул хэрэглэхгүй
    if not result or len(result) > 220:
        return ""
    return result


def run():
    log.info("=== Auto News Poster эхэллээ ===")

    # Token дууссан бол Gemini/Groq-ийн эрх үрэлгүй ЭХЭНД нь зогсоод эзэнд хэлнэ
    token_error = check_facebook_token()
    if token_error:
        log.error(f"🛑 {token_error}")
        if alert_due("fb_token"):
            telegram_notify.notify_alert(token_error + "\nGitHub Secrets → FB_ACCESS_TOKEN-ийг шинэчилнэ үү.")
        sys.exit(1)

    posted_ids = load_posted()
    posted_topics = load_posted_topics()
    log.info(f"Өмнө постолсон мэдээ: {len(posted_ids)} ширхэг")

    all_news = fetch_all_news()
    log.info(f"Нийт татсан мэдээ: {len(all_news)} ширхэг")

    # ДӨНГӨЖ ДУУССАН NBA ТОГЛОЛТ (ESPN scoreboard) — редакцийн бодлогын №1,
    # шүүлтүүр давахгүй, үргэлж эхэнд
    recaps = nba_scores.fetch_finished_games(posted_ids)
    # S2: ганцаарчилсан recap зөвхөн онцгой тоглолтод (playoff / OT / ≤3 оноо);
    # бусад нь 13:00-ийн "Өглөөний NBA" тоймд орно
    skipped = [g["title"] for g in recaps if not nba_digest.should_post_recap(g)]
    recaps = [g for g in recaps if nba_digest.should_post_recap(g)]
    if skipped:
        log.info(f"[NBA SCORES] Өглөөний тоймд үлдээв ({len(skipped)}): " + "; ".join(skipped[:3]))

    new_news = [n for n in all_news if n["id"] not in posted_ids]
    log.info(f"Шинэ мэдээ: {len(new_news)} ширхэг (+{len(recaps)} тоглолтын үр дүн)")

    if not new_news and not recaps:
        log.info("Шинэ мэдээ байхгүй. Дуусгалаа.")
        return

    # Ач холбогдлын ОНОО — босгоос доош бүгд хасагдана, үлдсэн нь
    # оноо → шинэлэг байдлаар эрэмбэлэгдсэн ирнэ
    new_news = filter_relevant_news(new_news) if new_news else []
    new_news = recaps + new_news

    # СЭДВИЙН ДАВХАРДЛЫН ШҮҮЛТҮҮР:
    # 1) Сүүлийн 48ц-д постолсон сэдэвтэй давхцвал алгасна
    #    (BBC + Sky Sports ижил мэдээ бичихэд URL өөр тул ID-дедуп
    #    барьж чадахгүй — Guehi-гийн мэдээ 2 удаа гарсны шалтгаан)
    # 2) Нэг run доторх batch-д ч мөн адил шалгана
    recent_titles = [t["title"] for t in posted_topics]
    to_post = []
    for n in new_news:
        if is_duplicate_topic(n.get("title", ""), recent_titles):
            log.info(f"⏭️ Ижил сэдэв тул алгаслаа: {n['title'][:50]}")
            posted_ids.add(n["id"])  # дахин оролдохгүй
            continue
        to_post.append(n)
        recent_titles.append(n.get("title", ""))  # batch доторх давхардлыг ч барина
        if len(to_post) >= MAX_POSTS_PER_RUN:
            break

    log.info(f"Постолох мэдээ: {len(to_post)} ширхэг")

    success_count = 0
    for news in to_post:
        try:
            log.info(f"Боловсруулж байна: {news['title'][:60]}...")
            log.info(f"  [ДИАГНОСТИК] Эх агуулга (эхний 100): {news.get('summary', '')[:100]!r}")

            # Эх хуудаснаас og:description + body excerpt-ийг НИЙТЛЭЛ
            # БИЧИХЭЭС ӨМНӨ татна — Gemini-д RSS-ийн богино/хоосон
            # summary-с илүү бодит материал өгнө (доорх image-ийн
            # логикт ч энэ дуудлагаар аль хэдийн олдсон og:image-ийг
            # дахин ашиглана, давхар HTTP татахгүй)
            context = extract_article_context(news.get("url", ""))

            # ЭХ СУРВАЛЖ BOT-ХАМГААЛАЛТААР ХААГДСАН эсэхийг шалгана
            # (жишээ: ESPN HTTP 202 stub хуудас буцаадаг, og:description/
            # body_excerpt хоосон гардаг). Ийм тохиолдолд Google News-ээр
            # ижил сэдвийг бичсэн ӨӨР сайтаас (NBC Sports, Yahoo г.м.)
            # агуулгыг нөхөж хайна.
            content_len = len(context.get("og_description", "")) + len(context.get("body_excerpt", ""))
            if content_len < 150:
                log.info(f"[ДИАГНОСТИК context] Эх сурвалжийн агуулга хомс ({content_len}ch) — өөр сайтаас нөхөж үзье")
                # ESPN бол эхлээд өөрийнх нь JSON API-аас текстийг авна —
                # 403 өгдөг HTML-ийн оронд headline + description ирдэг
                alt = {}
                if "espn.com" in news.get("url", ""):
                    alt = espn_api.get_context(news.get("url", ""))
                if len(alt.get("og_description", "")) + len(alt.get("body_excerpt", "")) < 150:
                    alt = find_context_from_other_sources(news.get("title", ""))
                alt_len = len(alt.get("og_description", "")) + len(alt.get("body_excerpt", ""))
                if alt_len > content_len:
                    if alt.get("og_description"):
                        context["og_description"] = alt["og_description"]
                    if alt.get("body_excerpt"):
                        context["body_excerpt"] = alt["body_excerpt"]
                    if not context.get("og_image") and alt.get("og_image"):
                        context["og_image"] = alt["og_image"]

            news["og_description"] = context["og_description"]
            news["body_excerpt"] = context["body_excerpt"]

            written = write_article(news)

            # ЧАНАРЫН ХАМГААЛАЛТ: орчуулга/бичвэр бүтэлгүйтсэн бол
            # (англи хэвээр эсвэл хоосон) энэ мэдээг огт постлохгүй алгасна.
            if not is_valid_mongolian(written.get("article_mn", ""), min_len=40):
                log.warning(f"⏭️ Орчуулга/бичвэр чанаргүй тул алгаслаа: {news['title'][:40]}")
                posted_ids.add(news["id"])  # дахин оролдохгүйн тулд тэмдэглэнэ
                continue

            # РЕДАКТОРЫН ДАМЖЛАГА: эх баримттай тулгаж, хэл найруулгыг засна
            written["article_mn"] = polish_article(written, written["article_mn"])

            # S6 ХЭЛНИЙ LINT: калька/буруу үг → редакторт нэг удаа буцаана → үлдсэнийг 1:1 солино
            hits = lint_mn.check(written["article_mn"])
            if hits:
                log.warning(f"[LINT] {len(hits)} олдвор: {lint_mn.report(hits)}")
                written["article_mn"] = polish_article(written, written["article_mn"], lint_note=lint_mn.report(hits))
                hits = lint_mn.check(written["article_mn"])
                if hits:
                    written["article_mn"], n_fixed = lint_mn.autofix(written["article_mn"])
                    log.warning(f"[LINT] редакторын дараа ч {len(hits)} үлдсэн, {n_fixed}-ийг кодоор солив")

            category_now = written.get("category", "")

            # ЗУРГИЙН ЭРЭМБЭ (хэмжээ-шалгалттай):
            # УРЬД НЬ: RSS-ийн image_url (ихэвчлэн 140-400px жижиг
            # thumbnail!) байвал og:image-руу огт очилгүй шууд ашиглаад,
            # quote_card 1200px болгож томруулахад бүдэг гардаг байсан.
            # ОДОО: бүх нэр дэвшигчийг цуглуулж, эхний ≥700px-ийг сонгоно:
            # 1) RSS-ийн зураг  2) og:image  3) өөр сайтын og:image
            # Аль нь ч том биш бол → Pollinations/Wikimedia/Unsplash fallback
            candidates = [written.get("image_url", ""), context.get("og_image", "")]

            # ESPN бол HTML scrape биш нээлттэй JSON API-аас нь зургийг авна —
            # GitHub Actions-ийн IP-ээс espn.com-ийн HTML хуудас 403 өгдөг
            # (Akamai bot protection) ч site.api.espn.com API нь өгдөггүй
            if "espn.com" in news.get("url", ""):
                candidates.append(espn_api.get_image(news.get("url", "")))

            best = pick_best_image(candidates)
            if not best:
                other_img = find_image_from_other_sources(written.get("title", ""))
                best = pick_best_image([other_img]) if other_img else ""

            if best:
                written["image_url"] = best
            else:
                fallback = get_fallback_image(category_now, written.get("title", ""))
                written["image_url"] = fallback.get("url", "")
                written["image_bytes"] = fallback.get("bytes", b"")

            # restyle_photo: Gemini image квот=0 тул одоогоор идэвхгүй.
            # Google AI Studio → Billing идэвхжүүлсний дараа доорх
            # блокийг uncomment хийнэ:
            #
            # log.info(f"[ДИАГНОСТИК] category={category_now!r}, image_url={'байна' if written.get('image_url') else 'ХООСОН'}")
            # if category_now in ("sports", "music") and written.get("image_url"):
            #     restyled = gemini_image.restyle_photo(image_url=written["image_url"])
            #     if restyled:
            #         written["image_bytes"] = restyled
            #         written["image_url"] = ""
            #         log.info("[ДИАГНОСТИК] restyle АМЖИЛТТАЙ")
            #     else:
            #         log.info("[ДИАГНОСТИК] restyle БҮТЭЛГҮЙТЭВ — эх зураг хэвээр ашиглана")
            log.info(f"[ДИАГНОСТИК] category={category_now!r}, image_url={'байна' if written.get('image_url') else 'ХООСОН'}")

            # Давхарлах текст тодорхойлох: бодит ишлэл байвал түүнийг,
            # эсвэл (sports/music категорид) гарчгийг ашиглана.
            # Хөгжимд дууны нэрийг "ишлэл" гэж андуурахаас сэргийлж, тэнд
            # quote-хайлт хийхгүй.
            # ТОГЛОЛТЫН ҮР ДҮНГИЙН МЭДЭЭ → ESPN маягийн stat card оролдоно.
            # Стат олдохгүй бол хэвийн quote card руугаа үргэлжилнэ.
            stat_done = False

            # S8 ЗУРГИЙН СИСТЕМ: HTML→Chromium карт. Recap → recap карт (scoreboard
            # өгөгдлөөс); бусад → төрлөөр deal/quote/news. Рендер унавал доорх
            # хуучин PIL зам хэвээр ажиллана.
            if news.get("kind") == "game_recap" and news.get("card"):
                png = cards.recap_card(news["card"])
                if png:
                    written["image_bytes"], written["image_url"], stat_done = png, "", True
                    written["card_kind"] = "recap"
                    log.info("🎨 Recap карт (HTML) үүслээ")
            elif category_now in ("basketball", "mn_basketball"):
                quote_en_early = quote_card.extract_quote(f"{news.get('title', '')} {news.get('summary', '')} {news.get('og_description', '')}")
                headline_mn = _translate_overlay(news.get("title", "")) or written.get("title_mn", "")
                quote_mn_early = _translate_overlay(quote_en_early) if quote_en_early and len(quote_en_early) > 30 else ""
                entities = espn_api.get_entities(news.get("url", "")) if "espn.com" in news.get("url", "") else {}
                photo = written.get("image_url", "")  # ≥700px сонгогдсон эх зураг (fallback биш бол)
                if written.get("image_bytes") and not photo:
                    photo = ""  # fallback/AI зураг — news картанд хэрэглэхгүй
                png, ck = cards.build_for_news(news, written, headline_mn, quote_mn_early, entities, photo)
                if png:
                    written["image_bytes"], written["image_url"], stat_done = png, "", True
                    written["card_kind"] = ck
                    log.info(f"🎨 {ck} карт (HTML) үүслээ")

            if not stat_done and category_now in ("basketball", "mn_basketball", "football", "ufc", "sports") and \
                    (written.get("image_url") or written.get("image_bytes")):
                stats = stat_card.extract_stats(
                    news.get("title", ""),
                    news.get("summary", ""),
                    (context.get("og_description", "") + " " + context.get("body_excerpt", ""))
                    if isinstance(context, dict) else "",
                )
                if stats:
                    card = stat_card.generate_stat_card(
                        stats,
                        category_mn=written.get("category_mn", ""),
                        image_url=written.get("image_url", ""),
                        image_bytes=written.get("image_bytes", b""),
                    )
                    if card:
                        written["image_bytes"] = card
                        written["image_url"] = ""
                        stat_done = True

            source_text = f"{news.get('title', '')} {news.get('summary', '')}"
            quote_en = quote_card.extract_quote(source_text) if category_now != "music" else ""
            if quote_en:
                log.info(f"  [ДИАГНОСТИК] Энэ мэдээ '{news['title'][:50]}' → ишлэл олдлоо: {quote_en[:80]!r} | эх сурвалж: {written.get('source_name', '?')}")

            overlay_text_en = quote_en
            # Шинэ спорт категориуд (basketball/football/ufc) бүгд гарчгийн
            # давхаргатай quote card авна
            if not overlay_text_en and category_now in ("sports", "music", "basketball", "mn_basketball", "football", "ufc"):
                overlay_text_en = news.get("title", "")  # ишлэлгүй бол гарчгийг ашиглана

            if not stat_done and overlay_text_en and (written.get("image_url") or written.get("image_bytes")):
                # УРЬД НЬ: ишлэлийг Google Translate-аар орчуулдаг байсан нь
                # "Райс алдаатай өвчтэй байна" маягийн утгагүй гарчиг үүсгэсэн.
                # ОДОО: Gemini-ээр (үндсэн бичигчтэй ижил чанараар) орчуулж,
                # бүтэлгүйтвэл л Google Translate-руу буцна.
                overlay_text_mn = _translate_overlay(overlay_text_en)
                if not overlay_text_mn and not quote_en:
                    overlay_text_mn = written.get("title_mn", "")
                if not overlay_text_mn:
                    overlay_text_mn = google_translate(overlay_text_en)

                if overlay_text_mn:
                    card_bytes = quote_card.generate_quote_card(
                        quote_mn=overlay_text_mn,
                        source_name=written.get("source_name", "Эх сурвалж"),
                        category_mn=written.get("category_mn", ""),
                        image_url=written.get("image_url", ""),
                        image_bytes=written.get("image_bytes", b"")
                    )
                    if card_bytes:
                        written["image_bytes"] = card_bytes
                        written["image_url"] = ""
                        log.info(f"📇 Зурган давхарга ашиглав: {overlay_text_mn[:50]}...")

            written["score"] = news.get("score", 0)
            written["kind"] = news.get("kind", "")
            written = scheduler.assign(written)   # S1: слот эсвэл шууд
            result = post_to_all_platforms(written)

            if result["success"]:
                ledger.record(written, result)    # S3: дэвтэрт бүртгэнэ
                posted_ids.add(news["id"])
                import time as _t
                posted_topics.append({"title": news.get("title", ""), "ts": _t.time()})
                success_count += 1
                log.info(f"✅ Амжилттай: {news['title'][:40]}")
            else:
                log.warning(f"⚠️ Алдаа: {result['error']}")

            # Telegram мэдэгдэл (хүлээхгүй, зөвхөн FYI; draft горимд илгээхгүй)
            if not os.environ.get("AUTONEWS_DRAFT_DIR"):
                telegram_notify.notify_posted(written, result["success"], result.get("error") or "")

            import time
            time.sleep(3)

        except Exception as e:
            log.error(f"❌ Алдаа гарлаа [{news.get('title','?')[:40]}]: {e}")
            continue

    save_posted(posted_ids, posted_topics)
    log.info(f"=== Дууслаа: {success_count}/{len(to_post)} амжилттай ===")
    if to_post and success_count == 0:
        # Постлох мэдээ байсан ч нэг нь ч гараагүй — ажиллагааг улаанаар дуусгана
        sys.exit(1)


if __name__ == "__main__":
    run()
