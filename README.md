# 📰 Auto News Poster — Монгол мэдээ автомат постлогч

Дэлхийн том мэдээний сайтуудаас мэдээ татаж, Монгол хэлрүү орчуулаад
Facebook, Instagram, X (Twitter)-д автоматаар постолдог систем.

## Чиглэлүүд
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
