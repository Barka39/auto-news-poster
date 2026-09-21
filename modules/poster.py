"""
Постлох модуль — Facebook, Instagram, X (Twitter)
Бүх API зөвшөөрөгдсөн Graph API болон Tweepy ашиглана
Зурагтай пост дэмждэг (RSS-ийн featured image)
"""

import os
import logging
import requests
import tweepy

log = logging.getLogger(__name__)


# ============================================================
# ПОСТ ФОРМАТЛАХ
# ============================================================

def format_post(news: dict, platform: str) -> str:
    """
    Платформ тус бүрд тохирсон пост текст үүсгэх.
    Groq-ийн бичсэн дэлгэрэнгүй article_mn ашиглана.
    Эх сурвалж, линк ЗОРИУД ДУРДАХГҮЙ (хэрэглэгчийн хүсэлтээр).
    """
    article = news.get("article_mn", "").strip()

    if platform == "twitter":
        # X: 280 тэмдэгт хязгаар
        text = article
        if len(text) > 275:
            text = text[:272] + "..."
        return text

    elif platform in ["facebook", "instagram"]:
        footer = news.get("hashtag_footer", "#МонголМэдээ #Mongolia")
        return article + ("\n\n" + footer if footer else "")

    return article


# ============================================================
# FACEBOOK ПОСТЛОХ
# ============================================================

