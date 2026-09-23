"""
Контент хуудсууд: мэдээ биш, ҮҮСГЭСЭН контентоор ажилладаг хоёр Facebook хуудас.

  suns  — «Сүнсний код»: өдрийн зурхай, тоо судлал, сүнслэг сургаал, зүүд, тарот,
          уламжлалт ёс заншил, сар/гарагийн бэлгэдэл. Зорилго: сонирхол, сэтгэлийн хөдөлгөөн.
  udesh — «Үдшийн шивнээ»: насанд хүрэгчдэд зориулсан үргэлжилсэн өгүүллэг (хайр, урвалт,
          нууц, хүсэл, сэтгэлийн зовлон). Мэдрэмжтэй, дур татам, ГЭХДЭЭ Facebook-ийн
          community standards-д нийцсэн: ил задгай бэлгийн дүрслэлгүй, насанд хүрээгүй
          дүргүй, хүчирхийллийг магтахгүй. Эс бөгөөс хуудас хаагдана.

Постын дараалал pages_state.json-д (хуудас бүрийн өнөөдөр гарсан слот, сүүлийн 40 гарчиг,
өгүүллэгийн цуврал: нэр, хэсэг, товч агуулга). Слот бүр өдөрт нэг удаа; 10 минут тутмын
run слотын цаг болсон эсэхийг шалгаад постолно (GitHub-ийн cron-оос хамаарахгүй).
"""

import json
import logging
import math
import os
import random
import re
from datetime import datetime, timedelta, timezone

from modules import gemini_compare, cards, lint_mn
from modules.writer import is_valid_mongolian

log = logging.getLogger(__name__)

UB = timezone(timedelta(hours=8))
STATE_FILE = "pages_state.json"

WEEKDAY_MN = ["Даваа", "Мягмар", "Лхагва", "Пүрэв", "Баасан", "Бямба", "Ням"]
WEEKDAY_PLANET = {"Даваа": "Сар", "Мягмар": "Ангараг", "Лхагва": "Буд", "Пүрэв": "Бархасбадь",
                  "Баасан": "Сугар", "Бямба": "Санчир", "Ням": "Нар"}
ZODIAC = ["Хонь ♈", "Үхэр ♉", "Ихэр ♊", "Мэлхий ♋", "Арслан ♌", "Охин ♍",
          "Жинлүүр ♎", "Хилэнц ♏", "Нум ♐", "Матар ♑", "Хумх ♒", "Загас ♓"]

PAGES = {
    "suns": {
        "name": "Сүнсний код",
        "suffix": "SUNS",
        "brand": "СҮНСНИЙ КОД ✨",
        "hashtags": "#СүнснийКод #Зурхай #Сүнслэг",
        "slots": {"08:00": "zurhai", "13:00": "spirit", "21:00": "numerology"},
    },
    "udesh": {
        "name": "Үдшийн шивнээ",
        "suffix": "UDESH",
        "brand": "ҮДШИЙН ШИВНЭЭ 🌙",
        "hashtags": "#ҮдшийнШивнээ #Өгүүллэг",
        "slots": {"21:30": "story", "12:30": "confession"},
    },
}

