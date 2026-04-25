#!/usr/bin/env python3
"""
Manhwa Recap Pipeline — Solo Leveling
Uses: Pollinations AI (images) + Kokoro TTS via audio_gen.py + FFmpeg
"""

import os, sys, json, time, argparse, subprocess, requests
from pathlib import Path
from urllib.parse import quote

# Import our fixed audio module
from audio_gen import generate_audio

# ── Config ────────────────────────────────────────────────────────
MANGA_TITLE  = "Solo Leveling"
FANDOM_BASE  = "https://solo-leveling.fandom.com/wiki"
POLLINATIONS = "https://image.pollinations.ai/prompt/{prompt}?width={w}&height={h}&seed={seed}&nologo=true&model=flux"
RESOLUTION   = "1280x720"
FONT_PATH    = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
WORK_DIR     = Path("workspace")
SCENES_DIR   = WORK_DIR / "scenes"
AUDIO_DIR    = WORK_DIR / "audio"
OUTPUT_DIR   = Path("output")
BGM_PATH     = Path("bgm/dramatic.mp3")

def setup():
    for d in [WORK_DIR, SCENES_DIR, AUDIO_DIR, OUTPUT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def log(msg, icon="▶"):
    print(f"\n{icon}  {msg}", flush=True)

def get_api_key():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("KEY1") or os.environ.get("KEY2")
    if not key:
        print("❌  Set GEMINI_API_KEY / KEY1 / KEY2"); sys.exit(1)
    return key

# ── Step 1: Fetch plot ────────────────────────────────────────────
BUILTIN_PLOT = """
Solo Leveling Ch1-10: Sung Jinwoo is the weakest E-Rank hunter in Korea, barely
surviving dungeons to support his sick mother. On a D-Rank raid, the team discovers
a hidden double dungeon. Stone statues massacre the group. Jinwoo sacrifices himself
so others escape. Near death, a mysterious System appears and chooses him as its
sole Player, granting him the unique ability to level up — something no hunter has
ever done. He wakes in hospital with his first quest: 100 push-ups, 100 sit-ups,
10km run or die. He completes it and realizes this power is real. He begins grinding
secretly, growing at an impossible rate. The weakest hunter just became something else.
"""

def fetch_wiki_plot(ch_start: int, ch_end: int) -> str:
    log(f"Fetching plot: Ch.{ch_start}-{ch_end}", "📖")
    import re
    urls = [
        f"{FANDOM_BASE}/Story_Arcs",
        "https://en.wikipedia.org/wiki/Solo_Leveling",
    ]
    text = ""
    for url in urls:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                t = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', r.text, flags=re.DOTALL)
                t = re.sub(r'<[^>]+>', ' ', t)
                t = re.sub(r'\s+', ' ', t).strip()
                text += f"\n[{url}]\n{t[:3000]}"
                log(f"Fetched {url}", "✅")
        except Exception as e:
            log(f"Failed {url}: {e}", "⚠️")
    return text if text else BUILTIN_PLOT

# ── Step 2: Gemini generates script ──────────────────────────────
GEMINI_SYSTEM = """
You are a YouTube manhwa recap scriptwriter. Given a plot, return ONLY valid JSON:
{
  "title": "Solo Leveling Ch.X-Y Full Recap",
  "output_filename": "solo_leveling_chX_Y.mp4",
  "scenes": [
    {
      "id": 1,
      "type": "static_bg",
      "background_color": "#000000",
      "overlay_text": "SOLO LEVELING",
      "sub_text": "Chapters X-Y | Full Recap",
      "narration": "Hook narration.",
      "voice": "am_adam",
      "mood": "epic",
      "transition": "fade"
    },
    {
      "id": 2,
      "type": "ai_image",
      "image_prompt": "Korean manhwa art style, webtoon illustration, [scene description], dramatic lighting, high detail",
      "narration": "2-4 sentence storyteller narration. Excited fan tone.",
      "voice": "am_adam",
      "mood": "dramatic",
      "transition": "fade"
    }
  ]
}
Rules:
- First scene: static_bg title card (black, white text)
- Last scene: static_bg cliffhanger/subscribe hook
- ai_image prompts: always include "Korean manhwa art style, webtoon illustration"
- Narration: storyteller voice, NOT dubbing dialogue
- Voices: am_adam (default), af_heart, af_bella, bm_george
- Return ONLY JSON — no markdown, no explanation
"""

def generate_script(plot: str, ch_start: int, ch_end: int, num_scenes: int) -> dict:
    log("Gemini generating script...", "🤖")
    key = get_api_key()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
    prompt = f"Plot: {plot[:5000]}\n\nWrite a {num_scenes}-scene recap for Ch.{ch_start}-{ch_end}. Start with hook, end with cliffhanger."
    payload = {
        "system_instruction": {"parts": [{"text": GEMINI_SYSTEM}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 4096}
    }
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=60)
            r.raise_for_status()
            raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            script = json.loads(raw.strip())
            log(f"Script ready: {len(script['scenes'])} scenes", "✅")
            return script
        except Exception as e:
            log(f"Attempt {attempt+1} failed: {e}", "⚠️")
            time.sleep(5)
    log("Gemini failed — using fallback script", "❌")
    return fallback_script(ch_start, ch_end)

def fallback_script(ch_start, ch_end):
    return {
        "title": f"Solo Leveling Ch.{ch_start}-{ch_end} Full Recap",
        "output_filename": f"solo_leveling_ch{ch_start}_{ch_end}.mp4",
        "scenes": [
            {"id":1,"type":"static_bg","background_color":"#000000","overlay_text":"SOLO LEVELING",
             "sub_text":f"Chapters {ch_start}–{ch_end}","narration":"What if the weakest hunter became the strongest? This is Solo Leveling.","voice":"am_adam","mood":"epic","transition":"fade"},
            {"id":2,"type":"ai_image","image_prompt":"Korean manhwa art style, webtoon illustration, Sung Jinwoo young Korean man in dark dungeon, determined face, glowing blue system window floating, dramatic lighting, high detail",
             "narration":"Sung Jinwoo was the weakest E-Rank hunter in Korea. Every dungeon was a near-death experience. He kept going anyway — for his family.","voice":"am_adam","mood":"dramatic","transition":"fade"},
            {"id":3,"type":"ai_image","image_prompt":"Korean manhwa art style, massive stone temple, giant statues with glowing red eyes awakening, hunters fleeing in panic, dramatic action scene",
             "narration":"Then came the Double Dungeon. A hidden floor. Stone gods that moved. A massacre. In his final breath — the System chose him.","voice":"am_adam","mood":"tense","transition":"fade"},
            {"id":4,"type":"static_bg","background_color":"#050510","overlay_text":"The System has chosen you.","sub_text":"as its sole Player.",
             "narration":"Arise. The journey of the Shadow Monarch begins. Subscribe so you don't miss what happens next.","voice":"am_adam","mood":"epic","transition":"fade"},
        ]
    }

# ── Step 3: Generate images ───────────────────────────────────────
def generate_ai_image(scene: dict, out_path: Path):
    w, h   = RESOLUTION.split("x")
    prompt = scene.get("image_prompt", "Korean manhwa scene")
    seed   = scene["id"] * 137
    url    = POLLINATIONS.format(prompt=quote(prompt), w=w, h=h, seed=seed)
    log(f"Scene {scene['id']}: Generating image...", "🎨")
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=90)
            r.raise_for_status()
            out_path.write_bytes(r.content)
            log(f"Scene {scene['id']}: Image saved ✅", "")
            return
        except Exception as e:
            log(f"Attempt {attempt+1}: {e}", "⚠️")
            time.sleep(8)
    generate_static_bg(scene, out_path)

