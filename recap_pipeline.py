#!/usr/bin/env python3
"""
Manhwa Recap Pipeline — Solo Leveling
Fixes: Gemini 2.0-flash model, Groq fallback, 9:16 resolution, better prompts
"""

import os, sys, json, time, argparse, subprocess, requests
from pathlib import Path
from urllib.parse import quote
from audio_gen import generate_audio

# ── Config ────────────────────────────────────────────────────────
MANGA_TITLE  = "Solo Leveling"
FANDOM_BASE  = "https://solo-leveling.fandom.com/wiki"

# 9:16 for Instagram Reels / Facebook Reels / TikTok
# 16:9 for YouTube — change here or pass via --format
FORMATS = {
    "reels": ("1080x1920", "9:16"),   # Instagram/Facebook/TikTok
    "youtube": ("1280x720", "16:9"),  # YouTube
}

POLLINATIONS = "https://image.pollinations.ai/prompt/{prompt}?width={w}&height={h}&seed={seed}&nologo=true&model=flux"
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

def get_gemini_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("KEY1") or os.environ.get("KEY2") or ""

def get_groq_key():
    return os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_KEY") or ""


# ── Step 1: Fetch plot ────────────────────────────────────────────
BUILTIN_PLOT = """
Solo Leveling Ch1-10 detailed summary:

WORLD SETUP: Ten years ago, magical gates connecting to monster dungeons appeared worldwide.
Humans with supernatural powers called Hunters must clear these dungeons.
Hunters have fixed ranks from E (weakest) to S (strongest) — ranks never change.

CH 1-2 — THE WEAKEST:
Sung Jinwoo is an E-Rank hunter, the absolute weakest. He's called "the weakest hunter
of all mankind." He enters dungeons to pay for his mother's hospital bills, relying on
teammates to survive. One day, his party discovers a hidden door in a D-Rank dungeon.
Against better judgment, they enter — revealing a massive stone temple on the second floor.
Giant stone statues line the walls. Carved rules appear: bow to the statues, don't make noise,
never stop praying. Hunters panic and accidentally trigger the trap. The statues awaken.

CH 3-4 — THE DOUBLE DUNGEON MASSACRE:
The stone gods slaughter the hunters one by one. Jinwoo fights desperately but is outmatched.
He finds a solution — a hidden exit behind the altar — but there's only enough time to help
others escape. He stays behind. A statue runs him through. Near death, a mysterious glowing
screen appears: "You have been selected as a Player." Jinwoo blacks out.

CH 5-6 — THE SYSTEM AWAKENS:
Jinwoo wakes in a hospital. His injuries are healed — impossibly fast. The System interface
is real: floating quest windows only he can see. First quest: 100 push-ups, 100 sit-ups,
100 squats, 10km run — or die. He completes it despite his wounds. He realizes: the System
gives him stat points. He can grow stronger. No hunter has EVER grown stronger after awakening.

CH 7-8 — SECRET GRINDING:
Jinwoo begins daily quests in secret. His stats rise visibly. He re-enters low-level dungeons
and handles monsters that once required full teams — alone. Other hunters notice something is
off. The System rewards him with skills, inventory, and titles. He's becoming something
entirely new — not just a stronger hunter, but a different class of being entirely.

CH 9-10 — THE PENALTY ZONE:
Jinwoo misses a daily quest and gets pulled into a "penalty zone" — a nightmare dungeon
designed to kill. He survives through wit and his growing powers. He levels up again.
The gap between him and regular hunters widens. The System calls him its Player.
He begins to wonder: what exactly is the System, and why did it choose him?
"""

def fetch_wiki_plot(ch_start: int, ch_end: int) -> str:
    log(f"Fetching plot: Ch.{ch_start}-{ch_end}", "📖")
    import re
    urls = [
        "https://en.wikipedia.org/wiki/Solo_Leveling",
        f"{FANDOM_BASE}/Story_Arcs",
    ]
    text = ""
    for url in urls:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                t = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', r.text, flags=re.DOTALL)
                t = re.sub(r'<[^>]+>', ' ', t)
                t = re.sub(r'\s+', ' ', t).strip()
                text += f"\n[{url}]\n{t[:2000]}"
                log(f"Fetched {url}", "✅")
        except Exception as e:
            log(f"Failed {url}: {e}", "⚠️")

    # Always append builtin for richer context
    text += f"\n\n[DETAILED PLOT]\n{BUILTIN_PLOT}"
    return text


# ── Step 2: AI Script Generation ─────────────────────────────────

