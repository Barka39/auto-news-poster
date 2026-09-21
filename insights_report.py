"""
Хэмжилтийн гогцоо (S3): ledger.json дахь пост бүрийн Facebook insights-ийг
татаж хадгална, долоо хоног бүр Telegram-д тайлан илгээнэ.

  python insights_report.py            # 24ц-аас хуучин, insights-гүй постуудыг татна
  python insights_report.py --report   # + долоо хоногийн тайлан (Даваа)
  python insights_report.py --backfill # ledger-т байхгүй сүүлийн 25 постыг page-ээс нэмнэ

Хэмжүүр: post_impressions_unique (reach), post_clicks, reactions (fields),
shares, comments. Эрх: pages_read_engagement (бий).
"""

import logging
import os
import sys
import time
from collections import defaultdict

import requests

from modules import ledger, telegram_notify

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

G = "https://graph.facebook.com/" + os.environ.get("FB_API_VERSION", "v21.0")
TOKEN = os.environ.get("FB_ACCESS_TOKEN", "")
PAGE = os.environ.get("FB_PAGE_ID", "")


def _get(path: str, **params) -> dict:
    params["access_token"] = TOKEN
    r = requests.get(f"{G}/{path}", params=params, timeout=20)
    return r.json()


def fetch_post_metrics(post_id: str) -> dict | None:
    out = {}
    # Meta 2024-2025-д олон post metric-ийг хассан → боломжит багцуудыг дарааллаар оролдоно
    d = None
    for metrics in ("post_impressions_unique,post_clicks", "post_impressions_unique", "post_impressions"):
        d = _get(f"{post_id}/insights", metric=metrics)
        if "error" not in d:
            break
    if not d or "error" in d:
        log.warning(f"insights алдаа {post_id}: {(d or {}).get('error', {}).get('message')}")
        return None
    for m in d.get("data", []):
        vals = m.get("values") or [{}]
        out[m["name"].replace("post_", "")] = vals[0].get("value", 0)
    if "impressions_unique" not in out and "impressions" in out:
        out["impressions_unique"] = out["impressions"]
    f = _get(post_id, fields="reactions.summary(true).limit(0),comments.summary(true).limit(0),shares")
    if "error" not in f:
        out["reactions"] = (f.get("reactions") or {}).get("summary", {}).get("total_count", 0)
        out["comments"] = (f.get("comments") or {}).get("summary", {}).get("total_count", 0)
        out["shares"] = (f.get("shares") or {}).get("count", 0)
    out["fetched_at"] = time.time()
    return out


def update_metrics(min_age_h: float = 24, max_posts: int = 40) -> int:
    posts = ledger.load()
    now = time.time()
    n = 0
    for p in posts:
        pid = p.get("fb_id")
        if not pid or "_" not in str(pid):
            continue
        age_h = (now - p.get("ts", 0)) / 3600
        have = p.get("m24") if age_h < 7 * 24 else p.get("m7d")
        if age_h < min_age_h or have:
            continue
        m = fetch_post_metrics(pid)
        if m is None:
            continue
        key = "m7d" if age_h >= 7 * 24 else "m24"
        p[key] = m
        n += 1
        if n >= max_posts:
            break
    ledger.save(posts)
    log.info(f"insights шинэчлэв: {n} пост")
    return n


def backfill(limit: int = 25) -> int:
    """Ledger-ээс өмнөх постуудыг page-ийн feed-ээс нэмнэ (kind=unknown)."""
    posts = ledger.load()
    known = {p.get("fb_id") for p in posts}
    d = _get(f"{PAGE}/posts", fields="id,created_time,message", limit=limit)
    added = 0
    for item in d.get("data", []):
        if item["id"] in known:
            continue
        from datetime import datetime
        ts = datetime.fromisoformat(item["created_time"].replace("+0000", "+00:00")).timestamp()
        msg = (item.get("message") or "")[:120]
        kind = "digest" if "ӨГЛӨӨНИЙ NBA" in msg else ("mn" if "МОНГОЛЫН САГС" in msg.upper() else "unknown")
        posts.append({"ts": ts, "fb_id": item["id"], "kind": kind, "card": "", "score": 0,
                      "category": "", "source": "backfill", "title": msg, "url": "", "slot": ""})
        added += 1
    posts.sort(key=lambda p: p.get("ts", 0))
    ledger.save(posts)
    log.info(f"backfill: {added} пост нэмэв")
    return added


