"""
Gemini харьцуулалтын модуль (зөвхөн туршилт, ДИАГНОСТИК зорилготой).

GEMINI_API_KEY тохируулсан үед л идэвхжинэ. Gemini-ийн гаралтыг
ПОСТЛОХОД ашиглахгүй — зөвхөн лог дээр Qwen-ийн гаралттай зэрэгцүүлж
харуулна, ингэснээр бодит RSS мэдээн дээр 2 загварын чанарыг шууд
харьцуулах боломжтой болно.
"""

import os
import logging
import requests

log = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


def is_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def compare(system_prompt: str, user_prompt: str) -> str:
    """
    Ижил prompt-оор Gemini-д бичүүлж, гаралтыг буцаана (постлохгүй,
    зөвхөн харьцуулалтад).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return ""

    try:
        response = requests.post(
            f"{GEMINI_API_URL}?key={api_key}",
            json={
                "contents": [
                    {"role": "user", "parts": [{"text": user_prompt}]}
                ],
                "systemInstruction": {
                    "parts": [{"text": system_prompt}]
                },
                "generationConfig": {
                    "temperature": 0.5,
                    "maxOutputTokens": 700,
                }
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text
    except Exception as e:
        log.warning(f"Gemini харьцуулалт алдаа: {e}")
        return ""