# «Сүнсний код» — 13:00-ийн сэдвийн эргэлт (давтагдахгүй, өдөр бүр өөр)
SPIRIT_THEMES = [
    "Буддын сургаалаас өдрийн нэг ойлголт (жишээ: сэтгэлийн амгалан, үйлийн үр, анхаарал) — амьдралд хэрхэн хэрэглэх",
    "Монголын уламжлалт ёс заншил, бэлгэдэл (гал голомт, хадаг, тэнгэр шүтлэг, өвөг дээдэс) — утга, өнөөдрийн хэрэглээ",
    "Зүүдний тайлал: нэг түгээмэл зүүдний утга (ус, унах, нисэх, шүд, могой, гэрээсээ гарах гэх мэт)",
    "Тарот: өдрийн нэг хөзөр (Major Arcana) — утга, анхааруулга, зөвлөгөө",
    "Гарагийн энерги: өнөөдрийн гарагийн бэлгэдэл, юу хийхэд тохиромжтой, юунаас зайлсхийх",
    "Сарны үе шат ба сэтгэл: өнөөдрийн сарны байдал сэтгэл, эрч хүчинд хэрхэн нөлөөлдөг",
    "Чакра / энергийн төв: нэг чакрын утга, тэнцвэргүй үеийн шинж, 3 минутын дасгал",
    "Тэнгэр элчийн тоо (angel numbers): 111, 222, 333 ... нэг тооны утга",
    "Бясалгал, амьсгалын нэг энгийн арга — өдрийн 5 минут",
    "Фэн шуй / орон зайн энерги: гэрийн нэг булан, өнгө, чиглэлийн зөвлөгөө",
    "Дэлхийн шашин, сүнслэг уламжлалын нэг сонирхолтой баримт (хиндү, даоизм, суфи, нутгийн шүтлэг)",
    "Ид шидийн чулуу, эрдэнийн чулуу: нэг чулууны бэлгэдэл, хэнд тохирох",
    "Карма, үйлийн үрийн тухай нэг богино сургаалт өгүүллэг (уламжлалт эсвэл зохиомол, тэгж тэмдэглэ)",
    "Сэтгэлийн шинж: өнгө / тоо / амьтны бэлгэдэл сонгуулж хариултаар нь зан чанар тайлах (engagement)",
    "Шинэ сар, тэргэл сар, улирлын хагас — байгалийн мөчлөг ба зорилго тавих ёс",
]

CONFESSION_THEMES = [
    "нууцаа хэзээ ч хэлж чадаагүй хайр", "гэрлэлтийн дараах ганцаардал", "хуучин хайртайгаа санамсаргүй тааралдах",
    "эцэг эхийн эсрэг сонголт", "найзын нөхөрт татагдах", "хол зайн харилцааны шаналал", "уучлахыг хүсдэг ч чадахгүй",
    "хоёр хүний хооронд сонгох", "ажлын өрөөнд эхэлсэн харц", "хуримын өмнөх эргэлзээ", "салсны дараах анхны шөнө",
    "нэг мессежээс эхэлсэн бүх зүйл",
]

# Зурганд ашиглах уур амьсгал (AI зураг; хүний ил бие БИШ, зөвхөн санаа)
IMAGE_MOODS = [
    # Ихэнх нь нүүргүй (объект, гар, дүрс) — эротик санаа, ямар ч эрсдэлгүй
    "close-up of a red lipstick mark on a wine glass beside a black silk scarf, candlelight, moody",
    "a man's hand gently holding a woman's hand wearing a ring, dim warm restaurant light, shallow depth of field",
    "a black evening dress draped over a velvet armchair, city lights through the window at night",
    "a hotel key card and a pair of elegant leather gloves on dark marble, noir lighting",
    "rain drops on a dark window with blurred warm city lights, a single red rose on the sill",
    "two champagne glasses touching on a balcony at night, city skyline bokeh",
    "a handwritten love letter and a pearl necklace on a dark wooden desk, warm lamp light",
    "high heels and a men's tie on a hotel carpet, warm dim hallway light, cinematic",
    # Хүнтэй бол: 40 орчим насны, бүрэн хувцастай, зогсож буй
    "a mature couple in their forties in elegant formal evening wear dancing close in a dim ballroom, seen from behind",
    "a mature woman in her forties in a long red evening gown looking back over her shoulder in a warm lit hallway",
]

STORY_GENRES = [
    "хайрын гурвалжин ба урвалт", "олон жилийн дараа буцаж ирсэн хайр", "нууцтай шинэ хөрш",
    "гэрлэлтээ аварч буй хосын сүүлчийн оролдлого", "ажил дээрх хориотой татах хүч",
    "хуучин захидлаас илэрсэн нууц", "нэг шөнийн санамсаргүй уулзалт, түүний үр дагавар",
    "эргэн ирсэн хуучин найз, хоёр хүний нууц", "зуны амралтын гэнэтийн хайр",
]


