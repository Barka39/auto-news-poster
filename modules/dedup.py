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
    # Headline-д томоор бичигддэг түгээмэл англи үгс. БОДИТ АЛДАА:
    # "Gary Trent Gets Paid" гэдэг title-case гарчгийн "Gets", "Paid"
    # хүний нэр мэт тоологдож олонлогийг хөөргөснөөс давхардал
    # баригдаагүй. Эдгээр үг нэр БИШ тул хоёр олонлогоос хоёуланг нь
    # хасна.
    "gets", "get", "got", "goes", "going", "makes", "made", "takes",
    "took", "gives", "given", "paid", "pays", "signs", "signing",
    "signed", "agrees", "agreed", "reach", "reaches", "reached",
    "inks", "lands", "joins", "joining", "leaves", "leaving", "deal",
    "deals", "contract", "extension", "trade", "traded", "beats",
    "beat", "wins", "win", "won", "loses", "loss", "lost", "leads",
    "led", "scores", "scored", "star", "stars", "boss", "chief",
    "says", "said", "claims", "reveals", "reportedly", "report",
    "reports", "rumors", "rumours", "returns", "return", "ready",
    "set", "eyes", "eyeing", "keen", "close", "closes", "moves",
    "move", "here", "why", "how", "what", "when", "watch", "look",
    "inside", "big", "huge", "major", "top", "best", "worst", "first",
    "last", "next", "now", "just", "still", "back", "out", "off",
    "million", "billion", "year", "years", "day", "days", "night",
    "week", "hero", "heroes", "king", "dies", "dead", "aged", "amid",
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
    for prev in previous_titles or []:
        if same_topic(title, prev):
            log.info(f"[DEDUP] ижил сэдэв: «{title[:45]}» ≈ «{prev[:45]}»")
            return True
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


# ============================================================
# 2026-09-23: НЭМЭЛТ ХОЁР ДҮРЭМ (бодит алдаа: Kawhi-гийн гэрээ 3 удаа,
# Hawks-Hornets-ийн трейд 2 удаа тус тусын сайтаас орсон)
#   A) ижил ХҮНИЙ БҮТЭН НЭР (хоёр дараалсан том үсэгтэй үг) хоёуланд байвал
#   B) ижил ХОЁР БАГИЙН нэр хоёуланд байвал
# Мөн эзэмшлийн 's болон олон тоог таслаж харьцуулна (Leonard's = Leonard,
# Raptors = Raptor) — өмнө нь эдгээрээс болж overlap 0.5 болж унадаг байв.
# ============================================================
NBA_TEAMS = {
    "hawks", "celtics", "nets", "hornets", "bulls", "cavaliers", "cavs", "mavericks", "mavs",
    "nuggets", "pistons", "warriors", "rockets", "pacers", "clippers", "lakers", "grizzlies",
    "heat", "bucks", "timberwolves", "wolves", "pelicans", "knicks", "thunder", "magic",
    "sixers", "76ers", "suns", "blazers", "trail", "kings", "spurs", "raptors", "jazz", "wizards",
}

_FULLNAME_RE = re.compile(r"\b([A-Z][a-z]{2,})[- ]([A-Z][a-z]{2,})\b")


def _norm(word: str) -> str:
    w = word.lower().strip(".,:;!?\"'()[]")
    w = re.sub(r"(?:'s|’s)$", "", w)
    if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return w


def full_names(title: str) -> set:
    """«Kawhi Leonard», «Finney Smith» гэх мэт хүний бүтэн нэрс."""
    out = set()
    for a, b in _FULLNAME_RE.findall(title or ""):
        if _norm(a) in _STOPWORDS or _norm(b) in _STOPWORDS:
            continue
        if _norm(a) in NBA_TEAMS or _norm(b) in NBA_TEAMS:
            continue
        out.add(f"{_norm(a)} {_norm(b)}")
    return out


def teams_in(title: str) -> set:
    return {_norm(w) for w in re.findall(r"[A-Za-z0-9'’-]+", title or "")} & NBA_TEAMS


def same_topic(title: str, other: str) -> bool:
    a_names, b_names = full_names(title), full_names(other)
    if a_names & b_names:
        return True
    at, bt = teams_in(title), teams_in(other)
    if len(at & bt) >= 2:
        return True
    # нормчилсон proper noun давхцал (эзэмшил/олон тоо арилгасан)
    ap = {_norm(w) for w in _signatures(title)[0]}
    bp = {_norm(w) for w in _signatures(other)[0]}
    shared = ap & bp
    if len(shared) >= 2 and len(shared) / max(min(len(ap), len(bp)), 1) >= 0.5:
        return True
    return False
