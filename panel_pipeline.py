#!/usr/bin/env python3
"""
Panel-Based Manga Recap Pipeline
=================================
The REAL way those YouTube recap channels work:
  1. You put manga panel images in panels/ch01/, panels/ch02/ etc.
  2. Gemini reads EACH panel image → writes deep line-by-line narration
  3. Kokoro TTS narrates each panel
  4. Panel image + audio = scene clip (with Ken Burns zoom)
  5. All clips concatenated → final long-form video
  6. BGM mixed underneath

Format: 9:16 (1080x1920) for Instagram/Facebook Reels
        16:9 (1280x720) for YouTube

Usage:
    python panel_pipeline.py                        # reads panels/ folder
    python panel_pipeline.py --chapters 1-5         # only ch01-ch05 subfolders
    python panel_pipeline.py --format youtube       # 16:9 for YouTube
    python panel_pipeline.py --panels-dir mypanels  # custom folder
"""

import os, sys, json, time, base64, argparse, subprocess, requests
from pathlib import Path
from audio_gen import generate_audio

# ── Config ────────────────────────────────────────────────────────
MANGA_TITLE = "Solo Leveling"

FORMATS = {
    "reels":   ("1080x1920", "9:16"),   # Instagram / Facebook / TikTok
    "youtube": ("1280x720",  "16:9"),   # YouTube
}

