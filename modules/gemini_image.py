"""
Gemini болон Хязгааргүй Free AI (Pollinations Flux) хавсарсан зураг үүсгэх модуль.
ҮНДСЭН ЗАРЧИМ:
1. generate_image_bytes() — Үндсэн моделиор 100% үнэгүй, квотгүй Pollinations AI (Flux)-ийг ашиглана.
   Хэрэв тухайн үед сервер нь завгүй байвал НӨӨЦӨӨР хуучин Gemini-2.5-flash-image руу автоматаар шилжинэ.
2. restyle_photo() — Google-ийн дүр төрх хадгалах алгоритмыг ашиглана. Хэрэв 429 квот дуусвал 
   систем унахгүй, quote_card модуль өөр сайтуудын (ESPN, BBC) бодит зургийг ашиглахаар алгасна.
"""

import os
import base64
import logging
import requests
import time
import urllib.parse

log = logging.getLogger(__name__)

# Google Gemini Зургийн Endpoint
GEMINI_IMAGE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"

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
    return True  # Pollinations AI-д API key шаардлагагүй тул үргэлж идэвхтэй байна

def generate_image_bytes(category: str) -> bytes:
    """
    Ерөнхий сэдэвчилсэн зургийг үүсгэхдээ КВОТГҮЙ, ХЯЗГААРГҮЙ Pollinations AI-ийг үндсэн
    модель болгож ашиглана. Алдаа гарвал НӨӨЦӨӨР Gemini-г дуудна.
    """
    scene = CATEGORY_PROMPTS.get(category, CATEGORY_PROMPTS["world_news"])
    prompt = f"{scene}, {STYLE_SUFFIX}"
    
    # 1. ҮНДСЭН МОДЕЛЬ: Pollinations AI (Flux) - Хязгааргүй, Үнэгүй
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        # Өндөр чанартай спорт постер гаргахад тохиромжтой Flux моделийг сонгов
        pollinations_url = f"https://image.pollinations.ai/p/{encoded_prompt}?width=1200&height=750&model=flux&seed=42"
        
        log.info(f"[ҮНДСЭН МОДЕЛЬ] Pollinations AI-аар зураг үүсгэж байна ({category})...")
        resp = requests.get(pollinations_url, timeout=20)
        resp.raise_for_status()
        
        if resp.content and len(resp.content) > 5000:  # Зөв зураг ирсэн эсэхийг шалгах
            log.info(f"✅ Pollinations AI зургийг амжилттай үүсгэв ({len(resp.content)} bytes)")
            return resp.content
    except Exception as e:
        log.warning(f"Pollinations AI-д алдаа гарлаа: {e}. НӨӨЦ МОДЕЛЬ (Gemini) руу шилжиж байна...")

    # 2. НӨӨЦ МОДЕЛЬ (FALLBACK): Gemini 2.5 Flash Image
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return b""

    try:
        log.info("[НӨӨЦ МОДЕЛЬ] Gemini-2.5-flash-image дуудаж байна...")
        response = requests.post(
            f"{GEMINI_IMAGE_URL}?key={api_key}",
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}]
            },
            timeout=25
        )
        response.raise_for_status()
        data = response.json()
        
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                inline_data = part.get("inlineData") or part.get("inline_data")
                if inline_data and inline_data.get("data"):
                    image_bytes = base64.b64decode(inline_data["data"])
                    log.info(f"✅ Gemini нөөц модоор зураг үүсгэв ({len(image_bytes)} bytes)")
                    return image_bytes
    except Exception as gemini_err:
        log.warning(f"Нөөц модель Gemini бас уналаа: {gemini_err}")
    
    return b""

def restyle_photo(image_url: str = "", image_bytes: bytes = b"") -> bytes:
    """
    Жинхэнэ фотог хөрвүүлэхэд Google-ийн алгоритм хэрэгтэй тул Gemini-г ашиглана.
    Хэрэв 429 квот дуусвал систем унахгүй, quote_card модуль өөр сурвалжуудын зургийг ашиглана.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return b""

    log.info("[ДИАГНОСТИК restyle] Gemini Rate Limit-ээс хамгаалж 12 секунд хүлээж байна...")
    time.sleep(12)

    try:
        if image_bytes:
            source_bytes = image_bytes
        elif image_url:
            resp = requests.get(image_url, timeout=15)
            resp.raise_for_status()
            source_bytes = resp.content
        else:
            return b""

        mime_type = "image/jpeg"
        try:
            from PIL import Image
            import io as _io
            detected = Image.open(_io.BytesIO(source_bytes)).format
            if detected:
                mime_type = f"image/{detected.lower()}"
        except Exception:
            pass

        img_b64 = base64.b64encode(source_bytes).decode()
        prompt = (
            "Convert this photo into a flat vector illustration / modern "
            "editorial sports-news art style, vibrant colors, clean "
            "geometric shapes. Preserve the exact same pose, composition, "
            "facial features, and moment shown in the original photo. No text."
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
            timeout=25
        )

        if response.status_code == 429:
            log.warning("Gemini restyle квот дууссан (429). Эх зургийг хэвээр ашиглахаар алгаслаа.")
            return b""

        response.raise_for_status()
        data = response.json()
        
        candidates = data.get("candidates", [])
        if not candidates:
            return b""
            
        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and inline_data.get("data"):
                return base64.b64decode(inline_data["data"])

        return b""
    except Exception as e:
        log.warning(f"Gemini restyle алдаа гарлаа: {e}")
        return b""