# ============================================================
# ТӨЛӨВ
# ============================================================
def load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def page_state(state: dict, page: str) -> dict:
    return state.setdefault(page, {"posted": {}, "recent": [], "story": {}})


def remember(ps: dict, title: str):
    ps["recent"] = ([title] + ps.get("recent", []))[:40]


def moon_phase(now: datetime) -> tuple:
    """(нэр, emoji, гэрэлтэлт %) — энгийн синодик тооцоо (29.53 хоног)."""
    ref = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)  # мэдэгдэж буй шинэ сар
    days = (now.astimezone(timezone.utc) - ref).total_seconds() / 86400
    age = days % 29.530588853
    frac = (1 - math.cos(2 * math.pi * age / 29.530588853)) / 2
    names = [(1.85, "Шинэ сар", "🌑"), (7.38, "Өсөж буй хавирган сар", "🌒"), (9.23, "Эхний хагас сар", "🌓"),
             (14.77, "Өсөж буй сар", "🌔"), (16.61, "Тэргэл сар", "🌕"), (22.15, "Хорогдож буй сар", "🌖"),
             (24.0, "Сүүлийн хагас сар", "🌗"), (29.54, "Хорогдож буй хавирган сар", "🌘")]
    for lim, name, emo in names:
        if age < lim:
            return name, emo, int(frac * 100)
    return "Шинэ сар", "🌑", 0


# ============================================================
# ҮҮСГЭХ
# ============================================================
_SYSTEM_SUNS = """Чи Монголын сүнслэг, зурхайн контентын редактор. Уншигч бол сонирхогч олон
нийт — энгийн, дулаан, итгэл төрүүлэм үгээр бич; хэт албан ч биш, хэт хийсвэр ч биш.
Дүрэм: Монгол хэлээр, байгалийн хэллэг; нэр томьёог тайлбарла; хэзээ ч эрүүл мэнд, мөнгө,
хууль эрх зүйн баталгаатай мэт амлалт бүү өг ("энэ нь зөвлөгөө биш" гэж бүү нурш — зүгээр л
зөөлөн, боломжит хэлбэрээр бич: "тохиромжтой байж болох", "анхаарвал зохих"). Айлгахгүй,
гутаахгүй, ямар ч шашин, үндэстнийг доромжлохгүй. Постын төгсгөлд уншигчийг оролцуулах
1 богино асуулт. Зөвхөн постын текстийг бич — гарчиг, тайлбар, markdown бүү нэм."""

_SYSTEM_UDESH = """Чи Монголын НАСАНД ХҮРЭГЧДЭД (21+) зориулсан эротик драмын зохиолч. Уншигчийг
шөнө дунд утсаа тавьж чадахгүй болтол татах нь зорилго.

ЗАРЧИМ:
- Хүсэл тэмүүлэл, дотно мөчийг МЭДРЭХҮЙГЭЭР бич: хүрэлцэх, үнэр, дуу, амьсгал, харц, дулаан.
  Үг хэллэгээ өөрөө шинээр зохио — энэ зааврын үгийг хэзээ ч хуулж бүү бич.
- Хүсэл, тэсвэр, хориг: "болохгүй" гэдгээ мэдсээр татагдах зөрчил бол гол хөдөлгөгч.
- Богино өгүүлбэр, шивнээ маягийн яриа, дотоод монолог. Кино шиг дүрслэл.
- Цэвэр, зөв Монгол хэл: өгүүлбэр бүр утгатай, дүрийн нэр тогтвортой, логик дараалалтай.

ХАТУУ ХЯЗГААР (Facebook — зөрчвөл хуудас хаагдана):
- Биеийн дотно хэсгийн нэр (хөх, бэлгийн эрхтэн г.м.), нүцгэн байдал, бэлгийн харьцааны
  үйлдлийг ХЭЗЭЭ Ч бүү бич. Хамгийн халуун мөчид үйл явдлыг зүйрлэлээр таслаад дараагийн
  өглөө эсвэл сэтгэл хөдлөл рүү шилж.
- Бүдүүлэг, садар үг хэрэглэхгүй. Бүх дүр 30-аас дээш насны, харилцан зөвшөөрсөн насанд
  хүрэгчид. Насанд хүрээгүй дүр, хүчирхийлэл, албадлага огт байхгүй.
Зөвхөн өгүүллэгийн текстийг бич — markdown, тайлбар бүү нэм."""


