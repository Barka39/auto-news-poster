"""
Сэдвийн түвшний давхардал илрүүлэгч.

АСУУДАЛ: posted_ids.json зөвхөн URL hash хадгалдаг тул BBC болон
Sky Sports хоёулаа ИЖИЛ мэдээ (жишээ: Guehi-гийн гэмтэл) бичихэд
хоёуланг нь тус тусад нь постолж, хуудсанд дублэкат үүсдэг байсан.

ШИЙДЭЛ: Гарчгаас "чухал үгс"-ийг (Латин proper noun + урт үгс)
ялгаж аваад, өмнөх гарчгуудтай давхцлыг (Jaccard) харьцуулна.
Нэг run доторх batch болон сүүлийн 48ц-ийн постуудад хоёуланд ажиллана.
"""

import re
import logging

log = logging.getLogger(__name__)

# ХОЁР ШАЛГУУР (аль нэг нь хангагдвал давхардал):
# 1) Proper noun (нэрс: Guehi, Norway...) overlap coefficient ≥ 0.6
#    БА дор хаяж 2 нэр давхцах — сэдвийг нэрс хамгийн сайн ялгадаг
# 2) Бүх signature үгсийн overlap ≥ 0.6 БА дор хаяж 3 үг давхцах
# (Overlap coefficient = давхцал / богино олонлогийн хэмжээ. Jaccard-с
# илүү тохиромжтой — нэг сайт урт, нөгөө нь богино гарчиг бичихэд
# Jaccard хиймлээр буурдаг байсан)
PROPER_THRESHOLD = 0.6
PROPER_MIN_SHARED = 2
FULL_THRESHOLD = 0.6
FULL_MIN_SHARED = 3

# Спорт мэдээнд байнга давтагддаг, сэдэв ялгахад хэрэггүй үгс
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "with", "over", "after",
    "before", "as", "in", "on", "at", "to", "of", "by", "from", "his",
    "her", "their", "its", "is", "are", "was", "were", "be", "been",
    "will", "would", "could", "may", "might", "has", "have", "had",
    "says", "say", "said", "new", "latest", "report", "reports", "news",
    "live", "update", "updates", "vs", "v",
    # Гарчгийн хэв маягийн үгс — сэдэв ялгадаггүй
    "sources", "source", "exclusive", "official", "breaking", "confirmed",
}

# Тоон токен: гэрээний дүн ($252M), оноо (97-96) зэрэг нь сэдвийг
# хамгийн хүчтэй таниулдаг. Он (19xx/20xx) хэт түгээмэл тул хасна.
_NUM_RE = re.compile(r"\d{2,4}")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")


def _signatures(title: str) -> tuple:
    """Гарчгаас (proper_nouns, all_words) хоёр олонлог гаргана."""
    words = _WORD_RE.findall(title or "")
    proper, full = set(), set()

    # Тоон токенууд хоёр олонлогт хоёуланд нь орно.
    # БОДИТ АЛДАА: Wemby-ийн $252M гэрээ 3 удаа давхар постлогдсон —
    # "Wemby" vs "Wembanyama", "Spurs'" vs "Spurs" гэж нэрс таараагүй ч
    # 252 гэсэн тоо бүх гарчигт байсан.
    for num in _NUM_RE.findall(title or ""):
        if not _YEAR_RE.match(num):
            proper.add(num)
            full.add(num)

    for i, w in enumerate(words):
        # Апострофыг ХОЁР талаас нь хайчилна: "Spurs'" → "spurs"
        lw = w.lower().strip("'-")
        if not lw or lw in _STOPWORDS:
            continue
        if len(lw) >= 4 or w[0].isupper():
            full.add(lw)
        # Өгүүлбэрийн эхний үг том үсгээр эхэлдэг тул нэр гэж
        # андуурахгүйн тулд i > 0 нөхцөл тавина
        if w[0].isupper() and i > 0:
            proper.add(lw)
        elif w[0].isupper() and i == 0 and len(w) >= 3:
            proper.add(lw)  # эхний үг ч гэсэн нэр байж болно (Marc...)
    return proper, full


def _overlap(a: set, b: set) -> tuple:
    """(давхцлын тоо, overlap coefficient) буцаана."""
    if not a or not b:
        return 0, 0.0
    inter = len(a & b)
    return inter, inter / min(len(a), len(b))


def is_duplicate_topic(title: str, previous_titles: list) -> bool:
    """
    title нь previous_titles доторх аль нэгтэй ижил сэдэв мөн эсэх.
    previous_titles: str жагсаалт (эх Англи гарчгууд).
    """
    proper, full = _signatures(title)
    if not full:
        return False

    for prev in previous_titles:
        p_proper, p_full = _signatures(prev)

        n, coef = _overlap(proper, p_proper)
        if n >= PROPER_MIN_SHARED and coef >= PROPER_THRESHOLD:
            log.info(
                f"🔁 Сэдвийн давхардал (нэрс: {n} давхцал, coef={coef:.2f}): "
                f"'{title[:50]}' ≈ '{prev[:50]}'"
            )
            return True

        n, coef = _overlap(full, p_full)
        if n >= FULL_MIN_SHARED and coef >= FULL_THRESHOLD:
            log.info(
                f"🔁 Сэдвийн давхардал (үгс: {n} давхцал, coef={coef:.2f}): "
                f"'{title[:50]}' ≈ '{prev[:50]}'"
            )
            return True
    return False
