"""
Quote Card модуль — эх сурвалжид БОДИТООР байгаа ишлэлийг олж, Монгол хэлрүү орчуулаад,
жинхэнэ зураг дээр дизайнтай quote card болгож давхарлана (Pulse Sports загварын адил).
ЗАРЧИМ: Зөвхөн эх текстэд хашилтад орсон БОДИТ ишлэлийг ашиглана. 
ХЭЗЭЭ Ч зохиомол ишлэл үүсгэхгүй, хэн нэгэнд үг зохиож хэлүүлэхгүй.
"""

import re
import io
import logging
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

log = logging.getLogger(__name__)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

QUOTE_RE_DOUBLE = re.compile(r'["\u201c\u201d]([^"\u201c\u201d]{30,200})["\u201c\u201d]')
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

def _fetch_image(image_url=None, image_bytes: bytes = b"") -> "Image.Image | None":
    """
    Зургийг нээх функц. 
    image_url нь нэг хаяг (str) эсвэл олон эх сурвалжийн хаяг агуулсан жагсаалт (list) байж болно.
    """
    if image_bytes:
        try:
            return Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as e:
            log.warning(f"Quote card: image_bytes-с зураг нээхэд алдаа: {e}")

    if image_url:
        urls = [image_url] if isinstance(image_url, str) else image_url
        for url in urls:
            if not url:
                continue
            try:
                resp = requests.get(
                    url, 
                    timeout=12, 
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )
                resp.raise_for_status()
                return Image.open(io.BytesIO(resp.content)).convert("RGB")
            except Exception as e:
                log.warning(f"Quote card: {url[:50]}... хаягаас зураг татаж чадсангүй, дараагийн эх сурвалжийг шалгаж байна. Алдаа: {e}")
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


def _draw_text_with_shadow(draw, xy, text, font, fill, shadow_color=(0, 0, 0, 60), offset=2):
    """Текстэд зөөлөн сүүдэр нэмж гүн бий болгоно (мэргэжлийн дизайны стандарт)"""
    x, y = xy
    draw.text((x + offset, y + offset), text, font=font, fill=shadow_color)
    draw.text((x, y), text, font=font, fill=fill)