SCRIPT_SYSTEM = """
You are an expert YouTube Shorts / Instagram Reels manhwa recap scriptwriter.
Generate an exciting scene-by-scene recap script in JSON format.

Return ONLY valid JSON — no markdown fences, no explanation, no extra text.

JSON structure:
{
  "title": "Solo Leveling Ch.X-Y | Full Recap",
  "output_filename": "solo_leveling_chX_Y.mp4",
  "scenes": [
    {
      "id": 1,
      "type": "static_bg",
      "background_color": "#000000",
      "overlay_text": "SOLO LEVELING",
      "sub_text": "Chapters X-Y | Full Recap",
      "narration": "Hook narration — punchy, 1-2 sentences.",
      "voice": "am_adam",
      "mood": "epic",
      "transition": "fade"
    },
    {
      "id": 2,
      "type": "ai_image",
      "image_prompt": "anime illustration style, manhwa webtoon art, [SPECIFIC SCENE], cel shading, vibrant colors, dramatic lighting, 4k detail, professional digital art",
      "narration": "3-4 sentence storyteller narration. Passionate fan tone. Build tension.",
      "voice": "am_adam",
      "mood": "dramatic",
      "transition": "fade"
    }
  ]
}

CRITICAL RULES:
1. image_prompt MUST start with: "anime illustration style, manhwa webtoon art, cel shading, vibrant colors"
2. image_prompt MUST be specific about: character appearance, setting, action, lighting, emotion
3. Good example: "anime illustration style, manhwa webtoon art, cel shading, vibrant colors, Sung Jinwoo young Korean man with black spiky hair, piercing purple eyes, standing in dark stone dungeon, glowing blue holographic System window floating before him, blue energy particles, shocked expression, dramatic side lighting, 4k detail"
4. Bad example: "Korean manhwa scene" (too vague — generates garbage images)
5. First scene: always static_bg black title card
6. Every 3-4 ai_image scenes: add 1 static_bg chapter marker (dark bg, white dramatic text)
7. Last scene: static_bg cliffhanger + "Subscribe for Ch.X-Y!" hook
8. Narration: excited storyteller, NOT dubbing speech bubbles
9. Voices: am_adam (deep dramatic), af_heart (warm), af_bella (intense female)
10. Generate EXACTLY the requested number of scenes
"""

def generate_script_gemini(plot: str, ch_start: int, ch_end: int, num_scenes: int) -> dict | None:
    key = get_gemini_key()
    if not key:
        log("No Gemini key found", "⚠️")
        return None

    # Try gemini-2.0-flash first, then 1.5-flash as backup
    models = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash-latest",
    ]

    prompt = (
        f"Plot of Solo Leveling Chapters {ch_start}-{ch_end}:\n\n{plot[:5000]}\n\n"
        f"Write a {num_scenes}-scene recap script. "
        f"Start with a hook that grabs attention in 3 seconds. "
        f"End with a cliffhanger and subscribe call-to-action."
    )

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {
            "system_instruction": {"parts": [{"text": SCRIPT_SYSTEM}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.85, "maxOutputTokens": 8192}
        }
        log(f"Trying Gemini model: {model}...", "🤖")
        try:
            r = requests.post(url, json=payload, timeout=90)
            r.raise_for_status()
            raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = raw.split("\n", 1)[1] if raw.startswith("```") else raw
            raw = raw.rsplit("```", 1)[0] if raw.endswith("```") else raw
            script = json.loads(raw.strip())
            log(f"Gemini ({model}): {len(script['scenes'])} scenes generated ✅", "")
            return script
        except Exception as e:
            log(f"Gemini {model} failed: {e}", "⚠️")
            time.sleep(3)

    return None


def generate_script_groq(plot: str, ch_start: int, ch_end: int, num_scenes: int) -> dict | None:
    key = get_groq_key()
    if not key:
        log("No Groq key found", "⚠️")
        return None

    log("Trying Groq (llama-3.3-70b)...", "🤖")
    url = "https://api.groq.com/openai/v1/chat/completions"
    prompt = (
        f"Plot of Solo Leveling Chapters {ch_start}-{ch_end}:\n\n{plot[:4000]}\n\n"
        f"Write a {num_scenes}-scene recap script. "
        f"Start with a hook. End with cliffhanger + subscribe CTA."
    )

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": SCRIPT_SYSTEM},
            {"role": "user",   "content": prompt}
        ],
        "temperature": 0.85,
        "max_tokens": 8192,
    }

    try:
        r = requests.post(url, json=payload,
                          headers={"Authorization": f"Bearer {key}"},
                          timeout=90)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        raw = raw.split("\n", 1)[1] if raw.startswith("```") else raw
        raw = raw.rsplit("```", 1)[0] if raw.endswith("```") else raw
        script = json.loads(raw.strip())
        log(f"Groq: {len(script['scenes'])} scenes generated ✅", "")
        return script
    except Exception as e:
        log(f"Groq failed: {e}", "⚠️")
        return None


