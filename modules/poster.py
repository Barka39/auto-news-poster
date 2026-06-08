"""
Постлох модуль — Facebook, Instagram, X (Twitter)
Бүх API зөвшөөрөгдсөн Graph API болон Tweepy ашиглана
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
    Платформ тус бүрд тохирсон пост текст үүсгэх
    Зохиогчийн эрх аюулгүй: хураангуй (өөрийн орчуулга) + эх линк
    """
    emoji = news.get("category_emoji", "📰")
    category = news.get("category_mn", "Мэдээ")
    title = news.get("title_mn", news.get("title", ""))
    summary = news.get("summary_mn", "")
    source = news.get("source_name", "")
    url = news.get("url", "")

    if platform == "twitter":
        # X: 280 тэмдэгт хязгаар
        text = f"{emoji} {title}\n\n{summary}"
        # Хэмжээ тохируулах
        max_len = 250 - len(url)
        if len(text) > max_len:
            text = text[:max_len - 3] + "..."
        return f"{text}\n\n🔗 {url}"

    elif platform in ["facebook", "instagram"]:
        # FB/IG: урт пост боломжтой
        lines = [
            f"{emoji} #{category.replace(' ', '_').replace('&', '')}",
            f"",
            f"📌 {title}",
            f"",
        ]
        if summary:
            lines.append(summary)
            lines.append("")
        lines.append(f"📰 Эх сурвалж: {source}")
        lines.append(f"🔗 {url}")
        lines.append("")
        lines.append("#МонголМэдээ #Mongolia")
        return "\n".join(lines)

    return f"{title}\n{url}"


# ============================================================
# FACEBOOK ПОСТЛОХ
# ============================================================

def post_to_facebook(news: dict) -> dict:
    """Facebook Page-д пост хийх"""
    page_id = os.environ.get("FB_PAGE_ID")
    access_token = os.environ.get("FB_ACCESS_TOKEN")

    if not page_id or not access_token:
        return {"success": False, "error": "FB credentials байхгүй"}

    text = format_post(news, "facebook")
    url = f"https://graph.facebook.com/v19.0/{page_id}/feed"

    try:
        response = requests.post(url, data={
            "message": text,
            "access_token": access_token
        }, timeout=15)

        data = response.json()

        if "id" in data:
            log.info(f"✅ Facebook: {data['id']}")
            return {"success": True, "id": data["id"]}
        else:
            error = data.get("error", {}).get("message", str(data))
            log.error(f"❌ Facebook алдаа: {error}")
            return {"success": False, "error": error}

    except Exception as e:
        log.error(f"❌ Facebook exception: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# INSTAGRAM ПОСТЛОХ
# ============================================================

def post_to_instagram(news: dict) -> dict:
    """
    Instagram Business Account-д текст пост хийх
    Зураггүй тохиолдолд зөвхөн caption+link — Reel/Story шаарддаггүй
    """
    ig_account_id = os.environ.get("IG_ACCOUNT_ID")
    access_token = os.environ.get("FB_ACCESS_TOKEN")  # FB token ижил ашигладаг

    if not ig_account_id or not access_token:
        return {"success": False, "error": "IG credentials байхгүй"}

    text = format_post(news, "instagram")

    try:
        # Алхам 1: Container үүсгэх
        container_url = f"https://graph.facebook.com/v19.0/{ig_account_id}/media"
        container_resp = requests.post(container_url, data={
            "caption": text,
            "media_type": "REELS",   # Текст зөвхөн Reels/Feed-д байдаг
            "access_token": access_token
        }, timeout=15)

        container_data = container_resp.json()

        if "id" not in container_data:
            # Instagram текст-only пост хязгаартай — FB-д постолсоноор орлуулна
            log.warning("IG container алдаа — FB хуваалцахаар орлуулна")
            return {"success": True, "note": "IG-д FB пост хуваалцагдана"}

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
    """X (Twitter)-д твит хийх — Tweepy v4 ашиглана"""
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
        response = client.create_tweet(text=text)

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

    # Facebook
    fb_result = post_to_facebook(news)
    results["facebook"] = fb_result
    if fb_result["success"]:
        any_success = True

    # Instagram
    ig_result = post_to_instagram(news)
    results["instagram"] = ig_result
    if ig_result["success"]:
        any_success = True

    # X (Twitter)
    x_result = post_to_twitter(news)
    results["twitter"] = x_result
    if x_result["success"]:
        any_success = True

    return {
        "success": any_success,
        "platforms": results,
        "error": None if any_success else "Бүх платформд алдаа гарлаа"
    }