def post_to_facebook(news: dict) -> dict:
    """
    Facebook Page-д пост хийх.
    Зураг байвал /photos endpoint ашиглаж caption-тай зураг postолно:
    - image_url байвал: Facebook серверээс URL-г шууд татна
    - image_bytes байвал: multipart upload хийнэ (жишээ: Gemini-ийн
      үүсгэсэн зураг, URL биш raw bytes хэлбэртэй ирдэг)
    Зураг байхгүй бол /feed endpoint-оор текст пост хийнэ.
    """
    page_id = os.environ.get("FB_PAGE_ID")
    access_token = os.environ.get("FB_ACCESS_TOKEN")

    if not page_id or not access_token:
        return {"success": False, "error": "FB credentials байхгүй"}

    text = format_post(news, "facebook")
    image_url = news.get("image_url", "")
    image_bytes = news.get("image_bytes", b"")
    log.info(f"FB зураг: {'URL байна' if image_url else ('bytes байна (' + str(len(image_bytes)) + ')' if image_bytes else 'ХООСОН')}")

    # S1: товлосон пост — FB 10 минутаас 75 хоногийн хооронд зөвшөөрнө
    sched = {}
    if news.get("scheduled_publish_time"):
        sched = {"published": "false", "scheduled_publish_time": int(news["scheduled_publish_time"])}

    try:
        if image_bytes:
            # Үүсгэсэн карт (HTML/PIL) — multipart file upload
            url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
            response = requests.post(
                url,
                data={"caption": text, "access_token": access_token, **sched},
                files={"source": ("image.png", image_bytes, "image/png")},
                timeout=30
            )
        elif image_url:
            # Зурагтай пост — /photos endpoint (Facebook URL-г татна)
            url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
            response = requests.post(url, data={
                "caption": text,
                "url": image_url,
                "access_token": access_token, **sched
            }, timeout=20)
        else:
            # Зураггүй текст пост — /feed endpoint
            url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
            response = requests.post(url, data={
                "message": text,
                "access_token": access_token, **sched
            }, timeout=15)

        data = response.json()

        if "id" in data or "post_id" in data:
            post_id = data.get("post_id", data.get("id"))
            log.info(f"✅ Facebook: {post_id}" + (f" (товлогдсон: {news.get('slot')})" if sched else ""))
            return {"success": True, "id": post_id, "photo_id": data.get("id") if (image_bytes or image_url) else "",
                    "scheduled": bool(sched)}
        else:
            error = data.get("error", {}).get("message", str(data))
            log.error(f"❌ Facebook алдаа (зураг {'байсан' if (image_url or image_bytes) else 'байхгүй'}): {error}")
            if sched:
                log.warning("Товлосон постлоход алдаа — шууд постлохоор дахин оролдоно")
                return post_to_facebook({**news, "scheduled_publish_time": 0, "slot": ""})
            if image_url or image_bytes:
                log.warning(f"Зурагтай постлоход дээрх алдаа гарлаа — зураггүйгээр дахин оролдож байна")
                return post_to_facebook({**news, "image_url": "", "image_bytes": b""})
            return {"success": False, "error": error}

    except Exception as e:
        log.error(f"❌ Facebook exception: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# INSTAGRAM ПОСТЛОХ
# ============================================================

def post_to_instagram(news: dict) -> dict:
    """
    Instagram Business Account-д пост хийх.
    Instagram зурагтай пост л дэмждэг тул зураггүй мэдээг алгасна.
    """
    ig_account_id = os.environ.get("IG_ACCOUNT_ID")
    access_token = os.environ.get("FB_ACCESS_TOKEN")
    image_url = news.get("image_url", "")

    if not ig_account_id or not access_token:
        return {"success": False, "error": "IG credentials байхгүй"}

    if not image_url and news.get("fb_photo_id"):
        # S5: үүсгэсэн карт (bytes) — FB-д аль хэдийн байршсан зургийн нийтийн
        # URL-ийг авч IG-д өгнө (IG зөвхөн public URL хүлээн авдаг)
        try:
            r = requests.get(f"https://graph.facebook.com/v19.0/{news['fb_photo_id']}",
                             params={"fields": "images", "access_token": access_token}, timeout=15).json()
            imgs = sorted(r.get("images", []), key=lambda i: i.get("width", 0), reverse=True)
            if imgs:
                image_url = imgs[0]["source"]
                log.info("IG: FB-д байршсан картын URL-ийг ашиглана")
        except Exception as e:
            log.warning(f"IG: FB зургийн URL авахад алдаа: {e}")

    if not image_url:
        log.info("IG: зураггүй тул алгаслаа (Instagram зураг шаарддаг)")
        return {"success": True, "note": "Зураггүй тул IG алгасав"}

    text = format_post(news, "instagram")

    try:
        # Алхам 1: Container үүсгэх (зурагтай)
        container_url = f"https://graph.facebook.com/v19.0/{ig_account_id}/media"
        container_resp = requests.post(container_url, data={
            "caption": text,
            "image_url": image_url,
            "access_token": access_token
        }, timeout=20)

        container_data = container_resp.json()

        if "id" not in container_data:
            error = container_data.get("error", {}).get("message", str(container_data))
            log.error(f"❌ IG container алдаа: {error}")
            return {"success": False, "error": error}

        container_id = container_data["id"]

        # Алхам 2: Publish хийх
        publish_url = f"https://graph.facebook.com/v19.0/{ig_account_id}/media_publish"
        publish_resp = requests.post(publish_url, data={
            "creation_id": container_id,
            "access_token": access_token
        }, timeout=15)

        publish_data = publish_resp.json()

        if "id" in publish_data:
            log.info(f"✅ Instagram: {publish_data['id']}")
            return {"success": True, "id": publish_data["id"]}
        else:
            error = publish_data.get("error", {}).get("message", str(publish_data))
            log.error(f"❌ Instagram алдаа: {error}")
            return {"success": False, "error": error}

    except Exception as e:
        log.error(f"❌ Instagram exception: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# X (TWITTER) ПОСТЛОХ
# ============================================================

def post_to_twitter(news: dict) -> dict:
    """X (Twitter)-д твит хийх — Tweepy v4 ашиглана. Зурагтай бол зурагтайгаар."""
    api_key = os.environ.get("X_API_KEY")
    api_secret = os.environ.get("X_API_SECRET")
    access_token = os.environ.get("X_ACCESS_TOKEN")
    access_secret = os.environ.get("X_ACCESS_SECRET")

    if not all([api_key, api_secret, access_token, access_secret]):
        return {"success": False, "error": "X credentials байхгүй"}

    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret
        )

        text = format_post(news, "twitter")
        image_url = news.get("image_url", "")

        media_ids = None
        if image_url:
            try:
                # v1.1 API зураг upload хийхэд шаардлагатай
                auth = tweepy.OAuth1UserHandler(
                    api_key, api_secret, access_token, access_secret
                )
                api_v1 = tweepy.API(auth)

                img_resp = requests.get(image_url, timeout=15)
                img_resp.raise_for_status()

                import io
                media = api_v1.media_upload(
                    filename="news.jpg",
                    file=io.BytesIO(img_resp.content)
                )
                media_ids = [media.media_id]
            except Exception as e:
                log.warning(f"X зураг upload алдаа, зураггүй постлоно: {e}")

        response = client.create_tweet(text=text, media_ids=media_ids)

        if response.data:
            tweet_id = response.data["id"]
            log.info(f"✅ X (Twitter): {tweet_id}")
            return {"success": True, "id": tweet_id}
        else:
            return {"success": False, "error": "Tweet ID байхгүй"}

    except tweepy.TweepyException as e:
        log.error(f"❌ Twitter алдаа: {e}")
        return {"success": False, "error": str(e)}

    except Exception as e:
        log.error(f"❌ Twitter exception: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# БҮГДИЙГ НЭГТГЭН ПОСТЛОХ
# ============================================================

def _draft_dir() -> str:
    """LEGION S85: when AUTONEWS_DRAFT_DIR is set, nothing is posted here —
    each item is written as a draft JSON for LEGION's social hand, which
    posts it platform by platform with an intent before and a receipt
    after, and can look for it after a crash. The pipeline (fetch, write,
    image) is unchanged; only the last step moves behind a door that can
    be recovered."""
    return os.environ.get("AUTONEWS_DRAFT_DIR", "").strip()


def write_draft(news: dict, draft_dir: str) -> dict:
    import base64
    import hashlib
    import json
    import time

    os.makedirs(draft_dir, exist_ok=True)
    image_bytes = news.get("image_bytes", b"")
    draft = {
        "id": str(news.get("id") or hashlib.sha256(str(news.get("title", "")).encode("utf-8")).hexdigest()[:16]),
        "title": news.get("title", ""),
        "url": news.get("url", ""),
        "category": news.get("category", ""),
        "text": {platform: format_post(news, platform) for platform in ("facebook", "instagram", "twitter")},
        "image_url": news.get("image_url", ""),
        "image_png_base64": base64.b64encode(image_bytes).decode("ascii") if image_bytes else "",
        "drafted_at": time.time(),
    }
    path = os.path.join(draft_dir, f"news-{draft['id']}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(draft, handle, ensure_ascii=False, indent=2)
    log.info(f"📝 LEGION draft бичигдлээ (постлоогүй): {path}")
    return {"success": True, "draft": path, "platforms": {}, "error": None}


def post_to_all_platforms(news: dict) -> dict:
    """Facebook, Instagram, X-д нэг зэрэг постлох"""
    draft_dir = _draft_dir()
    if draft_dir:
        return write_draft(news, draft_dir)
    results = {}
    any_success = False

    fb_result = post_to_facebook(news)
    results["facebook"] = fb_result
    if fb_result["success"]:
        any_success = True
        if fb_result.get("photo_id") and not fb_result.get("scheduled"):
            news["fb_photo_id"] = fb_result["photo_id"]

    ig_result = post_to_instagram(news)
    results["instagram"] = ig_result
    if ig_result["success"]:
        any_success = True

    # S5: X-ийн secret хоосон, Монгол уншигч X дээр цөөн → анхдагчаар унтраалттай
    if os.environ.get("X_ENABLED", "0") == "1":
        x_result = post_to_twitter(news)
        results["twitter"] = x_result
        if x_result["success"]:
            any_success = True

    return {
        "success": any_success,
        "platforms": results,
        "error": None if any_success else "Бүх платформд алдаа гарлаа: " + "; ".join(
            f"{name}={r.get('error', '?')}" for name, r in results.items()
        )
    }


def check_facebook_token() -> str:
    """FB token-ийг ажил эхлэхээс ӨМНӨ нэг удаа шалгана. Хүчинтэй эсвэл
    тохируулаагүй бол "" буцаана; дууссан/буруу бол Graph-ийн алдааны
    текстийг буцаана (2026-09-08-аас 2 долоо хоног чимээгүй унасан тохиолдол).
    Сүлжээний түр алдаанд ажиллагааг зогсоохгүй."""
    token = os.environ.get("FB_ACCESS_TOKEN")
    page_id = os.environ.get("FB_PAGE_ID")
    if not token or not page_id:
        return ""
    try:
        r = requests.get(f"https://graph.facebook.com/v19.0/{page_id}",
                         params={"access_token": token, "fields": "id"}, timeout=15)
        if r.status_code == 200:
            return ""
        err = r.json().get("error", {}).get("message", r.text[:200])
        return f"Facebook token хүчингүй: {err}"
    except Exception:
        return ""