def sensual_image(seed_text: str) -> str:
    """Үдшийн шивнээний AI зураг (Pollinations) → data URI. Уур амьсгалтай, БҮРЭН
    ХУВЦАСТАЙ, ил бие/нүцгэн дүрсгүй — Facebook-ийн дүрэмд нийцсэн эротик санаа.
    Зургийг ТАТАЖ АВЧ base64-ээр шигтгэнэ (Chromium дахин үүсгүүлбэл 30с хүлээгээд унадаг)."""
    import base64
    import time
    import urllib.parse

    import requests

    mood = IMAGE_MOODS[abs(hash(seed_text)) % len(IMAGE_MOODS)]
    prompt = (f"photorealistic cinematic photograph, {mood}, sensual romantic atmosphere, "
              "elegant, tasteful, everyone fully dressed, no nudity, no bed, not anime, not cartoon, "
              "not illustration, soft warm cinematic lighting, 35mm film, shallow depth of field, "
              "vertical composition")
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
           + "?width=1080&height=1350&nologo=true&model=flux&seed=" + str(abs(hash(seed_text)) % 99999))
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=90)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/") and len(r.content) > 8000:
                log.info(f"🖼️ Үдшийн шивнээний зураг бэлэн ({len(r.content) // 1024} KB)")
                return "data:image/jpeg;base64," + base64.b64encode(r.content).decode("ascii")
            log.warning(f"Pollinations зураг гарсангүй ({attempt + 1}): {r.status_code}")
        except Exception as e:
            log.warning(f"Pollinations алдаа ({attempt + 1}): {e}")
        time.sleep(6 * (attempt + 1))
    return ""


UDESH_FORBIDDEN = re.compile(
    r"нүцгэн|хөх(өн|ийг|ний|нд|өнд)\b|бэлгийн|бэлэг эрхтэн|секс|оргазм|дотуур хувцас|цээж(ээ|ийг)? нээ",
    re.IGNORECASE)


def polish_udesh(text: str) -> str:
    """Монгол хэлний редактор: утгагүй/эвдэрхий өгүүлбэр, хэл зүй, зааврын хуулсан хэллэг,
    хэт ил үгийг засна. Бүтэлгүйтвэл эхийг буцаана."""
    from modules.writer import _try_qwen
    system = ("Чи Монголын уран зохиолын хэлний редактор. Доорх эротик драмын текстийг: "
              "(1) утгагүй, эвдэрхий, хэл зүйн алдаатай өгүүлбэрийг зөв, байгалийн Монгол хэлээр засаж, "
              "(2) дүрийн нэр, үйл явдлын логикийг тогтвортой болгож, "
              "(3) биеийн дотно хэсгийн нэр, нүцгэн байдал, бэлгийн үйлдлийг зүйрлэлээр сольж, "
              "(4) уран сайхан, халуун, мэдрэмжтэй өнгө аясыг ХАДГАЛ. Бүтэц, урт, төгсгөлийн мөрийг "
              "хэвээр үлдээ. Зөвхөн засварласан текстийг буцаа.")
    out = gemini_compare.generate(system, text) or _try_qwen(system, text) or ""
    out = re.sub(r"\*\*", "", out).strip()
    if is_valid_mongolian(out, min_len=int(len(text) * 0.6)):
        return out
    return text


