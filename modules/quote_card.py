"""
Quote Card модуль — эх сурвалжид БОДИТООР байгаа ишлэлийг олж,
Монгол хэлрүү орчуулаад, жинхэнэ зураг дээр дизайнтай quote card
болгож давхарлана (Pulse Sports загварын адил).

ЗАРЧИМ: Зөвхөн эх текстэд хашилтад орсон БОДИТ ишлэлийг ашиглана.
ХЭЗЭЭ Ч зохиомол ишлэл үүсгэхгүй, хэн нэгэнд үг зохиож хэлүүлэхгүй.
"""

import re
import io
import logging
import requests
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Давхар хашилт (шулуун эсвэл муруй) — хамгийн найдвартай
QUOTE_RE_DOUBLE = re.compile(r'["\u201c\u201d]([^"\u201c\u201d]{30,200})["\u201c\u201d]')
# Ганц хашилт (‘ ’ эсвэл ') — зөвхөн мөрний эхэнд/зайн дараа эхэлсэн бол
# (contraction-той андуурахгүйн тулд, жишээ "England's" гэдэгтэй)
QUOTE_RE_SINGLE = re.compile(r"(?:^|\s)['\u2018]([^'\u2019]{30,200})['\u2019](?:\s|$|[.,!?:])")


def extract_quote(text: str) -> str:
    """Гарчиг/агуулгаас БОДИТ ишлэлийг олох (байхгүй бол хоосон буцаана)"""
    if not text:
        return ""
    match = QUOTE_RE_DOUBLE.search(text)
    if match:
        return match.group(1).strip()
    match = QUOTE_RE_SINGLE.search(text)
    if match:
        return match.group(1).strip()
    return ""


def _fetch_image(image_url: str = "", image_bytes: bytes = b"") -> "Image.Image | None":
    """Зургийг URL эсвэл bytes-с PIL Image болгож нээх"""
    try:
        if image_bytes:
            return Image.open(io.BytesIO(image_bytes)).convert("RGB")
        if image_url:
            resp = requests.get(image_url, timeout=15)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        log.warning(f"Quote card: зураг татахад алдаа: {e}")
    return None


def _wrap_text(draw, text: str, font, max_width: int) -> list:
    """Текстийг өгөгдсөн өргөнд багтаах мөрүүдэд хуваах"""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_quote_card(quote_mn: str, source_name: str,
                         image_url: str = "", image_bytes: bytes = b"") -> bytes:
    """
    Бодит зураг дээр quote card дизайн үүсгэнэ (Pulse Sports загварын адил):
    - Дээд хэсэгт: эх зураг
    - Доод хэсэгт: цагаан хайрцаг доторх Монгол ишлэл + эх сурвалж

    Амжилтгүй бол хоосон bytes буцаана (дуудагч тал өмнөх зургаа хэвээр үлдээнэ).
    """
    base_img = _fetch_image(image_url, image_bytes)
    if not base_img:
        return b""

    try:
        CANVAS_W = 1200
        # Зургийг canvas өргөнд тааруулж, харьцаагаар өндрийг тооцох
        ratio = CANVAS_W / base_img.width
        img_h = int(base_img.height * ratio)
        base_img = base_img.resize((CANVAS_W, img_h))

        # Зургийн өндрийг дээд тал нь 750px-т хязгаарлах (хэт өндөр болохоос сэргийлэх)
        if img_h > 750:
            top = (img_h - 750) // 2
            base_img = base_img.crop((0, top, CANVAS_W, top + 750))
            img_h = 750

        box_margin = 60
        quote_font = ImageFont.truetype(FONT_BOLD, 42)
        source_font = ImageFont.truetype(FONT_REGULAR, 30)

        # Текстийг эхлээд урьдчилан тооцоод (жинхэнэ canvas үүсгэхийн
        # өмнө), ингэснээр хайрцгийн өндрийг МӨРИЙН ТООНООС хамааруулж
        # тохируулна — богино ишлэлд жижиг, урт ишлэлд том хайрцаг.
        _tmp_img = Image.new("RGB", (10, 10))
        _tmp_draw = ImageDraw.Draw(_tmp_img)
        quote_text = f'\u201c{quote_mn}\u201d'
        lines = _wrap_text(_tmp_draw, quote_text, quote_font, CANVAS_W - box_margin * 2 - 80)
        lines = lines[:6]  # дээд тал нь 6 мөр

        LINE_HEIGHT = 54
        TOP_PADDING = 60
        BOTTOM_PADDING = 80  # эх сурвалжийн мөрөнд зориулсан зай
        text_block_h = len(lines) * LINE_HEIGHT
        QUOTE_BOX_H = max(220, TOP_PADDING + text_block_h + BOTTOM_PADDING)

        canvas = Image.new("RGB", (CANVAS_W, img_h + QUOTE_BOX_H), "white")
        canvas.paste(base_img, (0, 0))

        draw = ImageDraw.Draw(canvas)

        # Улаан хүрээтэй цагаан quote хайрцаг (Pulse Sports загвар)
        box_top = img_h + 30
        draw.rectangle(
            [box_margin, box_top, CANVAS_W - box_margin, img_h + QUOTE_BOX_H - 30],
            fill="white",
            outline=(200, 30, 30),
            width=6
        )

        # Ишлэлийн текстийг ХАЙРЦГИЙН ТӨВД (босоогоор) байрлуулах
        box_inner_h = QUOTE_BOX_H - 60 - BOTTOM_PADDING  # хүрээний дотоод өндөр (эх сурвалжийн зайг хасаад)
        text_y = box_top + max(30, (box_inner_h - text_block_h) // 2)
        for line in lines:
            # Мөр бүрийг хэвтээгээр төвлүүлэх
            bbox = draw.textbbox((0, 0), line, font=quote_font)
            line_w = bbox[2] - bbox[0]
            text_x = box_margin + ((CANVAS_W - box_margin * 2) - line_w) // 2
            draw.text((text_x, text_y), line, font=quote_font, fill=(20, 20, 20))
            text_y += LINE_HEIGHT

        # Эх сурвалжийн тэмдэглэл
        draw.text(
            (box_margin + 40, img_h + QUOTE_BOX_H - 70),
            f"Эх сурвалж: {source_name}",
            font=source_font,
            fill=(120, 120, 120)
        )

        output = io.BytesIO()
        canvas.save(output, format="PNG")
        log.info(f"Quote card үүсгэв ({len(output.getvalue())} bytes)")
        return output.getvalue()

    except Exception as e:
        log.warning(f"Quote card үүсгэхэд алдаа: {e}")
        return b""