FONT_PATH  = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_BOLD  = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
WORK_DIR   = Path("workspace")
CLIPS_DIR  = WORK_DIR / "clips"
AUDIO_DIR  = WORK_DIR / "audio"
OUTPUT_DIR = Path("output")
BGM_PATH   = Path("bgm/dramatic.mp3")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def setup():
    for d in [WORK_DIR, CLIPS_DIR, AUDIO_DIR, OUTPUT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def log(msg, icon="▶"):
    print(f"\n{icon}  {msg}", flush=True)

def get_gemini_key():
    return (os.environ.get("GEMINI_API_KEY") or
            os.environ.get("KEY1") or
            os.environ.get("KEY2") or "")

def get_groq_key():
    return (os.environ.get("GROQ_API_KEY") or
            os.environ.get("GROQ_KEY") or "")


# ── Step 1: Collect panel images ──────────────────────────────────

def collect_panels(panels_dir: Path, ch_start: int, ch_end: int) -> list[Path]:
    """
    Collect panel images from panels/ directory.
    
    Expected structure:
        panels/
            ch01/ (or chapter_01/ or 1/)
                001.jpg
                002.jpg
                ...
            ch02/
                001.jpg
                ...
    
    OR flat structure (all panels in one folder):
        panels/
            ch01_page001.jpg
            ch01_page002.jpg
    """
    log(f"Collecting panels from: {panels_dir}", "📁")

    all_panels = []

    if not panels_dir.exists():
        log(f"❌ Panels directory '{panels_dir}' not found!", "❌")
        log("Create a 'panels/' folder and put manga images inside:", "💡")
        log("  panels/ch01/001.jpg, panels/ch01/002.jpg, ...", "💡")
        sys.exit(1)

    # Try subfolder structure first
    subdirs = sorted([d for d in panels_dir.iterdir() if d.is_dir()])

    if subdirs:
        for subdir in subdirs:
            # Extract chapter number from folder name
            # Handles: ch01, ch1, chapter01, chapter_01, 01, 1, etc.
            name = subdir.name.lower()
            for prefix in ["chapter_", "chapter", "ch_", "ch"]:
                name = name.replace(prefix, "")
            try:
                ch_num = int(name.strip("_- "))
            except ValueError:
                continue

            if ch_start <= ch_num <= ch_end:
                pages = sorted([
                    f for f in subdir.iterdir()
                    if f.suffix.lower() in IMAGE_EXTS
                ])
                for page in pages:
                    all_panels.append((ch_num, page))
                log(f"Ch.{ch_num}: {len(pages)} panels found", "✅")
    else:
        # Flat folder — all images together
        pages = sorted([
            f for f in panels_dir.iterdir()
            if f.suffix.lower() in IMAGE_EXTS
        ])
        for i, page in enumerate(pages, 1):
            all_panels.append((1, page))
        log(f"Flat folder: {len(pages)} panels found", "✅")

    if not all_panels:
        log(f"❌ No panel images found in {panels_dir} for chapters {ch_start}-{ch_end}", "❌")
        sys.exit(1)

    log(f"Total panels collected: {len(all_panels)}", "📊")
    return all_panels


# ── Step 2: Gemini reads panel → writes narration ─────────────────

GEMINI_PANEL_SYSTEM = """
You are an expert manga/manhwa narrator for YouTube recap videos.

You will receive a manga panel image. Your job:
1. Look at the image carefully — characters, expressions, actions, text bubbles, setting
2. Write a narration that EXPLAINS what is happening in this panel
3. Style: Deep, immersive storytelling voice — like an excited fan explaining to a friend
4. DO NOT skip anything — explain every important visual and story beat
5. DO NOT just describe what you see literally — interpret the emotion and story significance
6. Length: 2-4 sentences per panel. Enough for 8-15 seconds of audio.
7. If there is dialogue text visible in the panel, incorporate its meaning into your narration
   (don't quote it word for word, explain what it means in context)
8. Make it feel EPIC and engaging — this is for YouTube/Instagram content

Example of BAD narration: "A man is standing in a dungeon holding a sword."
Example of GOOD narration: "Jinwoo stood at the edge of the abyss, blade raised, 
every muscle screaming in protest. This was the moment — the dungeon that had 
killed dozens of hunters before him. But something was different this time. 
HE was different."

Return ONLY the narration text. Nothing else. No labels, no JSON, no explanation.
"""

def image_to_base64(img_path: Path) -> tuple[str, str]:
    """Convert image to base64 for Gemini Vision API."""
    ext = img_path.suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp"}
    mime = mime_map.get(ext, "image/jpeg")
    with open(img_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return data, mime


def narrate_panel_gemini(img_path: Path, ch_num: int, page_num: int, context: str = "") -> str | None:
    """Send panel image to Gemini Vision → get narration text."""
    key = get_gemini_key()
    if not key:
        return None

    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash-latest"]

    img_data, mime_type = image_to_base64(img_path)

    user_prompt = (
        f"This is Chapter {ch_num}, page {page_num} of {MANGA_TITLE}.\n"
        f"{'Previous context: ' + context if context else ''}\n\n"
        f"Write the narration for this panel."
    )

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {
            "system_instruction": {"parts": [{"text": GEMINI_PANEL_SYSTEM}]},
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": mime_type, "data": img_data}},
                    {"text": user_prompt}
                ]
            }],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 512}
        }
        try:
            r = requests.post(url, json=payload, timeout=30)
            r.raise_for_status()
            narration = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            return narration
        except Exception as e:
            log(f"Gemini {model} failed for panel: {e}", "⚠️")
            time.sleep(2)

    return None


def narrate_panel_groq(img_path: Path, ch_num: int, page_num: int, context: str = "") -> str | None:
    """Groq fallback — text only (Groq doesn't support vision), uses filename context."""
    key = get_groq_key()
    if not key:
        return None

    log(f"Groq fallback for Ch.{ch_num} p.{page_num} (no vision — text only)", "⚠️")

    url = "https://api.groq.com/openai/v1/chat/completions"
    prompt = (
        f"Write an engaging 3-sentence narrator script for Chapter {ch_num}, page {page_num} "
        f"of {MANGA_TITLE}. "
        f"{'Previous context: ' + context if context else ''} "
        f"Make it dramatic and immersive. Return ONLY the narration, nothing else."
    )

    try:
        r = requests.post(url,
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 256, "temperature": 0.8},
            headers={"Authorization": f"Bearer {key}"},
            timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"Groq also failed: {e}", "⚠️")
        return None