def weekly_report() -> str:
    posts = ledger.load()
    now = time.time()
    week = [p for p in posts if now - p.get("ts", 0) <= 7 * 24 * 3600 and (p.get("m24") or p.get("m7d"))]
    if not week:
        return "📊 Долоо хоногийн тайлан: хэмжилттэй пост алга (insights хараахан ирээгүй)."

    def reach(p):
        m = p.get("m7d") or p.get("m24") or {}
        return m.get("impressions_unique", 0)

    def eng(p):
        m = p.get("m7d") or p.get("m24") or {}
        return m.get("reactions", 0) + m.get("comments", 0) * 3 + m.get("shares", 0) * 5

    by_kind = defaultdict(list)
    by_slot = defaultdict(list)
    for p in week:
        by_kind[p.get("kind") or "news"].append(p)
        hour = time.strftime("%H", time.gmtime(p.get("ts", 0) + 8 * 3600))
        by_slot[hour + ":00"].append(p)
    lines = [f"📊 Долоо хоногийн тайлан ({len(week)} пост, reach нийт {sum(reach(p) for p in week):,})", ""]
    lines.append("Төрлөөр (дундаж reach / engagement):")
    for k, ps in sorted(by_kind.items(), key=lambda kv: -sum(reach(p) for p in kv[1]) / len(kv[1])):
        lines.append(f"  • {k}: {sum(reach(p) for p in ps) / len(ps):,.0f} / {sum(eng(p) for p in ps) / len(ps):.1f}  (n={len(ps)})")
    lines.append("")
    top = sorted(week, key=reach, reverse=True)
    lines.append("Шилдэг 3:")
    for p in top[:3]:
        lines.append(f"  ✅ {reach(p):,} — {p.get('title', '')[:60]}")
    lines.append("Сул 3:")
    for p in top[-3:]:
        lines.append(f"  ⚠️ {reach(p):,} — {p.get('title', '')[:60]}")
    lines.append("")
    lines.append("Цагаар (УБ, дундаж reach):")
    for h, ps in sorted(by_slot.items()):
        lines.append(f"  {h}: {sum(reach(p) for p in ps) / len(ps):,.0f} (n={len(ps)})")
    return "\n".join(lines)


def probe_metrics():
    """Аль post metric энэ page/API хувилбарт хүчинтэйг нэг постоор шалгаж хэвлэнэ."""
    d = _get(f"{PAGE}/posts", fields="id", limit=1)
    pid = (d.get("data") or [{}])[0].get("id")
    if not pid:
        print("probe: пост алга", d); return
    cands = ["post_impressions", "post_impressions_unique", "post_impressions_organic", "post_impressions_paid",
             "post_clicks", "post_reactions_by_type_total", "post_reactions_like_total", "post_activity_by_action_type",
             "post_engaged_users", "post_video_views", "post_impressions_viral"]
    ok = []
    for m in cands:
        r = _get(f"{pid}/insights", metric=m)
        status = "OK" if "error" not in r else r["error"].get("message", "")[:60]
        print(f"  {m}: {status}")
        if "error" not in r:
            ok.append(m)
    f = _get(pid, fields="reactions.summary(true).limit(0),comments.summary(true).limit(0),shares,insights.metric(post_impressions_unique)")
    print("  fields:", {k: (v if k != 'insights' else 'ok') for k, v in f.items() if k != 'id'} if "error" not in f else f["error"].get("message"))
    print("VALID:", ",".join(ok))


if __name__ == "__main__":
    if not TOKEN:
        log.error("FB_ACCESS_TOKEN алга")
        sys.exit(1)
    if "--probe" in sys.argv:
        probe_metrics()
        sys.exit(0)
    if "--backfill" in sys.argv:
        backfill()
    update_metrics()
    if "--report" in sys.argv:
        text = weekly_report()
        print(text)
        if telegram_notify.is_enabled():
            try:
                requests.post(telegram_notify.TELEGRAM_API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method="sendMessage"),
                              json={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:3900]}, timeout=15)
                log.info("Telegram тайлан илгээв")
            except Exception as e:
                log.warning(f"Telegram тайлан алдаа: {e}")
