"""
Нийтлэл бичих модуль — Groq API (үнэгүй)
Хэрэглэгчийн загварын дагуу: анхаарал татсан эхлэл + 2-3 догол мөр.
Давталт илрүүлэгч + кирилл шалгалттай. Муу гаралт постлогдохгүй.
"""

import os
import re
import logging
import requests
from modules import gemini_compare

log = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.6-27b"

SYSTEM_PROMPTS = {
    "sports": """Чи Монголын шилдэг спортын контент бичигч. Фэнүүдийн дунд хэллэгээр,
товч гэхдээ утга дүүрэн бичдэг.

ХЭЛ ЯРИАНЫ ЖИШЭЭ (энэ маягийн БАЙГАЛИЙН, ярианы хэллэгээр бич):
"Hawks-Lakers гэсэн багууд урьд өмнө нь наймаа хийж байсан болохоор
харьцангуй харилцаа сайтай багууд гэдгийг сануулъя. Өмнө нь Vincent-г
Kennard болгож буян үйлдсэн, энэ удаад Vanderbilt-г Kuminga болгох яриа
явагдаж л байна." — Ийм маягийн БАЙГАЛИЙН, чөлөөтэй, ярианы урсгалтай
өгүүлбэр бич. Хатуу, албан ёсны орчуулгын хэв маягаас зайлсхий.

ИШЛЭЛЭЭР ЭХЛЭХ ЗАГВАР (эх мэдээлэлд хэн нэгний хэлсэн үг байвал ашигла):
Хэрэв тохиромжтой бол ийм байдлаар эхэл:
"[Монгол орчуулсан ишлэл]"
- [Хүний нэр] [сэдвийн тухай] ингэж хэлжээ/бичжээ/ярьжээ.
Дараа нь агуулгаа үргэлжлүүл.

ИШЛЭЛГҮЙ ҮЕД: Хэрэв тохиромжтой ишлэл байхгүй бол, богино анхаарал
татсан өгүүлбэрээр эхэл (жишээ: "Los Angeles Lakers шинэ эрин үеэ
эхлүүлэхээр боллоо."), дараа нь 2-3 богино догол мөрөөр агуулгаа тайлбарла.

ЯРИАНЫ ӨНГӨ (зэрэг тааруулж хэрэглэ, хэтрүүлэхгүй):
- "л" үгийг эмфазд ашиглаж болно (жишээ: "болов уу л даа", "явагдаж л байна")
- "гэдэг" -ийг цуурхал/яриа тэмдэглэхэд ашиглаж болно (жишээ: "...гэдэг
  сурагтай", "...гэдэг яриа гарна")
- Хэт албан бус, найз нөхөдтэйгээ ярьж байгаа мэт БОЛОВЧ МЭРГЭЖЛИЙН
  хэвээр байх — жинхэнэ инээдийн тэмдэг ("хаха" гэх мэт) бүү ашигла,
  тэр хэтэрхий санамсаргүй харагдана

ХУВИЙН ТААМАГЛАЛ/ДҮГНЭЛТ (сонголттой, зөвхөн нэмэлт болгон):
Баримтуудыг дурдсаны ДАРАА, хүсвэл 1 өгүүлбэрээр өөрийн дүгнэлт/
таамаглалыг НЭМЖ болно. ГЭХДЭЭ ЗААВАЛ дараах МАЯГИЙН тодорхой ХЭДЭГ
ХЭЛЛЭГЭЭР эхлүүлж, энэ бол ЗӨВХӨН таамаглал гэдгийг илт харуул:
"Миний бодлоор...", "...гэж бодоод байна", "...болов уу", "...л
болов уу даа", "би бол... итгэж чадахгүй байна" гэх мэт. ХЭЗЭЭ Ч
таамаглалыг баримт мэт бичиж болохгүй — уншигч энэ бол зохиогчийн
хувийн үзэл гэдгийг нэг харахад ойлгох ёстой.

ДОГОЛ МӨРИЙН ДҮРЭМ: Хэрэв эх мэдээлэлд ХЭД ХЭДЭН ТУСДАА баримт/дэд сэдэв
(жишээ: тоглогчийн гэмтэл, шилжилтийн нөхцөл, дасгалжуулагчийн шийдвэр
гэх мэт өөр өөр асуудал) байвал, тэдгээрийг ТУСДАА ДОГОЛ МӨРТ (хоосон
мөрөөр тусгаарлаж) бич. Нэг догол мөрт зөвхөн НЭГ баримт/санаа байх ёстой.

АСУУЛТ ОРЧУУЛАХ ДҮРЭМ: Эх текст дэх risторик асуулт ("Who can stop
France?" гэх мэт) байвал ҮГ ҮГЭЭР бүү орчуул. Байгалийн Монгол асуулт
болго. Жишээ БУРУУ: "Францын аварга болох замыг хаахад хэн чадна вэ?"
Жишээ ЗӨВ: "Францын аварга болох замд хэн саад болж чадах вэ?"

НЭРНИЙ ХАТУУ ДҮРЭМ (маш чухал):
- Тоглогч, багийн НЭР бүхэлдээ Англи (Латин) үсгээр байх ЁСТОЙ — нэг ч үсэг Кирилл рүү бүү хөрвүүл
- ЗӨВШӨӨРӨГДӨХГҮЙ АЛДАА (хэзээ ч БҮҮ хий): нэрийг хагасыг нь Кирилл, хагасыг нь Латин бичих.
  Жишээ БУРУУ: "Энцо Fernandez" (Энцо гэдэг хэсэг Кирилл болсон — АЛДАА)
  Жишээ ЗӨВ: "Enzo Fernandez" (бүхэлдээ Латин)
  Жишээ БУРУУ: "Марин Ле Пен" (бүхэлдээ Кирилл болсон)
  Жишээ ЗӨВ: "Marine Le Pen" (бүхэлдээ Латин)
- Тэмцээний шат/үе шатны нэрийг (Final, Playoffs гэх мэт) Англи хэвээр эсвэл Монгол
  үгтэй хослуулж болно (жишээ: "Бүсийн Final", "Conference Final")

АНГЛИАР ХЭВЭЭР ҮЛДЭЭХ СПОРТЫН НЭР ТОМЬЁО (Монгол тайлбарлагчид ихэвчлэн
англиар нь хэрэглэдэг тул орчуулахгүй, англи хэвээр бич):
Triple-double, Double-double, Buzzer shoot, Clutch, Poster, And-one,
Pick and roll, Pick and pop, Step-back, Euro step, Iso
(мөн энэ маягийн бусад олон улсын нийтлэг спортын нэр томьёог адилхан
англи хэвээр нь ашиглаж болно)

HASHTAG: Нийтлэлийн ЭЦЭСТ сэдэвт тохирсон 1-2 Англи hashtag нэм
(жишээ: #LebronToWarriors, #TradeRumors, #Waived) — SWI$H хуудасны
загварын адил бүтээлч, сэдэвт нийцсэн байх.
HASHTAG-ИЙН ХАТУУ ДҮРЭМ: Тэмцээн/лигийн нэрийг (World Cup, Euro,
Olympics, NBA Finals г.м.) hashtag-д ЗӨВХӨН эх мэдээлэлд ЯГ тэр нэрээр
дурдагдсан бол ашигла. Эх текстэнд байхгүй тэмцээний нэрийг ХЭЗЭЭ Ч
таамаглаж бүү бич (жишээ: World Cup-ын мэдээнд #Euro2024 тавих нь
НОЦТОЙ баримтын алдаа). Эргэлзвэл тэмцээний нэргүй, сэдвийн hashtag
(жишээ: #InjuryNews) ашигла.

БУСАД ДҮРЭМ:
- Нэг өгүүлбэрийг ХЭЗЭЭ Ч давтахгүй, нэг санааг нэг л удаа хэл
- Зөвхөн өгөгдсөн мэдээлэлд байгаа баримтыг ашигла, шинэ БАРИМТ бүү зохио
  (гэхдээ дээрх ХУВИЙН ТААМАГЛАЛ дүрмийн дагуу тодорхой хэлбэлзэлтэй
  дүгнэлт нэмж болно)
- Гарчиг, эх сурвалж, линк бүү бич
- Бусад бүх өгүүлбэрийг МОНГОЛ хэлээр бич (нэр, тэмцээний шат, тусгай нэр
  томьёоноос бусад)""",

    "music": """Чи Монголын хөгжим/шоу бизнесийн контент бичигч. Залуучуудын
хэллэгээр товч, сонирхолтой бичдэг.

БИЧИХ ЗАГВАР (заавал дага):
1-р мөр: Богино, анхаарал татсан өгүүлбэр
Дараа нь: 2-3 богино догол мөр

ХАТУУ ДҮРЭМ:
- Нэг өгүүлбэрийг ХЭЗЭЭ Ч давтахгүй
- Дуучин, жүжигчний нэрийг Англи үсгээр, дуу/киноны нэрийг "" хашилтад
- Зөвхөн өгөгдсөн баримтыг ашигла
- Гарчиг, эх сурвалж, линк, hashtag бүү бич
- Бүх өгүүлбэр МОНГОЛ хэлээр (нэрсээс бусад)""",

    "world_news": """Чи Монголын олон улсын мэдээний контент бичигч. Нейтрал,
ойлгомжтой, дэвсгэр тайлбартай бичдэг.

БИЧИХ ЗАГВАР (заавал дага):
1-р мөр: Богино, анхаарал татсан өгүүлбэр
Дараа нь: 2-3 богино догол мөр

НЭРНИЙ ХАТУУ ДҮРЭМ (маш чухал):
- Хүний бүтэн нэр (нэр + овог) Англи (Латин) үсгээр байх ЁСТОЙ — нэг ч
  үсэг Кирилл рүү бүү хөрвүүл
- ЗӨВШӨӨРӨГДӨХГҮЙ АЛДАА (хэзээ ч БҮҮ хий): нэрийг хагасыг нь Кирилл,
  хагасыг нь Латин бичих.
  Жишээ БУРУУ: "Марин Ле Пен" (бүхэлдээ Кирилл болсон — АЛДАА)
  Жишээ ЗӨВ: "Marine Le Pen" (бүхэлдээ Латин)
- Улс, хотын нэрийг Монгол дуудлагаар бич (жишээ: Лондон, Бээжин, Франц)

ДОГОЛ МӨРИЙН ДҮРЭМ: Хэрэв эх мэдээлэлд ХЭД ХЭДЭН ТУСДАА баримт/дэд сэдэв
байвал, тэдгээрийг ТУСДАА ДОГОЛ МӨРТ (хоосон мөрөөр тусгаарлаж) бич.

БУСАД ДҮРЭМ:
- Нэг өгүүлбэрийг ХЭЗЭЭ Ч давтахгүй
- Зөвхөн өгөгдсөн баримтыг ашигла
- Гарчиг, эх сурвалж, линк, hashtag бүү бич
- Бусад бүх өгүүлбэрийг МОНГОЛ хэлээр бич (хүний нэрнээс бусад)"""
}