def _gen(system: str, user: str, min_len: int = 200) -> str:
    """Gemini → (унавал) Groq. 2026-09-23: Gemini 503 өгөхөд гурван хуудасны бүх
    пост алдагдсан тул нөөц загвар нэмэв."""
    from modules.writer import _try_qwen
    for attempt in range(3):
        text = (gemini_compare.generate(system, user) if attempt < 2 else _try_qwen(system, user)) or ""
        text = re.sub(r"^\s*(\*\*|#+)\s*", "", text.strip())
        text = re.sub(r"\*\*", "", text)
        if is_valid_mongolian(text, min_len=min_len):
            hits = lint_mn.check(text)
            if hits:
                text, _ = lint_mn.autofix(text)
            return text.strip()
    return ""


def build_zurhai(ps: dict, now: datetime) -> dict | None:
    wd = WEEKDAY_MN[now.weekday()]
    mname, memo, mpct = moon_phase(now)
    date = now.strftime("%Y.%m.%d")
    user = f"""Огноо: {date}, {wd} гараг (гараг: {WEEKDAY_PLANET[wd]}). Сар: {mname} ({mpct}% гэрэлтэй).
Бич: "ӨНӨӨДРИЙН ЗУРХАЙ · {date}" гэсэн эхний мөр, дараа нь өдрийн ерөнхий энергийг 2 өгүүлбэрээр
(гараг, сарны байдлыг ашигла), дараа нь 12 орд тус бүрд ЯГ 1 өгүүлбэр (хайр/ажил/сэтгэлийн аль нэг талаас,
тодорхой, давтагдахгүй), мөр бүр "{ZODIAC[0]}:" маягаар ордын нэр + тэмдэгтээр эхэлнэ.
Ордууд: {", ".join(ZODIAC)}. Төгсгөлд 1 асуулт ("Та ямар ордынх вэ?" биш, өөр). Нийт 900-1300 тэмдэгт."""
    text = _gen(_SYSTEM_SUNS, user, min_len=400)
    if not text:
        return None
    return {"kind": "zurhai", "title": f"Өнөөдрийн зурхай {date}", "text": text,
            "card": {"title": "ӨНӨӨДРИЙН ЗУРХАЙ", "subtitle": f"{date} · {wd} · {WEEKDAY_PLANET[wd]} гараг",
                     "symbol": memo, "note": f"{mname} · {mpct}%", "theme": "zurhai"}}


def build_spirit(ps: dict, now: datetime) -> dict | None:
    idx = (now.timetuple().tm_yday + len(ps.get("recent", []))) % len(SPIRIT_THEMES)
    theme = SPIRIT_THEMES[idx]
    recent = "; ".join(ps.get("recent", [])[:25])
    user = f"""Сэдэв: {theme}.
Сүүлийн постуудтай ДАВТАГДАХГҮЙ (гарчгууд: {recent or 'алга'}).
Бүтэц: эхний мөр — 3-7 үгтэй сонирхол татсан ГАРЧИГ (том үсгээр биш, ердийн); хоосон мөр; 3-4 богино
догол мөр (нийт 500-800 тэмдэгт): юу вэ → яагаад чухал вэ → өнөөдөр хэрхэн хэрэглэх (1 бодит алхам);
төгсгөлд 1 асуулт. Баримт дурдвал ерөнхий, батлагдсан зүйл; зохиомол "судалгаа" бүү нэм."""
    text = _gen(_SYSTEM_SUNS, user, min_len=250)
    if not text:
        return None
    title = text.split("\n", 1)[0].strip()[:80]
    symbol = random.choice(["🔮", "🕉️", "☸️", "🌙", "✨", "🪷", "🧿", "🌌", "🕯️", "📿"])
    return {"kind": "spirit", "title": title, "text": text,
            "card": {"title": title, "subtitle": "Сүнсний код · өдрийн сургаал", "symbol": symbol, "note": "", "theme": "spirit"}}