def generate_quote_card(quote_mn: str, source_name: str, category_mn: str = "",
                         image_url=None, image_bytes: bytes = b"") -> bytes:
    """
    Бодит зураг дээр quote card дизайн үүсгэнэ:
    - Дээд хэсэгт: бодит зураг + ангиллын жижиг tag (visual hierarchy)
    - Доод хэсэгт: цагаан хайрцаг доторх Монгол ишлэл (сүүдэртэй, тод) + эх сурвалж
    """
    base_img = _fetch_image(image_url, image_bytes)

    if not base_img:
        log.warning("Quote card: Ижил төрлийн мэдээллүүдийн аль ч эх сурвалжаас бодит зураг олдсонгүй. Картыг алгасав.")
        return b""

    try:
        CANVAS_W = 1200
        ratio = CANVAS_W / base_img.width
        img_h = int(base_img.height * ratio)
        # LANCZOS: хамгийн чанартай resampling — default resize жижиг
        # зургийг томруулахад бүдэг/pixel-тэй болгодог байсан
        base_img = base_img.resize((CANVAS_W, img_h), Image.LANCZOS)

        if img_h > 750:
            top = (img_h - 750) // 2
            base_img = base_img.crop((0, top, CANVAS_W, top + 750))
            img_h = 750

        box_margin = 60
        quote_font = ImageFont.truetype(FONT_BOLD, 42)
        source_font = ImageFont.truetype(FONT_REGULAR, 28)
        tag_font = ImageFont.truetype(FONT_BOLD, 24)

        _tmp_img = Image.new("RGB", (10, 10))
        _tmp_draw = ImageDraw.Draw(_tmp_img)
        quote_text = f'\u201c{quote_mn}\u201d'
        lines = _wrap_text(_tmp_draw, quote_text, quote_font, CANVAS_W - box_margin * 2 - 80)
        lines = lines[:6]

        LINE_HEIGHT = 54
        TOP_PADDING = 70  # Ангиллын tag-д зай гаргах
        BOTTOM_PADDING = 80
        text_block_h = len(lines) * LINE_HEIGHT
        QUOTE_BOX_H = max(240, TOP_PADDING + text_block_h + BOTTOM_PADDING)

        canvas = Image.new("RGB", (CANVAS_W, img_h + QUOTE_BOX_H), "white")
        canvas.paste(base_img, (0, 0))

        # Зурган доод ирмэгт зөөлөн бараан gradient (зурган болон цагаан
        # хайрцгийн хооронд "уусах" маягтай, илүү мэргэжлийн шилжилт)
        GRADIENT_H = 40
        gradient = Image.new("L", (1, GRADIENT_H), color=0)
        for y in range(GRADIENT_H):
            gradient.putpixel((0, y), int(255 * (y / GRADIENT_H)))
        gradient = gradient.resize((CANVAS_W, GRADIENT_H))
        shadow_overlay = Image.new("RGBA", (CANVAS_W, GRADIENT_H), (0, 0, 0, 0))
        shadow_overlay.putalpha(gradient.point(lambda p: int(p * 0.25)))
        canvas.paste(Image.new("RGB", (CANVAS_W, GRADIENT_H), (0, 0, 0)),
                     (0, img_h - GRADIENT_H), shadow_overlay)

        draw = ImageDraw.Draw(canvas)

        box_top = img_h
        draw.rectangle(
            [0, box_top, CANVAS_W, img_h + QUOTE_BOX_H],
            fill="white"
        )
        # Дээд ирмэгт нимгэн улаан зураас (хүрээ бүхэлдээ биш, илүү орчин үеийн)
        draw.rectangle([0, box_top, CANVAS_W, box_top + 8], fill=(200, 30, 30))

        # Ангиллын жижиг tag (жишээ: "СПОРТ") — visual hierarchy, эх сурвалжийн
        # өмнө контекст өгнө
        if category_mn:
            tag_text = category_mn.upper()
            tag_bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
            tag_w = tag_bbox[2] - tag_bbox[0] + 30
            draw.rectangle(
                [box_margin, box_top + 24, box_margin + tag_w, box_top + 58],
                fill=(200, 30, 30)
            )
            draw.text((box_margin + 15, box_top + 30), tag_text, font=tag_font, fill="white")

        # Ишлэлийн текстийг хайрцгийн төвд, сүүдэртэйгээр байрлуулах
        box_inner_h = QUOTE_BOX_H - TOP_PADDING - BOTTOM_PADDING
        text_y = box_top + TOP_PADDING + max(10, (box_inner_h - text_block_h) // 2)
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=quote_font)
            line_w = bbox[2] - bbox[0]
            text_x = box_margin + ((CANVAS_W - box_margin * 2) - line_w) // 2
            _draw_text_with_shadow(draw, (text_x, text_y), line, quote_font,
                                    fill=(15, 15, 15), shadow_color=(180, 180, 180), offset=1)
            text_y += LINE_HEIGHT

        # Эх сурвалжийн тэмдэглэл — доод ирмэгт, бага контраст (secondary info)
        draw.text(
            (box_margin, img_h + QUOTE_BOX_H - 55),
            f"Эх сурвалж: {source_name}",
            font=source_font,
            fill=(130, 130, 130)
        )

        output = io.BytesIO()
        canvas.save(output, format="JPEG", quality=85, optimize=True)
        log.info(f"Бодит зурагтай Quote card амжилттай үүсгэв ({len(output.getvalue())} bytes)")
        return output.getvalue()

    except Exception as e:
        log.warning(f"Quote card үүсгэхэд алдаа: {e}")
        return b""