def generate_static_bg(scene: dict, out_path: Path):
    w, h    = RESOLUTION.split("x")
    color   = scene.get("background_color", "#0a0a0a")
    text    = scene.get("overlay_text", "")
    subtext = scene.get("sub_text", "")
    log(f"Scene {scene['id']}: Generating title card...", "🖼️")
    filters = []
    if text:
        esc = text.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
        filters.append(f"drawtext=fontfile={FONT_PATH}:text='{esc}':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2-30:shadowcolor=black@0.9:shadowx=3:shadowy=3")
    if subtext:
        esc2 = subtext.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
        filters.append(f"drawtext=fontfile={FONT_PATH}:text='{esc2}':fontcolor=#aaaaaa:fontsize=32:x=(w-text_w)/2:y=(h-text_h)/2+60:shadowcolor=black@0.9:shadowx=2:shadowy=2")
    vf = ",".join(filters) if filters else "null"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c={color}:size={w}x{h}:rate=1",
        "-vf", vf, "-frames:v", "1", str(out_path)
    ], check=True, capture_output=True)
    log(f"Scene {scene['id']}: Title card saved ✅", "")

# ── Step 4: Build scene clip (Ken Burns + audio) ──────────────────
def get_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                        "-of","default=noprint_wrappers=1:nokey=1",str(path)],
                       capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except: return 4.0