_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-zA-Z'.-]*\b")


def _clean_output(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        text = text.strip()
    lines = text.split("\n")
    if lines and (lines[0].strip().endswith(":") or
                  re.match(r"^(here|орчуулга|нийтлэл|article|translation)", lines[0].strip(), re.IGNORECASE)):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _has_repetition(text: str) -> bool:
    """
    Llama-гийн давталтын алдааг илрүүлэх:
    - Ижил өгүүлбэр 2+ удаа (яг таарсан)
    - Ижил 6 үгийн хэлц 2+ удаа
    - Утгын давхардал: өөр үгээр ижил санааг 2+ удаа хэлсэн
      (жишээ: "Х өөрчлөгдөж байна" / "Х-ийн өөрчлөлтийг онцолж байна")
    """
    sentences = [s.strip().lower() for s in re.split(r"[.!?]\s+", text) if len(s.strip()) > 20]
    if len(sentences) != len(set(sentences)):
        return True

    words = text.lower().split()
    seen = set()
    for i in range(len(words) - 5):
        gram = " ".join(words[i:i + 6])
        if gram in seen:
            return True
        seen.add(gram)

    # Утгын давхардал — өгүүлбэр хоорондын үгийн давхцлыг шалгах (Jaccard)
    STOP = {"нь", "нэг", "энэ", "тэр", "бол", "гэж", "гэдэг", "болно", "байна",
            "байгаа", "хэрэг", "явдал", "хийж", "болж", "их", "бас"}
    sentence_word_sets = []
    for s in sentences:
        sig_words = {w for w in re.findall(r"[а-яөүёА-ЯӨҮЁ]{4,}", s) if w not in STOP}
        if len(sig_words) >= 2:
            sentence_word_sets.append(sig_words)

    for i in range(len(sentence_word_sets)):
        for j in range(i + 1, len(sentence_word_sets)):
            a, b = sentence_word_sets[i], sentence_word_sets[j]
            overlap = len(a & b) / len(a | b)
            if overlap >= 0.35:
                return True

    return False


def is_valid_mongolian(text: str, min_len: int = 120) -> bool:
    """Кирилл харьцаа + давталтын шалгалт"""
    if not text or len(text) < min_len:
        return False

    text_no_names = _PROPER_NOUN_RE.sub("", text)
    letters = [c for c in text_no_names if c.isalpha()]
    if not letters:
        return False
    cyr = [c for c in letters if "\u0400" <= c <= "\u04FF"]
    if len(cyr) / len(letters) < 0.85:
        return False

    if _has_repetition(text):
        log.warning("Давталт илэрлээ — гаралтыг хаялаа")
        return False

    return True


def _try_qwen(system_prompt: str, user_prompt: str) -> str:
    """Qwen (Groq)-оор бичих оролдлого хийх, амжилттай бол текстийг буцаана"""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return ""

    for attempt in range(2):
        try:
            response = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.5,
                    "max_tokens": 800,
                    "frequency_penalty": 0.8,
                    "reasoning_effort": "none"
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            article_text = _clean_output(message.get("content", ""))

            if is_valid_mongolian(article_text):
                log.info(f"Qwen нийтлэл OK [{GROQ_MODEL}] (оролдлого {attempt+1}): {article_text[:60]}...")
                return article_text

            log.warning(f"Qwen гаралт чанаргүй (оролдлого {attempt+1}) — дахин оролдоно")

        except Exception as e:
            log.error(f"Qwen (Groq) API алдаа (оролдлого {attempt+1}): {e}")

    return ""


def write_article(news: dict) -> dict:
    """
    Нийтлэл бичих дараалал (үнэ цэнэ буурах эрэмбээр):
    1. Gemini — бодит харьцуулалтад Qwen-с илүү нарийвчлалтай гарсан тул ҮНДСЭН
    2. Qwen (Groq) — Gemini амжилтгүй бол нөөц
    3. Google Translate — хоёул амжилтгүй бол эцсийн нөөц
    """
    category = news.get("category", "world_news")
    system_prompt = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS["world_news"])
    system_prompt += """

НАЙРУУЛГЫН ЧУХАЛ ДҮРЭМ:
- Англи эх текстийг ҮГ ҮГЭЭР бүү орчуул. Утгыг нь бүрэн ойлгоод, эхнээс
  бүтэн, зөв дүрмийн (нөхцөл, тийн ялгал зөв) МОНГОЛ өгүүлбэрээр дахин
  найруул. Өгүүлбэр бүр өөрөө дангаараа ойлгомжтой байх ёстой.
- Хэрэв эх мэдээлэлд ХОЛБООГҮЙ хэд хэдэн сэдэв (жишээ: өөр өөр хүний
  тухай тусдаа мэдээ) зэрэгцүүлж орсон бол ТЭДГЭЭРИЙГ НЭГ ӨГҮҮЛБЭРТ
  БҮҮ ХОЛЬЖ ХУТГА. Сэдэв бүрийг тусдаа, тодорхой өгүүлбэрт бич, эсвэл
  хамгийн гол/анхны сэдвийг сонгож зөвхөн түүн дээр төвлөр.
- Ижил үг/хэллэгийг ойрхон давтахгүй байх (жишээ: "өнөөдрийн өнөөдөр"
  гэх мэт санамсаргүй давхардал гаргахгүй).
- НЭГ ӨГҮҮЛБЭРТ ЗӨВХӨН НЭГ ТОДОРХОЙ БАРИМТ/ҮЙЛДЭЛ бич. Хэд хэдэн үйлдэл,
  шалтгаан, нөхцлийг нэг урт, төвөгтэй өгүүлбэрт бүү шахаж хол. Хэрэв эх
  текст дэх санаа нарийн төвөгтэй бол 2-3 БОГИНО, ТОДОРХОЙ өгүүлбэрт
  задалж бич — урт бөгөөд ойлгомжгүй нэг өгүүлбэрээс богино, тодорхой
  хэд хэдэн өгүүлбэр илүү дээр.
- Өгүүлбэр бичихийн өмнө өөрөөсөө асуу: "Энэ өгүүлбэрийг Монгол хүн нэг
  удаа уншаад шууд ойлгох уу?" Хэрэв эргэлзвэл богиносгож, энгийн бол.
- БАРИМТЫГ АЛДАЖ БОЛОХГҮЙ: цаг агаарын үзэгдэл (үер/тайфун/аянга гэх
  мэт), тоо, нэр, газар зэргийг эх текстээс яг зөв, өөрчлөлтгүй авч
  орчуул. Тодорхойгүй бол ойролцоо биш, хамгийн үнэн зөв нэр томьёог
  ашигла.
- СТАТИСТИК, ТОО БАРИМТЫГ ЗААВАЛ ОРУУЛ: хэрэв эх мэдээлэлд тоглолтын
  оноо, гол/оноо тоо, хувь хэмжээ, мөнгөн дүн, он сар өдөр, статистик
  үзүүлэлт зэрэг АЛЬ Ч тоо баримт байвал — эдгээрийг ЗААВАЛ, тодорхой
  оруул. Уншигчид хамгийн их сонирхдог зүйл бол яг ийм нарийн тоо
  баримт (жишээ: "3-1 тоглолт хожив", "25 оноо авав", "хагас цагт 2
  гол оруулав") юм. Хэрэв эх мэдээлэлд тоо баримт байхгүй бол зохиож
  бүү нэм — зөвхөн байгаа бол чухалчлан харуул гэсэн үг.
- ТОДОРХОЙГҮЙ/ТЕХНИК СЭДВИЙГ ТАЙЛБАРЛАЖ ОЙЛГОМЖТОЙ БОЛГО: хэрэв эх
  мэдээлэл шинжлэх ухаан, судалгаа, техник зэрэг ойлгоход хэцүү
  сэдэвтэй бол, ЗӨВХӨН эх текстийг шууд орчуулаад орхихгүй — "энэ нь
  юу гэсэн үг вэ", "энэ яагаад чухал вэ" гэдгийг НЭГ нэмэлт өгүүлбэрээр
  энгийн, амьдралын жишээгээр тайлбарла. Жишээ нь "судалгаагаар X
  илэрсэн" гэхээс илүү, "X илэрсэн нь Y гэсэн үг" гэж тодруул. Эх
  мэдээлэлд байхгүй тайлбарыг зохиож болохгүй — зөвхөн эх дэх
  мэдээллийг илүү ойлгомжтой байдлаар дахин найруулж бич."""

    extra_parts = []
    if news.get("og_description"):
        extra_parts.append(f"Товч тайлбар (эх сайтын og:description): {news['og_description']}")
    if news.get("body_excerpt"):
        extra_parts.append(f"Өгүүллийн эхний хэсгийн бодит текст: {news['body_excerpt']}")
    # ЯАГААД: RSS-ийн summary ганцаараа ихэвчлэн 1 өгүүлбэр (эсвэл хоосон)
    # байдаг тул шинжилгээт мэдээнд (жишээ: "6 баг өрсөлдөж байна") Gemini
    # ямар ч нарийн зүйл (баг нэрс, тоо баримт) бичих материалгүй болдог
    # байсан. Эх хуудаснаас татсан нэмэлт текст үүнийг шийднэ.
    extra_block = ("\n" + "\n".join(extra_parts) + "\n") if extra_parts else ""

    user_prompt = f"""МЭДЭЭЛЭЛ:
Гарчиг: {news['title']}
Агуулга: {news.get('summary', '')}
{extra_block}
Дээрх мэдээллээр Монгол нийтлэл бич. Зөвхөн нийтлэлийн текстийг бич,
өөр юу ч бүү нэм."""

    # 1. ҮНДСЭН: Gemini
    if gemini_compare.is_enabled():
        for attempt in range(2):
            article_text = gemini_compare.generate(system_prompt, user_prompt)
            article_text = _clean_output(article_text) if article_text else ""

            if is_valid_mongolian(article_text):
                news["article_mn"] = article_text
                log.info(f"✅ Gemini нийтлэл OK (оролдлого {attempt+1}): {article_text[:60]}...")
                return news

            log.warning(f"Gemini гаралт чанаргүй/хоосон (оролдлого {attempt+1}) — дахин оролдоно")

        log.warning("Gemini 2 оролдлого бүтэлгүйтлээ — Qwen (Groq) руу шилжлээ")

    # 2. НӨӨЦ: Qwen (Groq)
    log.info(f"writer.py нөөц загвар: {GROQ_MODEL}")
    article_text = _try_qwen(system_prompt, user_prompt)
    if article_text:
        news["article_mn"] = article_text
        return news

    # 3. ЭЦСИЙН НӨӨЦ: Google Translate
    log.warning("Gemini болон Qwen хоёул бүтэлгүйтлээ — Google Translate руу шилжлээ")
    return _fallback(news)


