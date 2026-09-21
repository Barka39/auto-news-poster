"""
Бичлэг (S9): тоглолтын үр дүнгээс 1080×1920 босоо видео — өөрийн график
(recap картын элементүүд хөдөлгөөнтэй) + Монгол хэлний хоолой (edge-tts,
mn-MN-BataaNeural) + хадмал. NBA-ийн бодит бичлэг ашиглахгүй (зохиогчийн эрх).

Дамжлага: HTML темплэйт (window.setT(t) — 0..1 хугацааны хувь) → Playwright
кадр бүрийг screenshot → ffmpeg (Actions runner дээр бэлэн) → mp4 (H.264/AAC).
Хадмал: хоолойн текстийг өгүүлбэрээр хувааж, нийт хугацаанд тэмдэгтийн тоогоор
хуваарилна (edge-tts-ийн Монгол хоолой WordBoundary өгдөггүй).

Юу ч унавал "" буцаана → зурагтай пост хэвээр гарна.
"""

import asyncio
import base64
import html
import logging
import os
import re
import shutil
import subprocess
import tempfile

from modules import cards

log = logging.getLogger(__name__)

W, H = 1080, 1920
FPS = int(os.environ.get("VIDEO_FPS", "24"))
VOICE = os.environ.get("TTS_VOICE", "mn-MN-BataaNeural")
FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")


def enabled() -> bool:
    return os.environ.get("VIDEO_RECAPS", "1") != "0" and shutil.which(FFMPEG) is not None


# ============================================================
# ХООЛОЙ
# ============================================================
def tts_script(text: str) -> str:
    """Уншуулах текст: оноог '130 120' биш '130 : 120' гэж; hashtag хасна; 3 өгүүлбэр."""
    t = re.sub(r"#\S+", "", text or "")
    t = re.sub(r"(\d+)\s*[-:]\s*(\d+)", r"\1 : \2", t)          # 130-120 → 130 : 120 (хасах гэж уншихгүй)
    t = re.sub(r"\s+", " ", t).strip()
    sents = re.split(r"(?<=[.!?])\s+", t)
    return " ".join(sents[:3]).strip()


def synthesize(text: str, out_mp3: str) -> float:
    """edge-tts → mp3; секундээр урт (ffprobe). Алдаа бол 0."""
    try:
        import edge_tts

        async def _run():
            await edge_tts.Communicate(text, VOICE).save(out_mp3)
        asyncio.run(_run())
        probe = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1", out_mp3],
                               capture_output=True, text=True, timeout=30)
        return float(probe.stdout.strip() or 0)
    except Exception as e:
        log.warning(f"[VIDEO] TTS алдаа: {e}")
        return 0.0


def caption_timeline(text: str, total: float) -> list:
    """[(start, end, sentence)] — тэмдэгтийн тоогоор пропорциональ."""
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    n = sum(len(s) for s in sents) or 1
    out, t = [], 0.0
    for s in sents:
        d = total * len(s) / n
        out.append((t, t + d, s))
        t += d
    return out


