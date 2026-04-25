#!/usr/bin/env python3
"""
Manhwa Recap Pipeline — Solo Leveling Edition
=============================================
Flow:
  1. Fetch plot summary from Fandom wiki (free, no API key)
  2. Gemini reads the plot → writes scene-by-scene narration script
  3. Pollinations AI generates manhwa-style images per scene (free)
  4. Kokoro TTS narrates each scene (fallback: edge-tts)
  5. FFmpeg: image + Ken Burns zoom + audio → scene clip
  6. All clips + BGM → final MP4
  7. Telegram notification

Usage:
    python recap_pipeline.py                        # default: Solo Leveling Ch1-10
    python recap_pipeline.py --chapters 11-20
    python recap_pipeline.py --chapters 1-5 --scenes 8
"""

import os
import sys
import json
import time
import argparse
import textwrap
import subprocess
import requests
from pathlib import Path
from urllib.parse import quote


# ─────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────

MANGA_TITLE  = "Solo Leveling"
MANGA_SLUG   = "Solo_Leveling"          # Fandom wiki slug
FANDOM_BASE  = "https://solo-leveling.fandom.com/wiki"

POLLINATIONS = "https://image.pollinations.ai/prompt/{prompt}?width={w}&height={h}&seed={seed}&nologo=true&model=flux"
KOKORO_URL   = "https://api.kokorotts.com/v1/audio/speech"

RESOLUTION   = "1280x720"
FONT_PATH    = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

WORK_DIR   = Path("workspace")
SCENES_DIR = WORK_DIR / "scenes"
AUDIO_DIR  = WORK_DIR / "audio"
OUTPUT_DIR = Path("output")
BGM_PATH   = Path("bgm/dramatic.mp3")   # optional — pipeline works without it


# ─────────────────────────────────────────────────────────────────
#  SETUP
# ─────────────────────────────────────────────────────────────────

