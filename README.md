# 🎬 Solo Leveling — Manhwa Recap Pipeline

Fully automated YouTube recap video generator. No manual downloads, no paid APIs.  
Just push → GitHub Actions does everything → download your video.

---

## 🔄 How It Works (Zero Manual Work)

```
Push chapters.txt
      ↓
GitHub Actions wakes up
      ↓
Fetches plot from Fandom wiki automatically (no downloads needed)
      ↓
Gemini reads plot → writes scene-by-scene narration script
      ↓
Pollinations AI generates manhwa-style art per scene (FREE, no API key)
      ↓
Kokoro TTS narrates each scene (edge-tts fallback if Kokoro is down)
      ↓
FFmpeg: image + Ken Burns zoom effect + audio → scene clip
      ↓
All clips merged + background music mixed in
      ↓
Final MP4 uploaded as GitHub Artifact + Telegram notification sent
```

---

## 📁 Repo Structure

```
manhwa-recap/
├── recap_pipeline.py          ← main script (do not edit)
├── chapters.txt               ← YOU edit this to trigger new videos
├── requirements.txt           ← pip packages (just 2)
├── bgm/
│   └── dramatic.mp3           ← optional background music
├── output/                    ← generated videos land here
└── .github/
    └── workflows/
        └── recap.yml          ← GitHub Actions workflow
```

---

## 🚀 How to Generate a New Video

### Option A — Push chapters.txt (simplest)
```
Edit chapters.txt:
  Line 1: chapter range  →  11-20
  Line 2: scene count    →  12

Then:
  git add chapters.txt
  git commit -m "generate ch11-20"
  git push
```
Actions runs automatically. Get Telegram notification when done.

### Option B — Manual trigger from GitHub UI
1. Go to your repo → **Actions** tab
2. Click **"Manhwa Recap Generator"**
3. Click **"Run workflow"**
4. Enter chapter range (e.g. `11-20`) and scene count
5. Click **Run workflow**

---

## ⚙️ GitHub Secrets Required

Go to: `Settings → Secrets and variables → Actions → New repository secret`

| Secret | What it is |
|--------|-----------|
| `KEY1` | Your Gemini API key (free at aistudio.google.com) |
| `KEY2` | Backup Gemini key (optional) |
| `TG_TOKEN` | Telegram bot token |
| `USER_ID` | Your Telegram chat/user ID |

---

## 🎵 Adding Background Music (Optional)

1. Find a free dramatic/epic music track (e.g. from Pixabay, Free Music Archive)
2. Save it as `bgm/dramatic.mp3` in your repo
3. Push — pipeline auto-mixes it at 15% volume under the narration

Without the BGM file, the pipeline still works — just no music.

---

## 🎙️ Voice Options

Change `"voice"` in generated scenes. Gemini picks automatically but you can override:

| Voice | Style |
|-------|-------|
| `am_adam` | Deep male narrator (default for Solo Leveling) |
| `am_michael` | Warmer male voice |
| `af_heart` | Warm female |
| `af_bella` | Dramatic female |
| `bm_george` | British male |

---

## 💡 Tips

- **More scenes = longer video** — set scenes to 15-20 for 5-10 minute videos
- **Ken Burns effect** alternates zoom-in / zoom-out between scenes automatically
- **Gemini script is saved** to `workspace/generated_script.json` after each run — visible in Action logs
- **No internet data on your end** — everything runs on GitHub's servers (2,000 free minutes/month)
- **Chapter range drives everything** — Gemini figures out what happened in those chapters from the wiki

---

## ❓ Troubleshooting

| Problem | Fix |
|---------|-----|
| `KEY1 not set` | Add Gemini API key to repo secrets |
| Kokoro TTS fails | Pipeline auto-falls back to edge-tts |
| Image generation slow | Normal — Pollinations can take 30-60s per image |
| Video not in artifacts | Check Actions logs for the error |
| FFmpeg font error | The workflow installs `fonts-dejavu-core` automatically |
