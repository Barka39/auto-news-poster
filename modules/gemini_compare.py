"""
Gemini API-аар нийтлэл бичих модуль (ҮНДСЭН бичигч).
GEMINI_API_KEY тохируулсан үед л идэвхжинэ.
Бодит харьцуулалтад Qwen-с илүү нарийвчлалтай (баримт алдаагүй) орчуулга гаргаж байсан тул одоо ЭХНИЙ ээлжинд ашиглагдана.
Амжилтгүй бол writer.py Qwen (Groq) руу, дараа нь Google Translate руу шилждэг.
"""

import os
import time
import logging
import requests

log = logging.getLogger(__name__)

# Өдөрт 500 эрхтэй үнэгүй тарифын шинэ модель руу шилжүүлэв
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"

def is_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))

def generate(system_prompt: str, user_prompt: str) -> str:
    """
    Ижил prompt-оор Gemini-д бичүүлж, гаралтыг буцаана (постлохгүй, зөвхөн харьцуулалтад).
    503 (сервер завгүй) алдаанд 1 удаа дахин оролдоно.
    Gemini-ийн "бодох горим"-ыг унтраасан (thinkingBudget=0) — Qwen-д тулгарсан адил "token дуусаж хариулт хоосорсон" алдаанаас сэргийлэхийн тулд.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return ""

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": user_prompt}]}
        ],
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 2000,
            "thinkingConfig": {"thinkingBudget": 0},
        }
    }

    # 2026-09-23: flash-lite удаан хугацаанд 503 өгч, гурван хуудсын бүх контент зогссон тул
    # загварын жагсаалтаар дамжина: 503/429 → дахин оролдоод дараагийн загвар; 404 → шууд дараагийн.
    models = [m.strip() for m in os.environ.get(
        "GEMINI_MODELS", "gemini-3.1-flash-lite,gemini-3.1-flash,gemini-2.5-flash,gemini-2.5-flash-lite").split(",") if m.strip()]
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(2):
            try:
                response = requests.post(f"{url}?key={api_key}", json=payload, timeout=45)
                if response.status_code == 404:
                    break
                if response.status_code in (429, 500, 503):
                    log.warning(f"Gemini {model} {response.status_code} (оролдлого {attempt + 1})")
                    time.sleep(3)
                    continue
                response.raise_for_status()
                data = response.json()
                candidate = data["candidates"][0]
                parts = candidate.get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                if not text:
                    log.warning(f"Gemini {model} хоосон гаралт (finishReason: {candidate.get('finishReason')})")
                    break
                if model != models[0]:
                    log.info(f"Gemini нөөц загвар ашиглав: {model}")
                return text
            except Exception as e:
                log.warning(f"Gemini {model} алдаа: {e}")
                break
    return ""