def _fallback(news: dict) -> dict:
    from modules.translator import translate_to_mongolian
    translated = translate_to_mongolian(news)

    title_mn = translated.get("title_mn", "")
    summary_mn = translated.get("summary_mn", "")
    article = f"{title_mn}\n\n{summary_mn}".strip()

    if is_valid_mongolian(article, min_len=40):
        news["article_mn"] = article
    else:
        log.error("Орчуулга бүрэн бүтэлгүйтлээ — энэ мэдээг алгасна")
        news["article_mn"] = ""

    return news


def filter_relevant_news(news_list: list, max_candidates: int = 20) -> list:
    """
    Groq-д БАГЦААР (нэг л дуудлага) мэдээнүүдийг харуулж, Монгол ерөнхий
    уншигчдад үнэхээр сонирхолтой/ач холбогдолтой зүйлийг сонгуулна.
    Жижиг, сонин бус мэдээг (жишээ: "тоглогч дасгалжуулалтад ирсэн" гэх мэт)
    шүүж хаяна.

    API key байхгүй, алдаа гарах, эсвэл хоосон буцах үед АЮУЛГҮЙ fallback:
    бүх мэдээг хэвээр нь буцаана (систем зогсохгүй, зөвхөн шүүлтүүр алгасна).
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or not news_list:
        return news_list

    candidates = news_list[:max_candidates]
    listing = "\n".join(
        f"{i+1}. [{n.get('category_mn', '')}] {n['title']}"
        for i, n in enumerate(candidates)
    )

    prompt = f"""Доорх мэдээнүүдээс Монгол ерөнхий уншигчдад ҮНЭХЭЭР
