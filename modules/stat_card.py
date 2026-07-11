"""
Stat card модуль — тоглолтын үр дүнгийн мэдээнд ESPN маягийн статтай
зурган карт үүсгэнэ.

ЗАРЧИМ:
- Зөвхөн ДУУССАН тоглолтын мэдээ, эх материалд тоглогчийн тодорхой
  стат байгаа үед л ажиллана. Стат олдохгүй бол None буцаана →
  main.py ердийн quote card руугаа явна.
- Суурь зураг нь ямагт БОДИТ (эх сурвалжийн) фото — AI зураг үүсгэхгүй,
  зөвхөн текст давхарга нэмнэ.
- Статыг Qwen (Groq)-оор JSON хэлбэрт задлана — writer-тэй ижил API,
  нэмэлт түлхүүр шаардахгүй.
"""

import os
import json
import io
import logging
import requests

from PIL import Image, ImageDraw, ImageFont
from modules.quote_card import _fetch_image, _draw_text_with_shadow, FONT_BOLD, FONT_REGULAR

log = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.6-27b"

# Хоёр тоглогчийн өнгө: улаан / гүн хөх (ESPN comparison загвар)
P1_COLOR = (200, 16, 46)
P2_COLOR = (30, 60, 110)

_EXTRACT_PROMPT = """You are a sports data extractor. From the news text below, extract
player stat lines ONLY IF this is a FINISHED game/match result AND the
text contains explicit numeric stats for specific named players.

Respond with ONLY raw JSON, no markdown, no explanation:
{"players": [{"name": "Caleb Wilson", "team": "Bulls",
  "stats": [{"label": "PTS", "value": "35"}, {"label": "REB", "value": "5"}]}],
 "score": "97-96"}

Rules:
- 1 or 2 players maximum (the top performers). 2 players only if both
  have stats in the text (ideal for head-to-head).
- 2-3 stats per player, only numbers explicitly present in the text.
- Short uppercase labels: PTS, REB, AST, GOALS, ASSISTS, SAVES, KO, etc.
- "score" = final score if present, else "".
- If this is NOT a finished game result, or NO explicit per-player
  numeric stats exist in the text, respond with exactly: null

NEWS TEXT:
"""