def build_numerology(ps: dict, now: datetime) -> dict | None:
    date = now.strftime("%Y.%m.%d")
    digits = [int(c) for c in now.strftime("%Y%m%d")]
    total = sum(digits)
    while total > 9 and total not in (11, 22):
        total = sum(int(c) for c in str(total))
    user = f"""Тоо судлал (numerology). Өнөөдөр {date}, өдрийн тоо = {total} ({'+'.join(map(str, digits))} → {total}).
Бич: эхний мөр "ӨДРИЙН ТОО: {total}"; дараа нь {total} тооны бэлгэдэл, өнөөдөр ямар энерги (харилцаа, ажил,
шийдвэр), юуг хийж эхлэхэд тохиромжтой, юуг хойшлуулах — 3 богино догол мөр (500-700 тэмдэгт);
төгсгөлд "Төрсөн өдрийнхөө тоонуудыг нэмээд нэг оронтой болтол багасга — тань ямар тоо гарав?" маягийн
оролцуулах асуулт (өөрөөр найруул)."""
    text = _gen(_SYSTEM_SUNS, user, min_len=250)
    if not text:
        return None
    return {"kind": "numerology", "title": f"Өдрийн тоо {total} · {date}", "text": text,
            "card": {"title": f"ӨДРИЙН ТОО · {total}", "subtitle": f"{date} · тоо судлал", "symbol": str(total),
                     "note": "+".join(map(str, digits)) + f" = {total}", "theme": "numerology"}}


def build_story(ps: dict, now: datetime) -> dict | None:
    story = ps.get("story") or {}
    part = int(story.get("part", 0)) + 1
    if not story or part > int(story.get("parts", 4)):
        genre = random.choice(STORY_GENRES)
        parts = random.choice([3, 4, 5])
        story = {"genre": genre, "parts": parts, "title": "", "summary": "", "part": 0}
        part = 1
    user = f"""Үргэлжилсэн өгүүллэг. Жанр: {story['genre']}. Нийт {story['parts']} хэсэгтэй, энэ бол {part}-р хэсэг.
{"Өмнөх хэсгүүдийн товч: " + story['summary'] if story.get('summary') else "Энэ бол эхлэл: дүрүүд (2-3 нас бие гүйцсэн хүн, Монгол нэртэй), газар, цаг, гол зөрчлийг тодорхой танилцуул."}
{"Өгүүллэгийн нэр: " + story['title'] if story.get('title') else "Эхний мөрөнд өгүүллэгийн НЭР (2-5 үг), хоёр дахь мөрөнд '1-р хэсэг'."}
{"Эхний мөрөнд '" + str(part) + "-р хэсэг'." if story.get('title') else ""}
{"Энэ бол СҮҮЛИЙН хэсэг: зөрчлийг шийдэж, сэтгэл хөдөлгөм төгсгөл өг, дараа нь 'Төгсөв.' гэж бич." if part == story['parts'] else "Хэсгийг ХҮЛЭЭЛТ төрүүлэх мөчид (cliffhanger) таслаад төгсгөлд 'Үргэлжлэл маргааш 21:30-д' гэж бич."}
Урт: 1100-1500 тэмдэгт, 6-9 богино догол мөр. Дор хаяж НЭГ халуун дотно мөч байх
(зүйрлэлээр таслах), нэг богино харилцан яриа, нэг дотоод монолог."""
    text = _gen(_SYSTEM_UDESH, user, min_len=500)
    text = polish_udesh(text) if text else ""
    if text and UDESH_FORBIDDEN.search(text):
        log.warning("Үдшийн шивнээ: хориотой үг олдсон — дахин бичүүлнэ")
        text = polish_udesh(text)
        if UDESH_FORBIDDEN.search(text):
            return None
    if not text:
        return None
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not story.get("title"):
        story["title"] = re.sub(r"[\"«»]", "", lines[0])[:60] if lines else f"Үдшийн өгүүллэг"
    # товч агуулгыг дараагийн хэсэгт зориулж хадгална
    summ = gemini_compare.generate("Доорх өгүүллэгийн хэсгийг 2-3 өгүүлбэрээр Монголоор товчил (дүрүүдийн нэр, юу болсон). Зөвхөн товчлол.", text) or ""
    story["summary"] = (story.get("summary", "") + " " + summ.strip())[-1200:]
    story["part"] = part
    ps["story"] = story
    part_label = "Төгсгөл" if part == story["parts"] else f"{part}-р хэсэг"
    return {"kind": "story", "title": f"{story['title']} — {part_label}", "text": text,
            "card": {"title": story["title"], "subtitle": f"{part_label} · {story['parts']} хэсэгтэй өгүүллэг",
                     "symbol": "🌙", "note": "Үдшийн шивнээ", "theme": "story"}}