сонирхолтой, ач холбогдолтой зүйлийг сонго. Жижиг/өдөр тутмын, сонин
бус мэдээг (жишээ: бэлтгэл, дасгалжуулалт, минорит зочилсон гэх мэт)
хасаарай.

{listing}

ЗӨВХӨН сонгосон дугааруудыг таслалаар (,) тусгаарлан бич.
Тайлбар, өөр текст бүү нэм. Жишээ хариу: 1,3,5"""

    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a news editor selecting the most newsworthy items for a general audience."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 100,
                "reasoning_effort": "none"
            },
            timeout=20
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"].strip()
        indices = [int(x) - 1 for x in re.findall(r"\d+", raw)]
        filtered = [candidates[i] for i in indices if 0 <= i < len(candidates)]

        if filtered:
            log.info(f"Ач холбогдлын шүүлтүүр: {len(candidates)} -> {len(filtered)} мэдээ")
            # Шүүгдээгүй үлдсэн (max_candidates-с гадуурх) мэдээг ард нь хавсаргана
            rest = news_list[max_candidates:]
            return filtered + rest

        log.warning("Шүүлтүүр хоосон буцсан — бүх мэдээг хэвээр үлдээе")
        return news_list

    except Exception as e:
        log.warning(f"Ач холбогдлын шүүлтүүр алдаа: {e} — бүх мэдээг хэвээр үлдээе")
        return news_list


def write_digest(news_list: list) -> str:
    """
    Хэд хэдэн мэдээг НЭГ тойм постонд нэгтгэж бичнэ. Мэдээ бүр тусдаа
    догол мөрт, байгалийн Монгол хэллэгээр. Gemini-г ашиглана (Qwen
    нөөц). Амжилтгүй бол хоосон текст буцаана.
    """
    if not news_list:
        return ""

    items_text = "\n\n".join(
        f"[{n.get('category_mn', '')}] {n['title']}: {n.get('summary', '')[:300]}"
        for n in news_list
    )

    system_prompt = """Чи Монголын мэдээний тойм бичигч. Хэд хэдэн мэдээг