def narrate_panel(img_path: Path, ch_num: int, page_num: int, context: str = "") -> str:
    """Get narration — try Gemini Vision first, then Groq, then generic fallback."""
    narration = narrate_panel_gemini(img_path, ch_num, page_num, context)
    if narration:
        return narration

    narration = narrate_panel_groq(img_path, ch_num, page_num, context)
    if narration:
        return narration

    # Last resort generic
    return (f"The story continues in Chapter {ch_num}. "
            f"Each panel reveals another layer of this incredible journey, "
            f"drawing us deeper into the world of {MANGA_TITLE}.")


# ── Step 3: Build title card ──────────────────────────────────────

def make_title_card(text: str, sub: str, out_path: Path, resolution: str,
                    bg_color: str = "#000000"):
    w, h = resolution.split("x")
    is_vertical = int(h) > int(w)
    main_size = 90 if is_vertical else 64
    sub_size  = 44 if is_vertical else 32

    filters = []
    if text:
        esc = text.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
        filters.append(
            f"drawtext=fontfile={FONT_BOLD}:text='{esc}':"
            f"fontcolor=white:fontsize={main_size}:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-40:"
            f"shadowcolor=black@0.95:shadowx=4:shadowy=4"
        )
    if sub:
        esc2 = sub.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
        filters.append(
            f"drawtext=fontfile={FONT_PATH}:text='{esc2}':"
            f"fontcolor=#bbbbbb:fontsize={sub_size}:"
            f"x=(w-text_w)/2:y=(h+text_h)/2+30:"
            f"shadowcolor=black@0.9:shadowx=2:shadowy=2"
        )

    vf = ",".join(filters) if filters else "null"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c={bg_color}:size={w}x{h}:rate=1",
        "-vf", vf, "-frames:v", "1", str(out_path)
    ], check=True, capture_output=True)


# ── Step 4: Build scene clip ──────────────────────────────────────

def get_duration(path: Path) -> float:
    r = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except:
        return 4.0


