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
from PIL import Image, ImageDraw, ImageFont

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
        # Хэрэв ганц стринг байвал жагсаалт болгож хөрвүүлнэ
        urls = [image_url] if isinstance(image_url, str) else image_url
        
        # Ижил төрлийн мэдээлэл тавьсан сайтуудын (ESPN, BBC, TNT) зургуудыг ээлжлэн шалгах
        for url in urls:
            if not url:
                continue
            try:
                # Сайтууд бот гэж блок хийхээс хамгаалж хөтчийн User-Agent нэмэв
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

def generate_quote_card(quote_mn: str, source_name: str, image_url=None, image_bytes: bytes = b"") -> bytes:
    """
    Бодит зураг дээр quote card дизайн үүсгэнэ (Pulse Sports загварын адил):
    - Дээд хэсэгт: эх сурвалжуудын аль нэгнээс олдсон БОДИТ зураг
    - Доод хэсэгт: цагаан хайрцаг доторх Монгол ишлэл + эх сурвалж
    """
    # Өгөгдсөн үндсэн болон өөр эх сурвалжуудын зургуудыг шалгаж нээнэ
    base_img = _fetch_image(image_url, image_bytes)
    
    # Хэрэв аль ч ижил мэдээллийн сайтаас зураг татагдаж чадаагүй бол цулгуй дэвсгэр тавихгүй, шууд алгасна
    if not base_img:
        log.warning("Quote card: Ижил төрлийн мэдээллүүдийн аль ч эх сурвалжаас бодит зураг олдсонгүй. Картыг алгасав.")
        return b""

    try:
        CANVAS_W = 1200
        ratio = CANVAS_W / base_img.width
        img_h = int(base_img.height * ratio)
        base_img = base_img.resize((CANVAS_W, img_h))

        if img_h > 750:
            top = (img_h - 750) // 2
            base_img = base_img.crop((0, top, CANVAS_W, top + 750))
            img_h = 750

        box_margin = 60
        quote_font = ImageFont.truetype(FONT_BOLD, 42)
        source_font = ImageFont.truetype(FONT_REGULAR, 30)

        _tmp_img = Image.new("RGB", (10, 10))
        _tmp_draw = ImageDraw.Draw(_tmp_img)
        quote_text = f'\u201c{quote_mn}\u201d'
        lines = _wrap_text(_tmp_draw, quote_text, quote_font, CANVAS_W - box_margin * 2 - 80)
        lines = lines[:6]
        
        LINE_HEIGHT = 54
        TOP_PADDING = 60
        BOTTOM_PADDING = 80  
        text_block_h = len(lines) * LINE_HEIGHT
        QUOTE_BOX_H = max(220, TOP_PADDING + text_block_h + BOTTOM_PADDING)

        canvas = Image.new("RGB", (CANVAS_W, img_h + QUOTE_BOX_H), "white")
        canvas.paste(base_img, (0, 0))
        draw = ImageDraw.Draw(canvas)

        box_top = img_h + 30
        draw.rectangle([box_margin, box_top, CANVAS_W - box_margin, img_h + QUOTE_BOX_H - 30], fill="white", outline=(200, 30, 30), width=6 )

        box_inner_h = QUOTE_BOX_H - 60 - BOTTOM_PADDING  
        text_y = box_top + max(30, (box_inner_h - text_block_h) // 2)
        
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=quote_font)
            line_w = bbox[2] - bbox[0]
            text_x = box_margin + ((CANVAS_W - box_margin * 2) - line_w) // 2
            draw.text((text_x, text_y), line, font=quote_font, fill=(20, 20, 20))
            text_y += LINE_HEIGHT

        draw.text((box_margin + 40, img_h + QUOTE_BOX_H - 70), f"Эх сурвалж: {source_name}", font=source_font, fill=(120, 120, 120) )

        output = io.BytesIO()
        # Фэйсбүүкт унахгүй орохын тулд JPEG форматаар оновчтой шахаж хадгална
        canvas.save(output, format="JPEG", quality=85, optimize=True)
        log.info(f"Бодит зурагтай Quote card амжилттай үүсгэв ({len(output.getvalue())} bytes)")
        return output.getvalue()
        
    except Exception as e:
        log.warning(f"Quote card үүсгэхэд алдаа: {e}")
        return b""
