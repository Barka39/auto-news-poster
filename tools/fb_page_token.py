"""
Facebook Page token-ийг ХУГАЦААГҮЙ болгож GitHub secret-д тавих туслах.

Яагаад хэрэгтэй вэ: Graph API Explorer-ийн өгдөг USER token 1-2 цаг,
"Extend" дарсан ч 60 хоног л амьдардаг. 2026-09-07-нд яг ийм 60 хоногийн
user token дуусаж 2 долоо хоног пост зогссон. Харин ТЭР УРТ user token-оор
/me/accounts-оос авсан PAGE token хугацаагүй (нууц үг солих, эрх хураахаас
бусад тохиолдолд) — энэ скрипт яг түүнийг авч secret-д тавина.

Хэрэглэх (энэ машин дээр, gh нэвтэрсэн байх):
    1. developers.facebook.com/tools/explorer → App сонгох →
       permissions: pages_manage_posts, pages_read_engagement,
       instagram_basic, instagram_content_publish → Generate Access Token
    2. Тэр хуудасны ⓘ (Access Token Debugger) → "Extend Access Token"
       → гарч ирсэн УРТ token-ийг хуулах
    3. python tools/fb_page_token.py   (token-ийг нууцаар асууна, дэлгэцэнд
       харагдахгүй, файлд хадгалахгүй)
Скрипт: page-уудыг жагсааж → сонгуулж → тухайн page token-ийн хугацааг
debug_token-оор шалгаад → хугацаагүй бол `gh secret set FB_ACCESS_TOKEN`
хийж → workflow-г нэг удаа гараар ажиллуулна.
"""

import getpass
import subprocess
import sys

import requests

GRAPH = "https://graph.facebook.com/v19.0"
REPO = "Barka39/auto-news-poster"


def main() -> int:
    user_token = ""
    if "--clipboard" in sys.argv:
        # Debugger дээр Extend хийсэн token-ийг Copy дарсны дараа .bat давхар товшиход
        # clipboard-оос уншина — гараар paste хийх шаардлагагүй.
        cp = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                            capture_output=True, text=True)
        user_token = (cp.stdout or "").strip()
        if not user_token.startswith("EAA") or len(user_token) < 80:
            print("Clipboard-д Facebook token алга. Debugger дээр сунгасан token-ийг Copy дараад дахин ажиллуул.")
            return 1
        print(f"Clipboard-оос token авлаа ({user_token[:8]}..., {len(user_token)} тэмдэгт)")
    if not user_token:
        user_token = getpass.getpass("Extend хийсэн user token (харагдахгүй): ").strip()
    if not user_token:
        print("Token хоосон байна."); return 1

    r = requests.get(f"{GRAPH}/me/accounts",
                     params={"access_token": user_token, "fields": "id,name,access_token"},
                     timeout=20)
    data = r.json()
    if "error" in data:
        print("Graph алдаа:", data["error"].get("message")); return 1
    pages = data.get("data", [])
    if not pages:
        print("Энэ token-д ямар ч Page харагдахгүй — pages_manage_posts эрх өгсөн эсэхээ шалга."); return 1

    for i, p in enumerate(pages, 1):
        print(f"  {i}. {p['name']}  (id {p['id']})")
    choice = "1" if len(pages) == 1 else (input("Аль page? [1]: ").strip() or "1")
    page = pages[int(choice) - 1]
    page_token = page["access_token"]

    # Хугацааг шалгах: expires_at == 0 гэдэг нь хугацаагүй
    d = requests.get(f"{GRAPH}/debug_token",
                     params={"input_token": page_token, "access_token": page_token},
                     timeout=20).json().get("data", {})
    expires_at = d.get("expires_at")
    if expires_at is None:
        print("⚠️ Хугацааг шалгаж чадсангүй — гэсэн ч үргэлжлүүлнэ.")
    elif expires_at != 0:
        print(f"❌ Энэ page token хугацаатай байна (expires_at={expires_at}).")
        print("   Graph Explorer-ийн Access Token Debugger дээр \"Extend Access Token\" дараад")
        print("   тэр УРТ user token-оор дахин ажиллуул — тэгвэл page token хугацаагүй гарна.")
        return 1
    else:
        print("✅ Page token хугацаагүй (expires_at=0).")

    subprocess.run(["gh", "secret", "set", "FB_ACCESS_TOKEN", "-R", REPO],
                   input=page_token, text=True, check=True)
    subprocess.run(["gh", "secret", "set", "FB_PAGE_ID", "-R", REPO],
                   input=page["id"], text=True, check=True)
    print(f"✅ GitHub secret шинэчлэгдлээ: FB_ACCESS_TOKEN, FB_PAGE_ID={page['id']}")

    subprocess.run(["gh", "workflow", "run", "auto_post.yml", "-R", REPO], check=True)
    print("▶ Auto News Poster workflow-г гараар эхлүүллээ. 2-3 минутын дараа:")
    print(f"   gh run list -R {REPO} --limit 1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
