"""
Gemini-аар (Nano Banana, gemini-2.5-flash-image) зураг үүсгэх/хөрвүүлэх модуль.
GEMINI_API_KEY тохируулсан үед л идэвхжинэ.
Үнэгүй tier: өдөрт 500 зураг.

Бүх зураг автоматаар SynthID watermark агуулна (AI-аар үүсгэсэн гэдгийг илрүүлэх боломжтой болгодог далд тэмдэг).

2 функц:
1. generate_image_bytes() — ЕРӨНХИЙ, ХҮНГҮЙ дүрслэл (талбай, трофей г.м.) ШИНЭЭР үүсгэнэ. Жинхэнэ хүн зохиомлоор зурахгүй.
2. restyle_photo() — ЖИНХЭНЭ ФОТОГ illustration маягт хөрвүүлнэ. Эх зураг дээрх хүний бодит поз, дүр төрх, мөч ХЭВЭЭР хадгалагдана — зөвхөн дүрслэлийн хэв маяг (photorealistic → illustrated) өөрчлөгдөнө.
Энэ нь шинэ дүр зохиохгүй, зөвхөн БОДИТ зургийг өөр хэв маягаар дахин зурах тул редакцийн зурган карикатур/иллюстрацитай адилтгах боломжтой, аюулгүй арга.
"""

import os
import base64
import logging
import requests
import time  # Хүлээлт үүсгэхэд ашиглана

log = logging.getLogger(__name__)

GEMINI_IMAGE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

# Тогтмол brand style — бүх зураг ижил "гар зурсан" маягтай харагдана
STYLE_SUFFIX = (
    "flat vector illustration style, modern editorial sports-news "
    "aesthetic, vibrant colors, clean geometric shapes, NOT photorealistic, "
    "NOT a real photograph, no text, no watermark, no logos"
)

CATEGORY_PROMPTS = {
    "sports": "a dynamic empty basketball/sports arena scene, dramatic lighting, no people",
    "music": "a vibrant concert stage with lights, empty venue, no people",
    "world_news": "an abstract global news concept, world map or city skyline silhouette, no people",
}

def is_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))

def generate_image_bytes(category: str) -> bytes:
    """
    Ерөнхий (хүнгүй) сэдэвчилсэн зургийг Gemini-ээр үүсгэж, raw image bytes-г буцаана
    (URL биш — Facebook-д multipart upload хийхэд ашиглана).
    Амжилтгүй бол хоосон bytes буцаана.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return b""

    scene = CATEGORY_PROMPTS.get(category, CATEGORY_PROMPTS["world_news"])
    prompt = f"{scene}, {STYLE_SUFFIX}"

    try:
        response = requests.post(
            f"{GEMINI_IMAGE_URL}?key={api_key}",
            json={
                "contents": [
                    {"role": "user", "parts": [{"text": prompt}]}
                ]
            },
            timeout=40
        )
        response.raise_for_status()
        data = response.json()
        parts = data["candidates"][0]["content"]["parts"]
        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and inline_data.get("data"):
                image_bytes = base64.b64decode(inline_data["data"])
                log.info(f"Gemini зураг үүсгэв ({category}, {len(image_bytes)} bytes)")
                return image_bytes

        log.warning("Gemini хариунд зураг олдсонгүй")
        return b""
    except Exception as e:
        log.warning(f"Gemini зураг үүсгэхэд алдаа: {e}")
        return b""

def restyle_photo(image_url: str = "", image_bytes: bytes = b"") -> bytes:
    """
    ЖИНХЭНЭ фотог Gemini-ээр illustration/cartoon маягт хөрвүүлнэ.
    Үнэгүй таримын 429 алдаанаас сэргийлж хүсэлт бүрийн өмнө 12 секунд зориуд хүлээнэ.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.info("[ДИАГНОСТИК restyle] GEMINI_API_KEY байхгүй — restyle алгасав")
        return b""

    # === РЕЙТ ХИЗГААРААС СЭРГИЙЛЭХ ХҮЛЭЭЛТ ===
    # Олон мэдээ зэрэг боловсруулах үед Gemini блоклохоос сэргийлж 12 секунд амраана.
    log.info("[ДИАГНОСТИК restyle] Gemini Rate Limit-ээс хамгаалж 12 секунд хүлээж байна...")
    time.sleep(12)

    try:
        if image_bytes:
            source_bytes = image_bytes
            log.info(f"[ДИАГНОСТИК restyle] эх эх нь bytes ({len(source_bytes)})")
        elif image_url:
            resp = requests.get(image_url, timeout=15)
            resp.raise_for_status()
            source_bytes = resp.content
            log.info(f"[ДИАГНОСТИК restyle] эх URL-с татлаа: {image_url[:80]} ({len(source_bytes)} bytes, content-type: {resp.headers.get('content-type')})")
        else:
            log.info("[ДИАГНОСТИК restyle] image_url, image_bytes хоёул хоосон — алгасав")
            return b""

        # Зургийн бодит форматыг тодорхойлох
        mime_type = "image/jpeg"
        try:
            from PIL import Image
            import io as _io
            detected = Image.open(_io.BytesIO(source_bytes)).format
            if detected:
                mime_type = f"image/{detected.lower()}"
        except Exception as fmt_err:
            log.warning(f"[ДИАГНОСТИК restyle] форматыг тодорхойлж чадсангүй, jpeg гэж үзнэ: {fmt_err}")

        img_b64 = base64.b64encode(source_bytes).decode()
        prompt = (
            "Convert this photo into a flat vector illustration / modern "
            "editorial sports-news art style, vibrant colors, clean "
            "geometric shapes. Preserve the exact same pose, composition, "
            "facial features, and moment shown in the original photo — "
            "only change the rendering style from photorealistic to "
            "illustrated. Do NOT change what is happening in the scene. "
            "No text, no watermark."
        )

        response = requests.post(
            f"{GEMINI_IMAGE_URL}?key={api_key}",
            json={
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inlineData": {"mimeType": mime_type, "data": img_b64}}
                    ]
                }]
            },
            timeout=25  # Овоорлоос сэргийлж timeout-ийг 40-өөс 25 болгож багасгав
        )

        log.info(f"[ДИАГНОСТИК restyle] HTTP статус: {response.status_code}")
        response.raise_for_status()
        
        data = response.json()
        parts = data["candidates"][0]["content"]["parts"]
        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and inline_data.get("data"):
                result_bytes = base64.b64decode(inline_data["data"])
                log.info(f"Gemini зургийг illustration болгож хөрвүүлэв ({len(result_bytes)} bytes)")
                return result_bytes

        log.warning(f"Gemini restyle хариунд зураг олдсонгүй. Бүтэн хариу: {str(data)[:500]}")
        return b""

    except requests.exceptions.HTTPError as e:
        log.warning(f"Gemini restyle HTTP алдаа: {e} | хариу: {response.text[:500]}")
        return b""
    except Exception as e:
        log.warning(f"Gemini restyle алдаа: {type(e).__name__}: {e}")
        return b""
