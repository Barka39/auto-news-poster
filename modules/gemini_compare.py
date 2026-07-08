"""
Gemini API-аар нийтлэл бичих модуль (ҮНДСЭН бичигч).

GEMINI_API_KEY тохируулсан үед л идэвхжинэ. Бодит харьцуулалтад Qwen-с
илүү нарийвчлалтай (баримт алдаагүй) орчуулга гаргаж байсан тул одоо
ЭХНИЙ ээлжинд ашиглагдана. Амжилтгүй бол writer.py Qwen (Groq) руу,
дараа нь Google Translate руу шилждэг.
"""

import os
import time
import logging
import requests

log = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


def is_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def generate(system_prompt: str, user_prompt: str) -> str:
    """
    Ижил prompt-оор Gemini-д бичүүлж, гаралтыг буцаана (постлохгүй,
    зөвхөн харьцуулалтад). 503 (сервер завгүй) алдаанд 1 удаа дахин
    оролдоно. Gemini-ийн "бодох горим"-ыг унтраасан (thinkingBudget=0)
    — Qwen-д тулгарсан адил "token дуусаж хариулт хоосорсон" алдаанаас
    сэргийлэхийн тулд.
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
            "maxOutputTokens": 1000,
            "thinkingConfig": {"thinkingBudget": 0},
        }
    }

    for attempt in range(2):
        try:
            response = requests.post(
                f"{GEMINI_API_URL}?key={api_key}",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            candidate = data["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()

            if not text:
                log.warning(f"Gemini хоосон гаралт буцаав (finishReason: {candidate.get('finishReason')})")
                return ""

            return text

        except requests.exceptions.HTTPError as e:
            if response.status_code == 503 and attempt == 0:
                log.warning("Gemini 503 (завгүй) — 3 секундын дараа дахин оролдоно")
                time.sleep(3)
                continue
            log.warning(f"Gemini харьцуулалт алдаа: {e}")
            return ""
        except Exception as e:
            log.warning(f"Gemini харьцуулалт алдаа: {e}")
            return ""

    return ""