def setup():
    for d in [WORK_DIR, SCENES_DIR, AUDIO_DIR, OUTPUT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def log(msg, icon="▶"):
    print(f"\n{icon}  {msg}", flush=True)

def get_api_key():
    key = (os.environ.get("GEMINI_API_KEY") or
           os.environ.get("KEY1") or
           os.environ.get("KEY2"))
    if not key:
        print("❌  Set GEMINI_API_KEY / KEY1 / KEY2 env variable")
        sys.exit(1)
    return key


# ─────────────────────────────────────────────────────────────────
#  STEP 1 — FETCH PLOT FROM FANDOM WIKI
# ─────────────────────────────────────────────────────────────────

def fetch_wiki_plot(chapter_start: int, chapter_end: int) -> str:
    """Scrape plot summary from Solo Leveling Fandom wiki pages."""
    log(f"Fetching plot: {MANGA_TITLE} Ch.{chapter_start}–{chapter_end}", "📖")

    # Try fetching the story arcs page first for overview
    urls_to_try = [
        f"{FANDOM_BASE}/Story_Arcs",
        f"{FANDOM_BASE}/{MANGA_SLUG}",
        f"https://en.wikipedia.org/wiki/Solo_Leveling",
    ]

    combined_text = ""
    for url in urls_to_try:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                # Very basic text extraction — strip HTML tags
                text = r.text
                # Remove scripts/styles
                import re
                text = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                # Grab a meaningful chunk
                combined_text += f"\n\n[Source: {url}]\n{text[:4000]}"
                log(f"Fetched: {url}", "✅")
        except Exception as e:
            log(f"Failed {url}: {e}", "⚠️")

    if not combined_text:
        log("Wiki fetch failed, using built-in plot summary", "⚠️")
        combined_text = BUILTIN_PLOT

    return combined_text


# Built-in fallback plot so pipeline always works even if wiki is down
BUILTIN_PLOT = """
Solo Leveling — Plot Summary (Chapters 1-10):

In a world where gates connecting to monster-filled dungeons appeared 10 years ago, 
humans awakened with supernatural powers called Hunters. Sung Jinwoo is considered 
the weakest E-Rank hunter, barely able to survive the lowest-level dungeons.

Ch1-2: Jinwoo joins a D-Rank dungeon raid to earn money for his sick mother's 
hospital bills. The raid team discovers a hidden second floor — a deadly double dungeon 
filled with traps and giant statues. The statues come alive and massacre the hunters.

Ch3-4: In a desperate moment, Jinwoo sacrifices himself so others can escape. 
Mortally wounded and near death, he encounters a mysterious floating screen — 
the "System" — which offers him a second chance as its sole Player.

Ch5-6: Jinwoo wakes up in the hospital, seemingly healed. He receives his first 
quest from the System: do 100 push-ups, 100 sit-ups, and a 10km run — or die. 
He realizes this is not a dream.

Ch7-8: Jinwoo begins grinding daily quests, hiding his new power. He notices he 
is actually getting stronger — something that has never happened to any hunter before. 
All hunters are born with a fixed rank. He should be the exception.

Ch9-10: Jinwoo re-enters a low-level dungeon and realizes his growth rate is 
extraordinary. He begins to understand the System's true potential. The weakest 
hunter in the world has just taken his first step toward becoming the strongest.
"""


# ─────────────────────────────────────────────────────────────────
#  STEP 2 — GEMINI GENERATES SCENE SCRIPT
# ─────────────────────────────────────────────────────────────────

GEMINI_SYSTEM = """
You are an expert YouTube manhwa recap scriptwriter. 
Given a plot summary, write a cinematic scene-by-scene script in JSON format.

Return ONLY valid JSON — no markdown fences, no explanation.

JSON structure:
{
  "title": "Video title (e.g. Solo Leveling Ch.1-10 Full Recap)",
  "output_filename": "solo_leveling_ch1_10.mp4",
  "scenes": [
    {
      "id": 1,
      "type": "static_bg",
      "background_color": "#0a0a0a",
      "overlay_text": "SOLO LEVELING",
      "sub_text": "Chapters 1-10 | Full Recap",
      "narration": "Short punchy hook narration.",
      "voice": "am_adam",
      "mood": "epic",
      "transition": "fade"
    },
    {
      "id": 2,
      "type": "ai_image",
      "image_prompt": "Detailed manhwa-style image prompt with art direction",
      "narration": "2-4 sentence storyteller narration for this scene. Engaging, cinematic tone.",
      "voice": "am_adam",
      "mood": "dramatic",
      "transition": "fade"
    }
  ]
}

Rules:
- First scene: always static_bg title card (black bg, manga title in white)
- Last scene: always static_bg with cliffhanger or "subscribe" hook
- For ai_image scenes: image_prompt must say "Korean manhwa art style, webtoon illustration, high detail, dramatic lighting" + specific scene description
- Narration is storyteller voice — excited fan, NOT dubbing speech bubbles
- Voice options: am_adam (deep narrator), af_heart (warm), af_bella (dramatic female)
- Moods: epic, dramatic, mysterious, tense, action, emotional
- Mix static_bg title cards between major story beats
- Generate exactly the number of scenes requested
- Each narration should be 2-5 sentences — enough for 10-20 seconds of audio
"""


def generate_script_with_gemini(plot_text: str, chapter_start: int, chapter_end: int, num_scenes: int) -> dict:
    """Call Gemini API to generate the full scene script from plot summary."""
    log("Calling Gemini to generate scene script...", "🤖")

    api_key = get_api_key()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

    prompt = f"""
Plot summary of {MANGA_TITLE}, Chapters {chapter_start}-{chapter_end}:

{plot_text[:6000]}

Generate a {num_scenes}-scene YouTube recap video script for chapters {chapter_start}-{chapter_end}.
Make it exciting and engaging — like a passionate fan explaining it to another fan.
Start with a hook, end with a cliffhanger teaser.
"""

    payload = {
        "system_instruction": {"parts": [{"text": GEMINI_SYSTEM}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 4096}
    }

    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            raw  = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            # Strip markdown fences if Gemini adds them
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]

            script = json.loads(raw.strip())
            log(f"Script generated: {len(script['scenes'])} scenes", "✅")
            return script

        except json.JSONDecodeError as e:
            log(f"JSON parse error on attempt {attempt+1}: {e}", "⚠️")
            time.sleep(3)
        except Exception as e:
            log(f"Gemini error on attempt {attempt+1}: {e}", "⚠️")
            time.sleep(5)

    log("Gemini failed — using fallback script", "❌")
    return get_fallback_script(chapter_start, chapter_end)


def get_fallback_script(ch_start: int, ch_end: int) -> dict:
    """Minimal hardcoded script used if Gemini fails."""
    return {
        "title": f"Solo Leveling Ch.{ch_start}-{ch_end} Full Recap",
        "output_filename": f"solo_leveling_ch{ch_start}_{ch_end}.mp4",
        "scenes": [
            {"id": 1, "type": "static_bg", "background_color": "#000000",
             "overlay_text": "SOLO LEVELING", "sub_text": f"Chapters {ch_start}–{ch_end}",
             "narration": "What if the weakest hunter in the world suddenly had the power to become the strongest? This is Solo Leveling.",
             "voice": "am_adam", "mood": "epic", "transition": "fade"},
            {"id": 2, "type": "ai_image",
             "image_prompt": "Korean manhwa art style, webtoon illustration, dramatic lighting, Sung Jinwoo a young Korean man standing in a dark dungeon corridor, determined expression, wearing casual hunter gear, glowing blue system screen floating before him, high detail",
             "narration": "Sung Jinwoo was known as the weakest E-Rank hunter in all of Korea. Every raid was a near-death experience. Every dungeon a gamble with his life. But he kept going — for his family.",
             "voice": "am_adam", "mood": "dramatic", "transition": "fade"},
            {"id": 3, "type": "ai_image",
             "image_prompt": "Korean manhwa art style, massive stone temple dungeon interior, giant stone statues with glowing red eyes awakening, hunters running in panic, dramatic lighting, action scene, high detail",
             "narration": "Then came the Double Dungeon. A hidden floor. Stone gods that moved. And a massacre that should have ended everything. In his final moments, the System chose him.",
             "voice": "am_adam", "mood": "tense", "transition": "fade"},
            {"id": 4, "type": "static_bg", "background_color": "#050510",
             "overlay_text": "The System has chosen you.", "sub_text": "as its sole Player.",
             "narration": "Arise. The weakest hunter just got his second chance.",
             "voice": "am_adam", "mood": "epic", "transition": "fade"},
        ]
    }


# ─────────────────────────────────────────────────────────────────
#  STEP 3 — IMAGE GENERATION
# ─────────────────────────────────────────────────────────────────

def generate_ai_image(scene: dict, out_path: Path):
    w, h   = RESOLUTION.split("x")
    prompt = scene.get("image_prompt", "Korean manhwa scene, dramatic")
    # Always append manhwa style keywords
    prompt += ", Korean manhwa art style, webtoon, high contrast, dramatic lighting, professional illustration"
    seed   = scene["id"] * 137

    log(f"Scene {scene['id']}: Generating manhwa-style image...", "🎨")

    url = POLLINATIONS.format(prompt=quote(prompt), w=w, h=h, seed=seed)

    for attempt in range(3):
        try:
            r = requests.get(url, timeout=90)
            r.raise_for_status()
            out_path.write_bytes(r.content)
            log(f"Scene {scene['id']}: Image saved ✅", "")
            return
        except Exception as e:
            log(f"Attempt {attempt+1} failed: {e}", "⚠️")
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
        escaped = text.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
        filters.append(
            f"drawtext=fontfile={FONT_PATH}:text='{escaped}':"
            f"fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2-30:"
            f"shadowcolor=black@0.9:shadowx=3:shadowy=3"
        )
    if subtext:
        esc_sub = subtext.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
        filters.append(
            f"drawtext=fontfile={FONT_PATH}:text='{esc_sub}':"
            f"fontcolor=#aaaaaa:fontsize=32:x=(w-text_w)/2:y=(h-text_h)/2+60:"
            f"shadowcolor=black@0.9:shadowx=2:shadowy=2"
        )

    vf  = ",".join(filters) if filters else "null"
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c={color}:size={w}x{h}:rate=1",
        "-vf", vf, "-frames:v", "1", str(out_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    log(f"Scene {scene['id']}: Title card saved ✅", "")


# ─────────────────────────────────────────────────────────────────
#  STEP 4 — AUDIO (KOKORO TTS)
# ─────────────────────────────────────────────────────────────────

def generate_audio(scene: dict, out_path: Path):
    text  = scene.get("narration", "")
    voice = scene.get("voice", "am_adam")

    if not text:
        _silence(2.0, out_path)
        return

    log(f"Scene {scene['id']}: Kokoro TTS — {voice}", "🔊")

    payload = {
        "model": "kokoro", "input": text,
        "voice": voice, "speed": 0.92,
        "response_format": "mp3"
    }

    for attempt in range(3):
        try:
            r = requests.post(KOKORO_URL, json=payload, timeout=90)
            r.raise_for_status()
            out_path.write_bytes(r.content)
            log(f"Scene {scene['id']}: Audio saved ✅", "")
            return
        except Exception as e:
            log(f"Attempt {attempt+1} failed: {e}", "⚠️")
            if attempt == 2:
                _edge_tts_fallback(text, voice, out_path)
                return
            time.sleep(5)


def _edge_tts_fallback(text: str, voice: str, out_path: Path):
    log("Falling back to edge-tts...", "⚠️")
    # Map kokoro voices to edge-tts equivalents
    voice_map = {
        "am_adam":    "en-US-GuyNeural",
        "am_michael": "en-US-ChristopherNeural",
        "af_heart":   "en-US-AriaNeural",
        "af_bella":   "en-US-JennyNeural",
        "bf_emma":    "en-GB-SoniaNeural",
        "bm_george":  "en-GB-RyanNeural",
    }
    edge_voice = voice_map.get(voice, "en-US-GuyNeural")
    tmp = out_path.with_suffix(".tmp.mp3")
    try:
        subprocess.run([
            "edge-tts", "--voice", edge_voice,
            "--text", text, "--write-media", str(tmp)
        ], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-i", str(tmp), str(out_path)],
                       check=True, capture_output=True)
        tmp.unlink(missing_ok=True)
        log("edge-tts fallback succeeded ✅", "")
    except Exception as e:
        log(f"edge-tts also failed: {e} — using silence", "❌")
        _silence(4.0, out_path)


def _silence(duration: float, out_path: Path):
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(duration), str(out_path)
    ], check=True, capture_output=True)


