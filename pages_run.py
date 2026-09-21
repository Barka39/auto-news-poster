"""
Контент хуудсуудын ажиллуулагч (Сүнсний код, Үдшийн шивнээ).

10 минут тутмын auto_post workflow-ийн доторх алхам: хуудас бүрийн слотын цаг
болсон бол контент үүсгэж постолно. Хуудас бүрийн Page token тусдаа secret-д:
FB_PAGE_ID_<SUFFIX>, FB_ACCESS_TOKEN_<SUFFIX> (tools/fb_page_token.py бүгдийг тавьдаг).
Secret байхгүй хуудсыг алгасна.

  PAGES_FORCE=all       бүх слотыг одоо (Draft Check-д)
  PAGES_FORCE=story     зөвхөн нэг төрөл
  AUTONEWS_DRAFT_DIR    постлохгүй, drafts/-д бичнэ
"""

import logging
import os
import sys
from datetime import datetime

from modules import pages_content as pc
from modules import ledger, telegram_notify
from modules.poster import post_to_all_platforms

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _with_page_env(suffix: str):
    """poster.py FB_PAGE_ID/FB_ACCESS_TOKEN-ийг уншдаг тул тухайн хуудсынхаар түр солино."""
    saved = {k: os.environ.get(k) for k in ("FB_PAGE_ID", "FB_ACCESS_TOKEN", "IG_ACCOUNT_ID")}
    os.environ["FB_PAGE_ID"] = os.environ.get(f"FB_PAGE_ID_{suffix}", "")
    os.environ["FB_ACCESS_TOKEN"] = os.environ.get(f"FB_ACCESS_TOKEN_{suffix}", "")
    os.environ["IG_ACCOUNT_ID"] = os.environ.get(f"IG_ACCOUNT_ID_{suffix}", "")
    return saved


def _restore(saved: dict):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def run() -> int:
    now = datetime.now(pc.UB)
    force = os.environ.get("PAGES_FORCE", "").strip()
    draft = bool(os.environ.get("AUTONEWS_DRAFT_DIR"))
    state = pc.load_state()
    total = 0
    for page, cfg in pc.PAGES.items():
        suffix = cfg["suffix"]
        if not draft and not (os.environ.get(f"FB_PAGE_ID_{suffix}") and os.environ.get(f"FB_ACCESS_TOKEN_{suffix}")):
            log.info(f"[{cfg['name']}] secret алга (FB_PAGE_ID_{suffix}) — алгасав")
            continue
        ps = pc.page_state(state, page)
        due = pc.due_slots(page, ps, now, force)
        if not due:
            continue
        log.info(f"[{cfg['name']}] гарах слот: {due}")
        for slot, kind in due:
            try:
                item = pc.BUILDERS[kind](ps, now)
            except Exception as e:
                log.error(f"[{cfg['name']}] {kind} үүсгэхэд алдаа: {e}")
                continue
            if not item:
                log.warning(f"[{cfg['name']}] {kind}: контент үүссэнгүй")
                continue
            post = pc.compose_post(page, item)
            post["hashtag_footer"] = ""   # poster-ийн #МонголМэдээ footer-ийг хаана (hashtag текстэнд орсон)
            post["kind"] = f"page_{kind}"
            saved = _with_page_env(suffix)
            try:
                result = post_to_all_platforms(post)
            finally:
                _restore(saved)
            if result.get("success"):
                pc.mark_posted(ps, now, slot)
                pc.remember(ps, item["title"])
                post["category"] = page
                ledger.record(post, result, {"page": page})
                total += 1
                log.info(f"✅ [{cfg['name']}] {kind} ({slot}): {item['title'][:60]}")
                if not draft:
                    telegram_notify.notify_posted({**post, "category_mn": cfg["name"]}, True)
            else:
                log.warning(f"⚠️ [{cfg['name']}] {kind} постлоход алдаа: {result.get('error')}")
                if not draft:
                    telegram_notify.notify_posted({**post, "category_mn": cfg["name"]}, False, result.get("error") or "")
    pc.save_state(state)
    log.info(f"=== Контент хуудсууд: {total} пост ===")
    return 0


if __name__ == "__main__":
    sys.exit(run())