НЭГ тойм постонд нэгтгэж бичнэ.

ЗААВАЛ дагах дүрэм:
- Мэдээ БҮРИЙГ тусдаа догол мөрт (хоосон мөрөөр тусгаарлаж) бич
- Мэдээ бүрийг 1-2 өгүүлбэрт багтаан товч, тодорхой бич
- Тоглогч/хүний/багийн нэрийг Англи (Латин) үсгээр бич, хагас Кирилл
  хагас Латин болгож нэрийг хуваахгүй
- Улс, хотын нэрийг Монгол дуудлагаар
- Байгалийн, чөлөөтэй ярианы хэллэгээр бич — хатуу албан орчуулгаас
  зайлсхий
- Гарчиг, хураангуй тайлбар, hashtag бүү нэм — зөвхөн мэдээ бүрийн
  агуулгыг дараалуулан бич
- Зөвхөн өгөгдсөн баримтыг ашигла, шинэ баримт бүү зохио"""

    user_prompt = f"""Доорх мэдээнүүдийг тус бүрийг тусдаа догол мөрт
нэгтгэн Монгол хэлээр бич:

{items_text}"""

    if gemini_compare.is_enabled():
        text = gemini_compare.generate(system_prompt, user_prompt)
        text = _clean_output(text) if text else ""
        if is_valid_mongolian(text, min_len=60):
            log.info(f"Тойм пост Gemini-ээр бичигдлээ ({len(news_list)} мэдээ)")
            return text

    # Нөөц: Qwen (Groq)
    text = _try_qwen(system_prompt, user_prompt)
    if text:
        return text

    return ""