def generate_script(plot: str, ch_start: int, ch_end: int, num_scenes: int) -> dict:
    # Try Gemini first, then Groq, then hardcoded fallback
    script = generate_script_gemini(plot, ch_start, ch_end, num_scenes)
    if script:
        return script

    script = generate_script_groq(plot, ch_start, ch_end, num_scenes)
    if script:
        return script

    log("All AI failed — using detailed fallback script", "❌")
    return fallback_script(ch_start, ch_end, num_scenes)


def fallback_script(ch_start: int, ch_end: int, num_scenes: int) -> dict:
    """Rich fallback with proper anime art prompts so images actually look good."""
    return {
        "title": f"Solo Leveling Ch.{ch_start}-{ch_end} | Full Recap",
        "output_filename": f"solo_leveling_ch{ch_start}_{ch_end}.mp4",
        "scenes": [
            {"id":1,"type":"static_bg","background_color":"#000000",
             "overlay_text":"SOLO LEVELING","sub_text":f"Chapters {ch_start}–{ch_end} | Full Recap",
             "narration":"What if the weakest man alive was chosen to become the most powerful being on Earth? This is Solo Leveling.",
             "voice":"am_adam","mood":"epic","transition":"fade"},

            {"id":2,"type":"ai_image",
             "image_prompt":"anime illustration style, manhwa webtoon art, cel shading, vibrant colors, Sung Jinwoo young Korean man with black messy hair, tired worn-out face, cheap hunter gear, standing at entrance of glowing magical dungeon gate at night, Seoul city behind him, blue portal light on his face, sad determined expression, 4k detail, dramatic lighting",
             "narration":"Sung Jinwoo. Known across Korea as the weakest E-Rank hunter alive. While others rose to glory in dungeons of monsters, he struggled to survive the easiest ones — barely making rent, paying for his mother's hospital bills with blood money.",
             "voice":"am_adam","mood":"dramatic","transition":"fade"},

            {"id":3,"type":"ai_image",
             "image_prompt":"anime illustration style, manhwa webtoon art, cel shading, vibrant colors, group of hunters exploring ancient stone temple dungeon, massive stone pillars, mysterious glowing runes on walls, torchlight, eerie atmosphere, hunters in various combat gear looking nervous, wide shot, 4k detail",
             "narration":"Then came the day everything changed. A routine D-Rank dungeon raid. Behind a hidden door — a second floor. A temple older than civilization. And carved into the stone walls: rules that no one had ever survived breaking.",
             "voice":"am_adam","mood":"mysterious","transition":"fade"},

            {"id":4,"type":"ai_image",
             "image_prompt":"anime illustration style, manhwa webtoon art, cel shading, vibrant colors, giant stone golem statues awakening with glowing red evil eyes, massive stone fists crushing hunters, blood and chaos, hunters screaming and running, ancient temple interior, fire and destruction, terrifying horror action scene, 4k detail",
             "narration":"The statues woke up. One by one, hunters were crushed, impaled, obliterated. The temple became a slaughterhouse. Jinwoo fought with everything he had — but E-Rank power against stone gods was nothing. Absolutely nothing.",
             "voice":"am_adam","mood":"tense","transition":"fade"},

            {"id":5,"type":"static_bg","background_color":"#050005",
             "overlay_text":"In his final moments...","sub_text":"the System appeared.",
             "narration":"Mortally wounded, bleeding out, Jinwoo made one last choice — stay behind so others could live.",
             "voice":"am_adam","mood":"dramatic","transition":"fade"},

            {"id":6,"type":"ai_image",
             "image_prompt":"anime illustration style, manhwa webtoon art, cel shading, vibrant colors, Sung Jinwoo lying dying on stone floor in dark dungeon, glowing blue holographic System window floating above him, text reading CONGRATULATIONS YOU HAVE BEEN SELECTED AS A PLAYER, blue light on his pale face, dramatic close-up, ethereal atmosphere, 4k detail",
             "narration":"And then — a miracle. Or something stranger than a miracle. A System. A floating interface only he could see. It offered him a second chance. Not as a better hunter. As something the world had never seen before.",
             "voice":"am_adam","mood":"wonder","transition":"fade"},

            {"id":7,"type":"ai_image",
             "image_prompt":"anime illustration style, manhwa webtoon art, cel shading, vibrant colors, Sung Jinwoo in hospital bed doing intense one-arm push-ups with glowing blue quest timer countdown floating above, determined fierce expression, muscles straining, blue energy aura, dramatic low angle shot, 4k detail",
             "narration":"He woke up in hospital — healed. The System gave him his first quest: a brutal physical challenge, or face death. Jinwoo completed it through sheer will. His stats went up. For the first time in history, a hunter was growing stronger.",
             "voice":"am_adam","mood":"epic","transition":"fade"},

            {"id":8,"type":"ai_image",
             "image_prompt":"anime illustration style, manhwa webtoon art, cel shading, vibrant colors, Sung Jinwoo standing alone in low-level dungeon surrounded by defeated monster bodies, glowing blue level-up notification screen, confident powerful stance, purple eyes glowing, dark dungeon atmosphere, dramatic lighting from below, 4k detail",
             "narration":"He began grinding in secret. Every dungeon that once nearly killed him — he cleared alone. The System rewarded him with skills, titles, and power. The weakest hunter was becoming something else entirely. Something that had no name yet.",
             "voice":"am_adam","mood":"dramatic","transition":"fade"},

            {"id":9,"type":"static_bg","background_color":"#000510",
             "overlay_text":"He was no longer a hunter.","sub_text":"He was a Player.",
             "narration":"The rules of this world only applied to hunters. Sung Jinwoo had just stepped outside those rules forever.",
             "voice":"am_adam","mood":"epic","transition":"fade"},

            {"id":10,"type":"static_bg","background_color":"#000000",
             "overlay_text":"What happens next?","sub_text":f"Ch.{ch_end+1} recap coming soon 🔥",
             "narration":"The Shadow Monarch's rise has only just begun. Subscribe and hit the bell — you do NOT want to miss what happens next in Solo Leveling.",
             "voice":"am_adam","mood":"epic","transition":"fade"},
        ][:num_scenes]
    }