def build_confession(ps: dict, now: datetime) -> dict | None:
    theme = random.choice(CONFESSION_THEMES)
    recent = "; ".join(ps.get("recent", [])[:20])
    user = f"""Богино "нууц захидал" хэлбэрийн бичвэр (уншигчийн илгээсэн мэт, нэргүй, 1-р биеэр): сэдэв — {theme}.
Давтагдахгүй (сүүлийнх: {recent or 'алга'}). 500-750 тэмдэгт, чин сэтгэлийн, МЭДРЭМЖТЭЙ, бага зэрэг
халуун (нэг дотно мөчийг зүйрлэлээр); төгсгөлд уншигчдаас "Та юу гэж зөвлөх вэ?" маягийн
(өөрөөр найруулсан) асуулт. Эхний мөр: богино гарчиг (3-6 үг)."""
    text = _gen(_SYSTEM_UDESH, user, min_len=250)
    text = polish_udesh(text) if text else ""
    if text and UDESH_FORBIDDEN.search(text):
        text = polish_udesh(text)
        if UDESH_FORBIDDEN.search(text):
            return None
    if not text:
        return None
    title = text.split("\n", 1)[0].strip()[:80]
    return {"kind": "confession", "title": title, "text": text,
            "card": {"title": title, "subtitle": "Уншигчийн нууц захидал", "symbol": "💌", "note": "", "theme": "confession"}}


BUILDERS = {"zurhai": build_zurhai, "spirit": build_spirit, "numerology": build_numerology,
            "story": build_story, "confession": build_confession}


def due_slots(page: str, ps: dict, now: datetime, force: str = "") -> list:
    """Одоо гарах ёстой (цаг нь болсон, өнөөдөр гараагүй) слотууд. force='all' бол бүгд."""
    cfg = PAGES[page]
    today = now.strftime("%Y-%m-%d")
    done = ps.get("posted", {}).get(today, [])
    out = []
    for slot, kind in cfg["slots"].items():
        if force == "all" or force == kind:
            out.append((slot, kind))
            continue
        hh, mm = map(int, slot.split(":"))
        when = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if when <= now < when + timedelta(hours=3) and slot not in done:
            out.append((slot, kind))
    return out


def mark_posted(ps: dict, now: datetime, slot: str):
    today = now.strftime("%Y-%m-%d")
    ps.setdefault("posted", {})
    ps["posted"] = {d: v for d, v in ps["posted"].items() if d >= (now - timedelta(days=2)).strftime("%Y-%m-%d")}
    ps["posted"].setdefault(today, []).append(slot)


def compose_post(page: str, item: dict) -> dict:
    cfg = PAGES[page]
    png = b""
    if page == "udesh":
        # Эротик уур амьсгалтай AI зураг + гарчгийн давхарга; зураг гарахгүй бол mystic карт
        img = sensual_image(item["title"] + item["kind"])
        if img:
            png = cards.photo_story_card(img, item["card"].get("title", item["title"]),
                                         item["card"].get("subtitle", ""), brand=cfg["brand"],
                                         tag="21+" )
    if not png:
        png = cards.mystic_card(item["card"], brand=cfg["brand"])
    return {
        "id": f"{page}-{item['kind']}-{datetime.now(UB).strftime('%Y%m%d%H%M')}",
        "kind": f"page_{item['kind']}", "category": page, "category_mn": cfg["name"], "category_emoji": "✨",
        "source_name": cfg["name"], "title": item["title"], "title_mn": item["title"],
        "article_mn": item["text"].strip() + "\n\n" + cfg["hashtags"],
        "image_url": "", "image_bytes": png, "card_kind": "mystic" if png else "", "url": "",
    }