# ─────────────────────────────────────────────────────────────────
#  STEP 5 — BUILD SCENE CLIP (image + Ken Burns + audio)
# ─────────────────────────────────────────────────────────────────

def get_duration(path: Path) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ], capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 4.0


def build_scene_clip(scene: dict, img_path: Path, audio_path: Path, out_path: Path):
    w, h     = RESOLUTION.split("x")
    duration = get_duration(audio_path) + 0.5
    sid      = scene["id"]

    log(f"Scene {sid}: Building clip ({duration:.1f}s)...", "🎬")

    # Ken Burns effect — alternate zoom in / zoom out per scene
    # zoompan filter: slow zoom from 1.0 to 1.08 over the clip duration
    fps      = 25
    frames   = int(duration * fps)
    zoom_dir = "in" if sid % 2 == 0 else "out"

    if zoom_dir == "in":
        zoom_expr = f"'min(zoom+0.0003,1.08)'"
        x_expr    = "iw/2-(iw/zoom/2)"
        y_expr    = "ih/2-(ih/zoom/2)"
    else:
        zoom_expr = f"'if(eq(on,1),1.08,max(zoom-0.0003,1.0))'"
        x_expr    = "iw/2-(iw/zoom/2)"
        y_expr    = "ih/2-(ih/zoom/2)"

    # Build filter chain
    # 1. Scale image larger than frame so Ken Burns has room
    # 2. zoompan for Ken Burns
    # 3. scale to exact output resolution
    # 4. fade in/out
    fade_d = 0.4
    vf = (
        f"scale={int(w)*2}:{int(h)*2}:force_original_aspect_ratio=increase,"
        f"zoompan=z={zoom_expr}:x={x_expr}:y={y_expr}:d={frames}:s={w}x{h}:fps={fps},"
        f"fade=t=in:st=0:d={fade_d},"
        f"fade=t=out:st={duration - fade_d}:d={fade_d}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(fps),
        "-i", str(img_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-t", str(duration),
        "-shortest",
        str(out_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    log(f"Scene {sid}: Clip ready ✅", "")


# ─────────────────────────────────────────────────────────────────
#  STEP 6 — CONCAT ALL CLIPS + MIX BGM
# ─────────────────────────────────────────────────────────────────

def concat_and_mix(clip_paths: list, output_path: Path):
    log("Concatenating all clips...", "🎞️")

    concat_txt = WORK_DIR / "concat.txt"
    with open(concat_txt, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    merged = WORK_DIR / "merged_no_bgm.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_txt),
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(merged)
    ], check=True)

    # Mix BGM if file exists
    if BGM_PATH.exists():
        log("Mixing background music...", "🎵")
        video_dur = get_duration(merged)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(merged),
            "-stream_loop", "-1", "-i", str(BGM_PATH),
            "-filter_complex",
            # BGM at 15% volume, loop to match video length
            f"[1:a]volume=0.15,atrim=0:duration={video_dur}[bgm];"
            "[0:a][bgm]amix=inputs=2:duration=first[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path)
        ]
        subprocess.run(cmd, check=True)
        merged.unlink(missing_ok=True)
    else:
        merged.rename(output_path)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    log(f"Final video: {output_path} ({size_mb:.1f} MB) ✅", "🎉")


# ─────────────────────────────────────────────────────────────────
#  STEP 7 — TELEGRAM NOTIFICATION
# ─────────────────────────────────────────────────────────────────

def notify_telegram(message: str):
    token   = os.environ.get("TG_TOKEN", "")
    user_id = os.environ.get("USER_ID", "")
    if not token or not user_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": user_id, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────
#  MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────

def run(chapter_start: int, chapter_end: int, num_scenes: int):
    setup()
    log(f"{MANGA_TITLE} Recap Pipeline | Ch.{chapter_start}-{chapter_end} | {num_scenes} scenes", "🚀")

    # 1. Fetch plot
    plot_text = fetch_wiki_plot(chapter_start, chapter_end)

    # 2. Generate script via Gemini
    script    = generate_script_with_gemini(plot_text, chapter_start, chapter_end, num_scenes)

    # Save script for debugging
    (WORK_DIR / "generated_script.json").write_text(json.dumps(script, indent=2))
    log("Script saved to workspace/generated_script.json", "💾")

    scenes      = script["scenes"]
    out_name    = script.get("output_filename", f"solo_leveling_ch{chapter_start}_{chapter_end}.mp4")
    output_path = OUTPUT_DIR / out_name
    clip_paths  = []

    for scene in scenes:
        sid       = scene["id"]
        img_path  = SCENES_DIR / f"scene_{sid:03d}.png"
        aud_path  = AUDIO_DIR  / f"scene_{sid:03d}.mp3"
        clip_path = SCENES_DIR / f"scene_{sid:03d}_clip.mp4"

        # Image
        if scene.get("type") == "ai_image":
            generate_ai_image(scene, img_path)
        else:
            generate_static_bg(scene, img_path)

        # Audio
        generate_audio(scene, aud_path)

        # Clip
        build_scene_clip(scene, img_path, aud_path, clip_path)
        clip_paths.append(clip_path)

        time.sleep(1)  # be kind to free APIs

    # Final video
    concat_and_mix(clip_paths, output_path)

    notify_telegram(
        f"✅ <b>{MANGA_TITLE} Ch.{chapter_start}-{chapter_end}</b> recap generated!\n"
        f"📁 File: {out_name}\n"
        f"🎬 Scenes: {len(scenes)}"
    )


# ─────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manhwa Recap Video Generator")
    parser.add_argument("--chapters", default="1-10",
                        help="Chapter range e.g. 1-10 or 11-20 (default: 1-10)")
    parser.add_argument("--scenes",   type=int, default=10,
                        help="Number of scenes to generate (default: 10)")
    args = parser.parse_args()

    try:
        ch_start, ch_end = map(int, args.chapters.split("-"))
    except ValueError:
        print("❌  --chapters must be in format START-END e.g. 1-10")
        sys.exit(1)

    run(ch_start, ch_end, args.scenes)