# ── Step 3: Generate images ───────────────────────────────────────
def generate_ai_image(scene: dict, out_path: Path, resolution: str):
    w, h   = resolution.split("x")
    prompt = scene.get("image_prompt", "anime illustration, solo leveling scene")
    seed   = scene["id"] * 137
    url    = POLLINATIONS.format(prompt=quote(prompt), w=w, h=h, seed=seed)
    log(f"Scene {scene['id']}: Generating image...", "🎨")
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            # Check it's actually an image (not an error page)
            if r.headers.get("content-type","").startswith("image"):
                out_path.write_bytes(r.content)
                log(f"Scene {scene['id']}: Image saved ✅", "")
                return
            else:
                raise ValueError(f"Got non-image response: {r.headers.get('content-type')}")
        except Exception as e:
            log(f"Attempt {attempt+1}: {e}", "⚠️")
            time.sleep(10)
    generate_static_bg(scene, out_path, resolution)


def generate_static_bg(scene: dict, out_path: Path, resolution: str):
    w, h    = resolution.split("x")
    color   = scene.get("background_color", "#0a0a0a")
    text    = scene.get("overlay_text", "")
    subtext = scene.get("sub_text", "")
    log(f"Scene {scene['id']}: Generating title card...", "🖼️")

    # Scale font size for resolution
    is_vertical = int(h) > int(w)
    main_size   = 80 if is_vertical else 64
    sub_size    = 40 if is_vertical else 32
    main_y      = "(h-text_h)/2-50" if subtext else "(h-text_h)/2"

    filters = []
    if text:
        esc = text.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
        filters.append(
            f"drawtext=fontfile={FONT_PATH}:text='{esc}':"
            f"fontcolor=white:fontsize={main_size}:"
            f"x=(w-text_w)/2:y={main_y}:"
            f"shadowcolor=black@0.9:shadowx=3:shadowy=3"
        )
    if subtext:
        esc2 = subtext.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
        filters.append(
            f"drawtext=fontfile={FONT_PATH}:text='{esc2}':"
            f"fontcolor=#cccccc:fontsize={sub_size}:"
            f"x=(w-text_w)/2:y=(h+text_h)/2+20:"
            f"shadowcolor=black@0.9:shadowx=2:shadowy=2"
        )

    vf = ",".join(filters) if filters else "null"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c={color}:size={w}x{h}:rate=1",
        "-vf", vf, "-frames:v", "1", str(out_path)
    ], check=True, capture_output=True)
    log(f"Scene {scene['id']}: Title card saved ✅", "")


