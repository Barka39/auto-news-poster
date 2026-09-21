# 📰 Auto News Poster — Монгол мэдээ автомат постлогч

Дэлхийн том мэдээний сайтуудаас мэдээ татаж, Монгол хэлрүү орчуулаад
Facebook, Instagram, X (Twitter)-д автоматаар постолдог систем.

## Чиглэлүүд (2026-09-21-ээс)
- 🏀 **NBA** — ESPN, Yahoo, CBS Sports RSS + ESPN scoreboard-оос дууссан тоглолт бүрийн үр дүн
  (оноо, W-L, шилдэг тоглогчдын stat line — RSS-ээс өмнө, шүүлтүүр давахгүй)
- 🇲🇳🏀 **Монголын сагсан бөмбөг** — 24tsag.mn спортын ангилал (RSS-гүй тул HTML жагсаалт,
  огноог нийтлэлийн meta-аас), ikon.mn RSS; зөвхөн "сагс/3x3/NBA/MBA" түлхүүр үгтэй мэдээ
- Хөл бөмбөг, UFC хасагдсан.

### Чанарын 4 хөшүүрэг
1. **Ач холбогдлын ОНОО** (`writer.score_news`): мэдээ бүрд 0-10, `MIN_NEWS_SCORE` (анхдагч 7)-оос
   доош постлогдохгүй. Preview, тойм, podcast, NCAA/WNBA/G-League, сагстай холбоогүй = 0-4.
   Groq → Gemini нөөц; хоёулаа унавал тэр run-д ЮУ Ч постлохгүй (сул пост гаргахаас дээр).
2. **Редакторын хоёр дахь дамжлага** (`writer.polish_article`): эх баримт + ноорог → баримт
   тулгалт, нэрийн Латин дүрэм, hook эхлэл, байгалийн хэл, 400-700 тэмдэгт.
3. **Бүтэн материал**: нийтлэлийн og:description + body (ESPN бол API-ийн story).
4. **Тоглолтын үр дүн өгөгдлөөс** (`modules/nba_scores.py`): хэн ч бичээгүй, баримтаар дүүрэн recap.

### Чанарыг постлохгүйгээр шалгах
Actions → **Draft Check (постлохгүй)** → Run workflow (max_posts, min_score, тестийн NBA огноо).
Нооргууд log-д бүтнээрээ хэвлэгдэнэ, `drafts` artifact болж хадгалагдана.
Endpoint хаагдсан эсэхийг **Probe endpoints** workflow-оор шалгана (ESPN-ийн `site.api` хост
Actions-оос 403 болсон тул `site.web.api.espn.com` хэрэглэж байгаа; `ESPN_API_HOST`-оор солино).

## Хуучин чиглэлүүд
- ⚽ **Спорт** — ESPN, BBC Sport
- 🎵 **Хөгжим & Холливүүд** — Billboard, Rolling Stone, TMZ
- 🌍 **Дэлхийн мэдээ** — Reuters, BBC World, AP News

---

## Тохируулах заавар

### 1. GitHub Repository үүсгэх
1. github.com → New repository
2. Нэр: `auto-news-poster`
3. **Private** сонгох
4. Энэ файлуудыг upload хийх

### 2. GitHub Secrets тохируулах
Repository → Settings → Secrets and variables → Actions → New repository secret

Дараах secrets нэмнэ:

| Secret нэр | Утга | Хаанаас авах |
|-----------|------|-------------|
| `ANTHROPIC_API_KEY` | sk-ant-... | console.anthropic.com |
| `FB_PAGE_ID` | 123456789 | FB Page Settings |
| `FB_ACCESS_TOKEN` | EAAx... | Meta Graph Explorer |
| `IG_ACCOUNT_ID` | 987654321 | FB Business Settings |
| `X_API_KEY` | abc... | developer.twitter.com |
| `X_API_SECRET` | def... | developer.twitter.com |
| `X_ACCESS_TOKEN` | 123-... | developer.twitter.com |
| `X_ACCESS_SECRET` | xyz... | developer.twitter.com |

### 3. Anthropic API Key авах
1. console.anthropic.com → бүртгэл нээх
2. API Keys → Create Key
3. $5 credit нэмэх (1-2 сарын хэрэгцээ)

### 4. Facebook/Instagram API тохируулах
1. developers.facebook.com → My Apps → Create App → Business
2. Graph API Explorer → Page token авах
3. Permissions: `pages_manage_posts`, `instagram_content_publish`

### 4a. ⚠ Facebook token ХУГАЦААГҮЙ болгох (2026-09 сургамж)
Graph Explorer-ийн user token 1-2 цаг, "Extend" дарсан ч **60 хоног** л ажиллана —
2026-09-07-нд яг ийм token дуусаж 2 долоо хоног пост зогссон. Хугацаагүй нь
зөвхөн **урт user token-оор /me/accounts-оос авсан PAGE token**. Үүнийг нэг
командаар хийдэг туслах бий (token дэлгэцэнд харагдахгүй, файлд үлдэхгүй):

```
python tools/fb_page_token.py
```

Token дуусвал одоо: run улаан болно, Telegram-д 🛑 шалтгаантай нь ирнэ (12 цаг
тутам нэг), Gemini/Groq-ийн эрх үрэгдэхгүй.

**Groq загвар** дуусвал (`404 Not Found`): repo Settings → Secrets → `GROQ_MODEL`
secret нэмээд шинэ загварын нэрийг тавьж болно (код өөрчлөх шаардлагагүй;
анхдагч `qwen/qwen3.8-27b`).

### 5. X Developer тохируулах
1. developer.twitter.com → Apply for access
2. Free tier сонгох
3. App → Keys and Tokens

---

## Ажиллуулах
GitHub Actions автоматаар **30 минут тутамд** ажиллана.

Гараар тест хийхэд:
Repository → Actions → Auto News Poster → Run workflow

---

## Зохиогчийн эрх хамгаалалт
- ✅ Зөвхөн гарчиг + богино хураангуй (300 тэмдэгт) авна
- ✅ Монгол орчуулга = өөрийн бүтээл
- ❌ Бүтэн нийтлэл хуулахгүй
