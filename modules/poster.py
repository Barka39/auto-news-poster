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
        lines = [
            article,
            "",
            "#МонголМэдээ #Mongolia",
        ]
        return "\n".join(lines)

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

    try:
        if image_bytes:
            # Gemini-ийн үүсгэсэн raw зураг — multipart file upload
            url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
            response = requests.post(
                url,
                data={"caption": text, "access_token": access_token},
                files={"source": ("image.png", image_bytes, "image/png")},
                timeout=30
            )
        elif image_url:
            # Зурагтай пост — /photos endpoint (Facebook URL-г татна)
            url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
            response = requests.post(url, data={
                "caption": text,
                "url": image_url,
                "access_token": access_token
            }, timeout=20)
        else:
            # Зураггүй текст пост — /feed endpoint
            url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
            response = requests.post(url, data={
                "message": text,
                "access_token": access_token
            }, timeout=15)

        data = response.json()

        if "id" in data or "post_id" in data:
            post_id = data.get("post_id", data.get("id"))
            log.info(f"✅ Facebook: {post_id}")
            return {"success": True, "id": post_id}
        else:
            error = data.get("error", {}).get("message", str(data))
            log.error(f"❌ Facebook алдаа (зураг {'байсан' if (image_url or image_bytes) else 'байхгүй'}): {error}")
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

def post_to_all_platforms(news: dict) -> dict:
    """Facebook, Instagram, X-д нэг зэрэг постлох"""
    results = {}
    any_success = False

    fb_result = post_to_facebook(news)
    results["facebook"] = fb_result
    if fb_result["success"]:
        any_success = True

    ig_result = post_to_instagram(news)
    results["instagram"] = ig_result
    if ig_result["success"]:
        any_success = True

    x_result = post_to_twitter(news)
    results["twitter"] = x_result
    if x_result["success"]:
        any_success = True

    return {
        "success": any_success,
        "platforms": results,
        "error": None if any_success else "Бүх платформд алдаа гарлаа"
    }