def extract_stats(title: str, summary: str = "", body: str = "") -> dict | None:
    """Мэдээний текстээс тоглогчийн статыг JSON болгож задлана."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    text = f"{title}\n{summary}\n{body}"[:2500]

    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "user", "content": _EXTRACT_PROMPT + text}
                ],
                "temperature": 0.1,
                "max_tokens": 300,
                "reasoning_effort": "none",
            },
            timeout=25,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.warning(f"[STAT CARD] задлагч API алдаа: {e}")
        return None

    raw = raw.replace("```json", "").replace("```", "").strip()
    if raw.lower() in ("null", "none", ""):
        return None

    try:
        data = json.loads(raw)
    except Exception:
        log.info(f"[STAT CARD] JSON биш хариу — алгасав: {raw[:80]!r}")
        return None

    players = (data or {}).get("players") or []
    # Хамгаалалт: нэр + дор хаяж 1 тоон стат байх ёстой
    clean = []
    for p in players[:2]:
        name = (p.get("name") or "").strip()
        stats = [
            s for s in (p.get("stats") or [])
            if s.get("label") and str(s.get("value", "")).strip()
        ][:3]
        if name and stats:
            clean.append({"name": name, "team": (p.get("team") or "").strip(), "stats": stats})

    if not clean:
        return None

    return {"players": clean, "score": (data.get("score") or "").strip()}


def generate_stat_card(stats: dict, category_mn: str = "",
                       image_url=None, image_bytes: bytes = b"") -> bytes:
    """
    Бодит зураг + доод хэсэгт стат самбар бүхий карт үүсгэнэ.
    Бүтэлгүйтвэл b"" буцаана (quote card руу унана).
    """
    base_img = _fetch_image(image_url, image_bytes)
    if not base_img:
        return b""

    try:
        players = stats["players"]
        score = stats.get("score", "")

        CANVAS_W = 1200
        ratio = CANVAS_W / base_img.width
        img_h = int(base_img.height * ratio)
        base_img = base_img.resize((CANVAS_W, img_h), Image.LANCZOS)
        if img_h > 720:
            top = (img_h - 720) // 2
            base_img = base_img.crop((0, top, CANVAS_W, top + 720))
            img_h = 720

        # Доод самбарын өндөр: оноо + нэр + том тоо + label
        panel_h = 300 if score else 260
        canvas = Image.new("RGB", (CANVAS_W, img_h + panel_h), (255, 255, 255))
        canvas.paste(base_img, (0, 0))
        draw = ImageDraw.Draw(canvas)

        # Улаан зааг шугам (quote card-тай ижил брэнд элемент)
        draw.rectangle([0, img_h, CANVAS_W, img_h + 6], fill=P1_COLOR)

        tag_font = ImageFont.truetype(FONT_BOLD, 24)
        score_font = ImageFont.truetype(FONT_BOLD, 46)
        name_font = ImageFont.truetype(FONT_BOLD, 34)
        team_font = ImageFont.truetype(FONT_REGULAR, 24)
        num_font = ImageFont.truetype(FONT_BOLD, 66)
        label_font = ImageFont.truetype(FONT_REGULAR, 22)

        y = img_h + 24

        # Ангиллын tag (зүүн дээд)
        if category_mn:
            tag_text = category_mn.upper()
            tw = draw.textlength(tag_text, font=tag_font)
            draw.rectangle([40, y, 40 + tw + 28, y + 40], fill=P1_COLOR)
            draw.text((54, y + 7), tag_text, font=tag_font, fill=(255, 255, 255))

        # Эцсийн оноо (голд, tag-тай нэг мөрөнд)
        if score:
            sw = draw.textlength(score, font=score_font)
            draw.text(((CANVAS_W - sw) / 2, y - 4), score,
                      font=score_font, fill=(20, 20, 20))
        y += 64

        # Тоглогчийн багана(ууд)
        n = len(players)
        col_w = CANVAS_W // n
        colors = [P1_COLOR, P2_COLOR]

        for i, p in enumerate(players):
            cx = col_w * i + col_w // 2
            color = colors[i % 2]

            # Нэр (багана дотроо голлуулж)
            name = p["name"]
            nf = name_font
            if draw.textlength(name, font=nf) > col_w - 60:
                nf = ImageFont.truetype(FONT_BOLD, 28)
            nw = draw.textlength(name, font=nf)
            draw.text((cx - nw / 2, y), name, font=nf, fill=(20, 20, 20))

            ty = y + 44
            team = p.get("team", "")
            if team:
                tw = draw.textlength(team, font=team_font)
                draw.text((cx - tw / 2, ty), team, font=team_font, fill=(110, 110, 110))
                ty += 36

            # Статууд: том тоо + доор нь label, зэрэгцээ
            sts = p["stats"]
            slot_w = min(180, (col_w - 40) // len(sts))
            total_w = slot_w * len(sts)
            sx = cx - total_w // 2
            for s in sts:
                val = str(s["value"])
                lab = str(s["label"]).upper()
                vw = draw.textlength(val, font=num_font)
                lw = draw.textlength(lab, font=label_font)
                scx = sx + slot_w // 2
                draw.text((scx - vw / 2, ty), val, font=num_font, fill=color)
                draw.text((scx - lw / 2, ty + 74), lab, font=label_font, fill=(110, 110, 110))
                sx += slot_w

        # Хоёр тоглогчийн хооронд нимгэн зааг
        if n == 2:
            draw.rectangle([CANVAS_W // 2 - 1, img_h + 80, CANVAS_W // 2 + 1,
                            img_h + panel_h - 30], fill=(225, 225, 225))

        buf = io.BytesIO()
        canvas.save(buf, format="JPEG", quality=90)
        log.info(f"📊 [STAT CARD] Үүслээ: {', '.join(p['name'] for p in players)}"
                 f"{' | ' + score if score else ''}")
        return buf.getvalue()

    except Exception as e:
        log.warning(f"[STAT CARD] зурах алдаа: {e}")
        return b""