def build_clip(scene: dict, img_path: Path, aud_path: Path, out_path: Path):
    w, h     = RESOLUTION.split("x")
    duration = get_duration(aud_path) + 0.5
    fps      = 25
    frames   = int(duration * fps)
    sid      = scene["id"]
    log(f"Scene {sid}: Building clip ({duration:.1f}s)...", "🎬")

    # Ken Burns: alternate zoom in/out
    if sid % 2 == 0:
        zoom = "'min(zoom+0.0003,1.08)'"
    else:
        zoom = "'if(eq(on,1),1.08,max(zoom-0.0003,1.0))'"

    fade_d = 0.4
    vf = (
        f"scale={int(w)*2}:{int(h)*2}:force_original_aspect_ratio=increase,"
        f"zoompan=z={zoom}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={fps},"
        f"fade=t=in:st=0:d={fade_d},"
        f"fade=t=out:st={duration-fade_d}:d={fade_d}"
    )
    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(fps), "-i", str(img_path),
        "-i", str(aud_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-t", str(duration), "-shortest",
        str(out_path)
    ], check=True, capture_output=True)
    log(f"Scene {sid}: Clip ready ✅", "")

# ── Step 5: Concat + BGM ──────────────────────────────────────────
def concat_and_mix(clips: list, output_path: Path):
    log("Concatenating clips...", "🎞️")
    txt = WORK_DIR / "concat.txt"
    txt.write_text("\n".join(f"file '{p.resolve()}'" for p in clips))
    merged = WORK_DIR / "merged.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt),
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(merged)
    ], check=True)

    if BGM_PATH.exists():
        log("Mixing BGM...", "🎵")
        dur = get_duration(merged)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(merged),
            "-stream_loop", "-1", "-i", str(BGM_PATH),
            "-filter_complex", f"[1:a]volume=0.15,atrim=0:duration={dur}[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(output_path)
        ], check=True)
        merged.unlink(missing_ok=True)
    else:
        merged.rename(output_path)

    mb = output_path.stat().st_size / (1024*1024)
    log(f"Done! {output_path} ({mb:.1f} MB) 🎉", "")

# ── Telegram ──────────────────────────────────────────────────────
def notify(msg: str):
    token = os.environ.get("TG_TOKEN","")
    uid   = os.environ.get("USER_ID","")
    if not token or not uid: return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id":uid,"text":msg,"parse_mode":"HTML"}, timeout=10)
    except: pass

# ── Main ──────────────────────────────────────────────────────────
def run(ch_start: int, ch_end: int, num_scenes: int):
    setup()
    log(f"{MANGA_TITLE} | Ch.{ch_start}-{ch_end} | {num_scenes} scenes", "🚀")

    plot   = fetch_wiki_plot(ch_start, ch_end)
    script = generate_script(plot, ch_start, ch_end, num_scenes)
    (WORK_DIR / "generated_script.json").write_text(json.dumps(script, indent=2))

    scenes     = script["scenes"]
    out_name   = script.get("output_filename", f"solo_leveling_ch{ch_start}_{ch_end}.mp4")
    out_path   = OUTPUT_DIR / out_name
    clips      = []

    for scene in scenes:
        sid      = scene["id"]
        img_path = SCENES_DIR / f"scene_{sid:03d}.png"
        aud_path = AUDIO_DIR  / f"scene_{sid:03d}.mp3"
        clip_p   = SCENES_DIR / f"scene_{sid:03d}_clip.mp4"

        if scene.get("type") == "ai_image":
            generate_ai_image(scene, img_path)
        else:
            generate_static_bg(scene, img_path)

        generate_audio(scene.get("narration",""), scene.get("voice","am_adam"), aud_path)
        build_clip(scene, img_path, aud_path, clip_p)
        clips.append(clip_p)
        time.sleep(1)

    concat_and_mix(clips, out_path)
    notify(f"✅ <b>{MANGA_TITLE} Ch.{ch_start}-{ch_end}</b> done!\n📁 {out_name}\n🎬 {len(scenes)} scenes")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--chapters", default="1-10")
    p.add_argument("--scenes",   type=int, default=10)
    args = p.parse_args()
    try:
        s, e = map(int, args.chapters.split("-"))
    except:
        print("❌ Use format: --chapters 1-10"); sys.exit(1)
    run(s, e, args.scenes)