def build_clip(img_path: Path, aud_path: Path, out_path: Path,
               resolution: str, clip_idx: int):
    """Panel image + audio → video clip with Ken Burns zoom."""
    w, h     = resolution.split("x")
    duration = get_duration(aud_path) + 0.4
    fps      = 25
    frames   = int(duration * fps)

    # Alternate zoom in / out for variety
    if clip_idx % 3 == 0:
        zoom = "'min(zoom+0.0002,1.05)'"          # slow zoom in
        px   = "iw/2-(iw/zoom/2)"
        py   = "ih/2-(ih/zoom/2)"
    elif clip_idx % 3 == 1:
        zoom = "'if(eq(on,1),1.05,max(zoom-0.0002,1.0))'"  # slow zoom out
        px   = "iw/2-(iw/zoom/2)"
        py   = "ih/2-(ih/zoom/2)"
    else:
        zoom = "'min(zoom+0.0002,1.05)'"          # pan right while zooming
        px   = "min(iw/2-(iw/zoom/2)+on*0.3, iw-(iw/zoom))"
        py   = "ih/2-(ih/zoom/2)"

    fade_d = 0.25
    vf = (
        f"scale={int(w)*2}:{int(h)*2}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},"
        f"zoompan=z={zoom}:x='{px}':y='{py}':d={frames}:s={w}x{h}:fps={fps},"
        f"fade=t=in:st=0:d={fade_d},"
        f"fade=t=out:st={max(0.1, duration-fade_d)}:d={fade_d}"
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
        err = result.stderr[-500:].decode(errors="replace")
        raise RuntimeError(f"FFmpeg failed for {out_path.name}: {err}")


# ── Step 5: Concat + BGM ──────────────────────────────────────────

def concat_and_mix(clip_paths: list, output_path: Path):
    log(f"Concatenating {len(clip_paths)} clips...", "🎞️")

    txt = WORK_DIR / "concat.txt"
    txt.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths))

    merged = WORK_DIR / "merged.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt),
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(merged)
    ], check=True)

    if BGM_PATH.exists():
        log("Mixing BGM at 12% volume...", "🎵")
        dur = get_duration(merged)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(merged),
            "-stream_loop", "-1", "-i", str(BGM_PATH),
            "-filter_complex",
            f"[1:a]volume=0.12,atrim=0:duration={dur}[bgm];"
            "[0:a][bgm]amix=inputs=2:duration=first[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(output_path)
        ], check=True)
        merged.unlink(missing_ok=True)
    else:
        merged.rename(output_path)

    mb  = output_path.stat().st_size / (1024*1024)
    dur = get_duration(output_path)
    mins = int(dur // 60)
    secs = int(dur % 60)
    log(f"Done! {output_path.name} ({mb:.1f} MB, {mins}m{secs:02d}s) 🎉", "")
    return dur


# ── Telegram ──────────────────────────────────────────────────────

def notify(msg: str):
    token = os.environ.get("TG_TOKEN", "")
    uid   = os.environ.get("USER_ID", "")
    if not token or not uid:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": uid, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except:
        pass


# ── Save/Load narration cache ──────────────────────────────────────

def load_cache() -> dict:
    cache_file = WORK_DIR / "narration_cache.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    return {}

def save_cache(cache: dict):
    cache_file = WORK_DIR / "narration_cache.json"
    cache_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


# ── Main Pipeline ─────────────────────────────────────────────────

def run(panels_dir: Path, ch_start: int, ch_end: int, fmt: str, voice: str):
    setup()
    resolution, aspect = FORMATS.get(fmt, FORMATS["reels"])
    log(f"{MANGA_TITLE} Panel Recap | Ch.{ch_start}-{ch_end} | {resolution} ({aspect})", "🚀")

    # 1. Collect panels
    panels = collect_panels(panels_dir, ch_start, ch_end)

    # 2. Load narration cache (avoid re-calling Gemini for same panels)
    cache = load_cache()

    out_name   = f"solo_leveling_ch{ch_start}_{ch_end}_recap.mp4"
    out_path   = OUTPUT_DIR / out_name
    clip_paths = []
    clip_idx   = 0

    # 3. Intro title card
    log("Generating intro title card...", "🎬")
    intro_img = WORK_DIR / "intro.png"
    make_title_card(
        MANGA_TITLE.upper(),
        f"Chapters {ch_start}–{ch_end} | Full Recap",
        intro_img, resolution, "#000000"
    )
    intro_aud = AUDIO_DIR / "intro.mp3"
    generate_audio(
        f"Welcome to the full recap of {MANGA_TITLE}, chapters {ch_start} through {ch_end}. "
        f"Get ready — this story is about to change everything you know about being the weakest.",
        voice, intro_aud
    )
    intro_clip = CLIPS_DIR / "intro_clip.mp4"
    build_clip(intro_img, intro_aud, intro_clip, resolution, clip_idx)
    clip_paths.append(intro_clip)
    clip_idx += 1

    # 4. Process each panel
    context_window = []  # keep last 2 narrations for context
    narration_log  = []  # save all narrations to JSON

    for panel_idx, (ch_num, img_path) in enumerate(panels):
        page_num = panel_idx + 1
        cache_key = str(img_path)

        log(f"Panel {panel_idx+1}/{len(panels)}: Ch.{ch_num} {img_path.name}", "🖼️")

        # Get narration (from cache or API)
        if cache_key in cache:
            narration = cache[cache_key]
            log("  Using cached narration", "💾")
        else:
            context = " ".join(context_window[-2:])
            narration = narrate_panel(img_path, ch_num, page_num, context)
            cache[cache_key] = narration
            save_cache(cache)

        log(f"  📝 {narration[:80]}...", "")

        narration_log.append({
            "panel": panel_idx + 1,
            "chapter": ch_num,
            "file": img_path.name,
            "narration": narration
        })

        # Update context
        context_window.append(narration[:100])

        # Chapter marker card every time chapter changes
        if panel_idx > 0 and ch_num != panels[panel_idx-1][0]:
            log(f"  Adding chapter {ch_num} marker card...", "🎬")
            marker_img = WORK_DIR / f"ch{ch_num:03d}_marker.png"
            make_title_card(
                f"CHAPTER {ch_num}",
                f"The story continues...",
                marker_img, resolution, "#050010"
            )
            marker_aud = AUDIO_DIR / f"ch{ch_num:03d}_marker.mp3"
            generate_audio(f"Chapter {ch_num}.", voice, marker_aud)
            marker_clip = CLIPS_DIR / f"ch{ch_num:03d}_marker_clip.mp4"
            build_clip(marker_img, marker_aud, marker_clip, resolution, clip_idx)
            clip_paths.append(marker_clip)
            clip_idx += 1

        # Generate audio
        aud_path  = AUDIO_DIR / f"panel_{panel_idx+1:04d}.mp3"
        generate_audio(narration, voice, aud_path)

        # Build clip
        clip_path = CLIPS_DIR / f"panel_{panel_idx+1:04d}_clip.mp4"
        try:
            build_clip(img_path, aud_path, clip_path, resolution, clip_idx)
            clip_paths.append(clip_path)
            clip_idx += 1
        except RuntimeError as e:
            log(f"  Clip failed, skipping: {e}", "⚠️")

        # Small delay to be kind to APIs
        if panel_idx % 5 == 4:
            time.sleep(1)

    # 5. Outro card
    log("Generating outro...", "🎬")
    outro_img = WORK_DIR / "outro.png"
    next_ch   = ch_end + 1
    make_title_card(
        "What happens next?",
        f"Ch.{next_ch} recap coming soon! 🔥",
        outro_img, resolution, "#000000"
    )
    outro_aud = AUDIO_DIR / "outro.mp3"
    generate_audio(
        f"And that's where we leave off for today. The story of {MANGA_TITLE} is far from over. "
        f"Subscribe and hit the notification bell — Chapter {next_ch} recap is coming very soon. "
        f"You do NOT want to miss what happens next.",
        voice, outro_aud
    )
    outro_clip = CLIPS_DIR / "outro_clip.mp4"
    build_clip(outro_img, outro_aud, outro_clip, resolution, clip_idx)
    clip_paths.append(outro_clip)

    # 6. Save narration log
    log_path = WORK_DIR / "narration_log.json"
    log_path.write_text(json.dumps(narration_log, indent=2, ensure_ascii=False))
    log(f"Narration log saved: {log_path}", "💾")

    # 7. Concat + BGM
    total_dur = concat_and_mix(clip_paths, out_path)
    mins = int(total_dur // 60)
    secs = int(total_dur % 60)

    notify(
        f"✅ <b>{MANGA_TITLE} Ch.{ch_start}-{ch_end} Recap</b> done!\n"
        f"📁 {out_name}\n"
        f"🎬 {len(panels)} panels → {len(clip_paths)} clips → {mins}m{secs:02d}s video\n"
        f"📐 Format: {resolution} ({aspect})"
    )


# ── Entry Point ───────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Panel-based manga recap generator")
    p.add_argument("--panels-dir", default="panels",
                   help="Folder containing manga panel images (default: panels/)")
    p.add_argument("--chapters",   default="1-10",
                   help="Chapter range e.g. 1-10 (default: 1-10)")
    p.add_argument("--format",     default="reels",
                   choices=["reels", "youtube"],
                   help="reels=1080x1920, youtube=1280x720 (default: reels)")
    p.add_argument("--voice",      default="am_adam",
                   help="TTS voice (default: am_adam)")
    args = p.parse_args()

    try:
        s, e = map(int, args.chapters.split("-"))
    except:
        print("❌ Use: --chapters 1-10")
        sys.exit(1)

    run(Path(args.panels_dir), s, e, args.format, args.voice)