# ── Step 4: Build scene clip ──────────────────────────────────────
def get_duration(path: Path) -> float:
    r = subprocess.run([
        "ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=noprint_wrappers=1:nokey=1",str(path)
    ], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except: return 4.0


def build_clip(scene: dict, img_path: Path, aud_path: Path, out_path: Path, resolution: str):
    w, h     = resolution.split("x")
    duration = get_duration(aud_path) + 0.6
    fps      = 25
    frames   = int(duration * fps)
    sid      = scene["id"]
    log(f"Scene {sid}: Building clip ({duration:.1f}s)...", "🎬")

    # Ken Burns — alternate zoom in/out
    zoom = "'min(zoom+0.0002,1.06)'" if sid % 2 == 0 else "'if(eq(on,1),1.06,max(zoom-0.0002,1.0))'"
    fade_d = 0.3

    vf = (
        f"scale={int(w)*2}:{int(h)*2}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},"
        f"zoompan=z={zoom}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={fps},"
        f"fade=t=in:st=0:d={fade_d},"
        f"fade=t=out:st={max(0, duration-fade_d)}:d={fade_d}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(fps), "-i", str(img_path),
        "-i", str(aud_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-t", str(duration), "-shortest",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        log(f"Scene {sid}: FFmpeg error — {result.stderr[-300:].decode()}", "❌")
        raise subprocess.CalledProcessError(result.returncode, cmd)
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
            "-filter_complex",
            f"[1:a]volume=0.12,atrim=0:duration={dur}[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(output_path)
        ], check=True)
        merged.unlink(missing_ok=True)
    else:
        merged.rename(output_path)

    mb = output_path.stat().st_size / (1024*1024)
    dur = get_duration(output_path)
    log(f"Done! {output_path} ({mb:.1f} MB, {dur:.0f}s) 🎉", "")


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
def run(ch_start: int, ch_end: int, num_scenes: int, fmt: str):
    setup()
    resolution, aspect = FORMATS.get(fmt, FORMATS["reels"])
    log(f"{MANGA_TITLE} | Ch.{ch_start}-{ch_end} | {num_scenes} scenes | {resolution} ({aspect})", "🚀")

    plot   = fetch_wiki_plot(ch_start, ch_end)
    script = generate_script(plot, ch_start, ch_end, num_scenes)
    (WORK_DIR / "generated_script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False))
    log(f"Script saved ({len(script['scenes'])} scenes)", "💾")

    scenes   = script["scenes"]
    out_name = script.get("output_filename", f"solo_leveling_ch{ch_start}_{ch_end}.mp4")
    out_path = OUTPUT_DIR / out_name
    clips    = []

    for scene in scenes:
        sid      = scene["id"]
        img_path = SCENES_DIR / f"scene_{sid:03d}.png"
        aud_path = AUDIO_DIR  / f"scene_{sid:03d}.mp3"
        clip_p   = SCENES_DIR / f"scene_{sid:03d}_clip.mp4"

        if scene.get("type") == "ai_image":
            generate_ai_image(scene, img_path, resolution)
        else:
            generate_static_bg(scene, img_path, resolution)

        generate_audio(scene.get("narration",""), scene.get("voice","am_adam"), aud_path)
        build_clip(scene, img_path, aud_path, clip_p, resolution)
        clips.append(clip_p)
        time.sleep(1)

    concat_and_mix(clips, out_path)

    total_dur = sum(get_duration(c) for c in clips)
    notify(
        f"✅ <b>{MANGA_TITLE} Ch.{ch_start}-{ch_end}</b> done!\n"
        f"📁 {out_name}\n"
        f"🎬 {len(scenes)} scenes | {total_dur:.0f}s | {resolution}"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--chapters", default="1-10")
    p.add_argument("--scenes",   type=int, default=10)
    p.add_argument("--format",   default="reels", choices=["reels","youtube"],
                   help="reels=1080x1920 (Instagram/FB), youtube=1280x720")
    args = p.parse_args()
    try:
        s, e = map(int, args.chapters.split("-"))
    except:
        print("❌ Use format: --chapters 1-10"); sys.exit(1)
    run(s, e, args.scenes, args.format)