# ============================================================
# ТЕМПЛЭЙТ (босоо recap)
# ============================================================
def _recap_html(card: dict, captions: list, total: float) -> str:
    h, a = card["home"], card["away"]
    stars = ""
    for i, p in enumerate((card.get("leaders") or [])[:2]):
        stats = "".join(f"<span><small>{cards._e(l)}</small>{cards._e(v)}</span>" for l, v in p.get("stats", [])[:2])
        img = f"<img src='{cards._e(p['headshot'])}'>" if p.get("headshot") else ""
        stars += f"<div class='star glass' id='star{i}'>{img}<div><div class='n'>{cards._e(p['name'])}</div><div class='t'>{cards._e(p.get('team', ''))}</div><div class='s'>{stats}</div></div></div>"
    caps_js = ",".join(f"[{s:.3f},{e:.3f},{html.escape(txt, quote=True)!r}]".replace("'", '"') for s, e, txt in captions)
    css = f"""
body{{background:#000}}
.card{{width:{W}px;height:{H}px;background:linear-gradient(115deg,#{a['color']} 0 50%,#{h['color']} 50% 100%)}}
.card:before{{content:"";position:absolute;inset:0;background:
  radial-gradient(1000px 700px at 20% 15%,rgba(255,255,255,.18),transparent 60%),
  radial-gradient(1000px 700px at 80% 90%,rgba(255,255,255,.14),transparent 60%),
  linear-gradient(180deg,rgba(0,0,0,0) 60%,rgba(0,0,0,.6) 100%)}}
.top{{position:absolute;top:80px;left:70px;right:70px;display:flex;justify-content:space-between;align-items:center}}
.date{{font-weight:600;font-size:30px;opacity:.9}}
.teams{{position:absolute;top:260px;left:0;right:0;display:flex;justify-content:space-around;align-items:flex-start}}
.team{{display:flex;flex-direction:column;align-items:center;width:480px;transition:none}}
.team img{{width:340px;height:340px;object-fit:contain;filter:drop-shadow(0 20px 30px rgba(0,0,0,.45))}}
.team .name{{font-weight:800;font-size:{38 if max(len(h['name']), len(a['name'])) <= 18 else 32}px;margin-top:14px;text-align:center;line-height:1.1;min-height:80px;display:flex;align-items:flex-end}}
.team .rec{{font-weight:600;font-size:28px;opacity:.85}}
.score{{position:absolute;top:820px;left:0;right:0;text-align:center;font-weight:900;font-size:210px;line-height:1;letter-spacing:-4px;text-shadow:0 12px 40px rgba(0,0,0,.4)}}
.final{{position:absolute;top:1040px;left:0;right:0;text-align:center;font-weight:800;font-size:34px;letter-spacing:6px;opacity:.9}}
.stars{{position:absolute;top:1130px;left:70px;right:70px;display:flex;flex-direction:column;gap:24px}}
.star{{padding:22px 26px;display:flex;align-items:center;gap:22px;min-height:200px}}
.star img{{width:150px;height:150px;border-radius:50%;object-fit:cover;object-position:top;background:#fff;flex:none}}
.star .n{{font-weight:800;font-size:36px;line-height:1.05}}
.star .t{{font-weight:600;font-size:22px;opacity:.8;margin-top:4px}}
.star .s{{font-weight:900;font-size:46px;margin-top:8px}}
.star .s small{{font-size:18px;font-weight:600;opacity:.85;margin-right:8px}} .star .s span{{white-space:nowrap;margin-right:16px}}
.cap{{position:absolute;left:60px;right:60px;bottom:150px;text-align:center;font-weight:800;font-size:40px;line-height:1.25;
  background:rgba(0,0,0,.55);border-radius:20px;padding:22px 28px;min-height:120px;opacity:0}}
.foot{{bottom:60px;font-size:26px}}
"""
    body = f"""<div class='card'>
<div class='top'><span class='badge light'>NBA · {cards._e(card.get('stage', 'УЛИРЛЫН ТОГЛОЛТ'))}</span><span class='date'>{cards._e(card.get('date', ''))}</span></div>
<div class='teams'>
 <div class='team' id='ta'><img src='{cards._e(a['logo'])}'><div class='name'>{cards._e(a['name'])}</div><div class='rec'>{cards._e(a.get('record', ''))}</div></div>
 <div class='team' id='th'><img src='{cards._e(h['logo'])}'><div class='name'>{cards._e(h['name'])}</div><div class='rec'>{cards._e(h.get('record', ''))}</div></div>
</div>
<div class='score' id='score'>0 : 0</div>
<div class='final' id='final'>ТОГЛОЛТ ДУУСЛАА</div>
<div class='stars'>{stars}</div>
<div class='cap' id='cap'></div>
{cards._foot('Эх сурвалж: ESPN')}
</div>
<script>
const A={a['score']}, Hs={h['score']}, TOTAL={total:.3f}, CAPS=[{caps_js}];
const ease=x=>1-Math.pow(1-x,3);
const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
window.setT=function(t){{
  const sec=t*TOTAL;
  // 1) лого 0-1.2с
  const p1=ease(clamp(sec/1.2,0,1));
  document.getElementById('ta').style.transform=`translateX(${{(-600*(1-p1)).toFixed(1)}}px)`;
  document.getElementById('th').style.transform=`translateX(${{(600*(1-p1)).toFixed(1)}}px)`;
  // 2) оноо 1.0-2.6с
  const p2=ease(clamp((sec-1.0)/1.6,0,1));
  document.getElementById('score').textContent=Math.round(A*p2)+' : '+Math.round(Hs*p2);
  document.getElementById('final').style.opacity=clamp((sec-2.4)/0.5,0,1);
  // 3) тоглогчид 2.6с-ээс
  for(let i=0;i<2;i++){{const el=document.getElementById('star'+i); if(!el) continue;
    const p=ease(clamp((sec-2.6-i*0.5)/0.7,0,1)); el.style.opacity=p; el.style.transform=`translateY(${{(80*(1-p)).toFixed(1)}}px)`;}}
  // 4) хадмал
  const cap=document.getElementById('cap'); let txt='';
  for(const c of CAPS){{ if(sec>=c[0]&&sec<c[1]) txt=c[2]; }}
  cap.textContent=txt; cap.style.opacity=txt?1:0;
}};
window.setT(0);
</script>"""
    return cards._wrap(body, css)


