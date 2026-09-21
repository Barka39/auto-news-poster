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


SUFFIX_BY_NAME = {"сүнсний код": "SUNS", "үдшийн шивнээ": "UDESH"}
import re as _re
NBA_PAGE_RE = _re.compile(r"unuudur|unuurdur|өнөөдөр|onoodor", _re.IGNORECASE)


def _confirm_nba(name: str) -> bool:
    if NBA_PAGE_RE.search(name or ""):
        return True
    ans = input(f"«{name}» — энэ бол САГСНЫ МЭДЭЭНИЙ хуудас (unuudur.mgl) мөн үү? (y/n): ").strip().lower()
    return ans in ("y", "yes", "т", "тийм")


def set_page_secrets(name: str, page_id: str, token: str) -> int:
    """Хуудасны нэрээр secret-ийн нэрийг сонгож gh-ээр тавина; NBA хуудас = үндсэн нэрс."""
    suf = SUFFIX_BY_NAME.get(name.strip().lower())
    if not suf and not _confirm_nba(name):
        print(f"⏭️ «{name}» хуудсыг NBA-д тавьсангүй.")
        return 1
    tok_key, id_key = (f"FB_ACCESS_TOKEN_{suf}", f"FB_PAGE_ID_{suf}") if suf else ("FB_ACCESS_TOKEN", "FB_PAGE_ID")
    subprocess.run(["gh", "secret", "set", tok_key, "-R", REPO], input=token, text=True, check=True)
    subprocess.run(["gh", "secret", "set", id_key, "-R", REPO], input=page_id, text=True, check=True)
    print(f"✅ {name} → {id_key}, {tok_key} тавигдлаа")
    if not suf:
        subprocess.run(["gh", "variable", "set", "NBA_PAGE_ID_EXPECTED", "-R", REPO, "--body", page_id], check=True)
        subprocess.run(["gh", "workflow", "run", "auto_post.yml", "-R", REPO], check=True)
        print("▶ Auto News Poster workflow-г эхлүүллээ")
    return 0


def main() -> int:
    user_token = ""
    if "--clipboard" in sys.argv:
        # Debugger дээр Extend хийсэн token-ийг Copy дарсны дараа .bat давхар товшиход
        # clipboard-оос уншина — гараар paste хийх шаардлагагүй.
        cp = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                            capture_output=True, text=True)
        user_token = (cp.stdout or "").strip()
        if not user_token.startswith("EAA") or len(user_token) < 80:
            print("Clipboard-д Facebook token алга (EAA... гэж эхлэх ёстой).")
            user_token = ""
        else:
            print(f"Clipboard-оос token авлаа ({user_token[:8]}..., {len(user_token)} тэмдэгт)")
    if not user_token:
        user_token = getpass.getpass("Token-оо энд paste хийгээд Enter дар (дэлгэцэнд харагдахгүй): ").strip()
    if not user_token:
        print("Token хоосон байна."); return 1

    r = requests.get(f"{GRAPH}/me/accounts",
                     params={"access_token": user_token, "fields": "id,name,access_token"},
                     timeout=20)
    data = r.json()
    pages = data.get("data", []) if "error" not in data else []

    if not pages:
        # PAGE TOKEN шууд өгсөн тохиолдол (Graph Explorer-ийн "Page" сонголтоор авсан, Extend хийсэн):
        # /me нь тухайн хуудсыг өөрийг нь буцаана → нэрээр нь таньж secret-д тавина.
        me = requests.get(f"{GRAPH}/me", params={"access_token": user_token, "fields": "id,name"}, timeout=20).json()
        if "error" in me:
            print("Graph алдаа:", me["error"].get("message")); return 1
        d2 = requests.get(f"{GRAPH}/debug_token", params={"input_token": user_token, "access_token": user_token},
                          timeout=20).json().get("data", {})
        exp = d2.get("expires_at")
        print(f"Page token: {me.get('name')} (id {me.get('id')}), хугацаа: {'хугацаагүй ✅' if exp == 0 else exp}")
        if exp not in (0, None):
            print("❌ Энэ token хугацаатай байна — Debugger дээр \"Extend Access Token\" дараад сунгасныг нь хуул.")
            return 1
        return set_page_secrets(me.get("name", ""), me.get("id", ""), user_token)

    for i, p in enumerate(pages, 1):
        print(f"  {i}. {p['name']}  (id {p['id']})")

    # Контент хуудсууд: нэрээр таньж тусдаа secret-д (FB_PAGE_ID_SUNS г.м.)
    SUFFIX_BY_NAME = {"сүнсний код": "SUNS", "үдшийн шивнээ": "UDESH"}
    for p in pages:
        suf = SUFFIX_BY_NAME.get(p["name"].strip().lower())
        if not suf:
            continue
        d2 = requests.get(f"{GRAPH}/debug_token", params={"input_token": p["access_token"], "access_token": p["access_token"]},
                          timeout=20).json().get("data", {})
        if d2.get("expires_at") not in (0, None):
            print(f"❌ {p['name']}: page token хугацаатай — сунгасан user token-оор дахин ажиллуул."); continue
        subprocess.run(["gh", "secret", "set", f"FB_ACCESS_TOKEN_{suf}", "-R", REPO], input=p["access_token"], text=True, check=True)
        subprocess.run(["gh", "secret", "set", f"FB_PAGE_ID_{suf}", "-R", REPO], input=p["id"], text=True, check=True)
        print(f"✅ {p['name']} → FB_PAGE_ID_{suf}, FB_ACCESS_TOKEN_{suf}")

    main_pages = [p for p in pages if NBA_PAGE_RE.search(p["name"] or "")]
    if not main_pages:
        others = [p for p in pages if p["name"].strip().lower() not in SUFFIX_BY_NAME]
        if others:
            print("Сагсны мэдээний (unuudur.mgl) хуудас аль нь вэ? 0 = аль нь ч биш")
            for i, p in enumerate(others, 1):
                print(f"  {i}. {p['name']}")
            ans = input("Дугаар: ").strip()
            if ans.isdigit() and 1 <= int(ans) <= len(others):
                main_pages = [others[int(ans) - 1]]
    if not main_pages:
        print("⚠️ unuudur.mgl (сагсны) хуудас энэ token-д алга. Graph Explorer-т Generate Access Token дарахад гарах")
        print("   Facebook-ийн цонхонд «Edit settings / Бүх хуудас» сонгож unuudur.mgl-ийг ЧАГТАЛНА уу.")
        print("   Контент хуудсуудыг тохируулсан; NBA-ийн тохиргоонд хүрсэнгүй."); return 0
    page = main_pages[0]
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
    subprocess.run(["gh", "variable", "set", "NBA_PAGE_ID_EXPECTED", "-R", REPO, "--body", page["id"]], check=True)
    print(f"✅ GitHub secret шинэчлэгдлээ: FB_ACCESS_TOKEN, FB_PAGE_ID={page['id']} ({page['name']})")

    subprocess.run(["gh", "workflow", "run", "auto_post.yml", "-R", REPO], check=True)
    print("▶ Auto News Poster workflow-г гараар эхлүүллээ. 2-3 минутын дараа:")
    print(f"   gh run list -R {REPO} --limit 1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