# ============================================================
# РЕНДЕР
# ============================================================
def recap_video(card: dict, script: str, out_path: str) -> str:
    """mp4 замыг буцаана; алдаа бол ""."""
    if not enabled():
        log.info("[VIDEO] идэвхгүй (VIDEO_RECAPS=0 эсвэл ffmpeg алга)")
        return ""
    work = tempfile.mkdtemp(prefix="anv_")
    try:
        text = tts_script(script)
        if len(text) < 30:
            return ""
        mp3 = os.path.join(work, "voice.mp3")
        dur = synthesize(text, mp3)
        if dur <= 0:
            return ""
        total = max(10.0, dur + 1.2)
        captions = caption_timeline(text, dur)
        html_doc = _recap_html(card, captions, total)

        browser = cards._get_browser()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        try:
            page.set_content(html_doc, wait_until="load")
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            frames = int(total * FPS)
            for i in range(frames):
                page.evaluate("t => window.setT(t)", i / max(frames - 1, 1))
                page.screenshot(path=os.path.join(work, f"f_{i:05d}.jpg"), type="jpeg", quality=88)
        finally:
            page.close()

        cmd = [FFMPEG, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(work, "f_%05d.jpg"),
               "-i", mp3, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out_path]
        subprocess.run(cmd, check=True, timeout=300)
        size = os.path.getsize(out_path)
        log.info(f"🎬 Recap видео: {total:.1f}с, {frames} кадр, {size // 1024} KB")
        return out_path
    except Exception as e:
        log.warning(f"[VIDEO] алдаа: {e}")
        return ""
    finally:
        shutil.rmtree(work, ignore_errors=True)


def post_video_facebook(path: str, description: str) -> dict:
    """POST /{page-id}/videos (энгийн видео пост)."""
    import requests
    page_id, token = os.environ.get("FB_PAGE_ID"), os.environ.get("FB_ACCESS_TOKEN")
    if not page_id or not token:
        return {"success": False, "error": "FB credentials байхгүй"}
    try:
        with open(path, "rb") as fh:
            r = requests.post(f"https://graph.facebook.com/v19.0/{page_id}/videos",
                              data={"description": description, "access_token": token},
                              files={"source": ("recap.mp4", fh, "video/mp4")}, timeout=180)
        data = r.json()
        if "id" in data:
            log.info(f"✅ Facebook видео: {data['id']}")
            return {"success": True, "id": data["id"]}
        err = data.get("error", {}).get("message", str(data))
        log.error(f"❌ Facebook видео алдаа: {err}")
        return {"success": False, "error": err}
    except Exception as e:
        return {"success": False, "error": str(e)}
