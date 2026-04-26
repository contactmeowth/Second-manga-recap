# 🎬 Panel-Based Manga Recap Pipeline

This is how the big YouTube/Instagram recap channels actually work.
Real manga panels + deep line-by-line AI narration + professional video output.

---

## 📁 Required Folder Structure

```
your-repo/
├── panels/                    ← PUT MANGA PANELS HERE
│   ├── ch01/
│   │   ├── 001.jpg
│   │   ├── 002.jpg
│   │   └── ...
│   ├── ch02/
│   │   ├── 001.jpg
│   │   └── ...
│   └── ch03/
├── panel_pipeline.py
├── audio_gen.py
├── requirements.txt
├── config.txt
├── bgm/
│   └── dramatic.mp3           ← optional background music
└── .github/workflows/
    └── panel_recap.yml
```

Folder names accepted: `ch01`, `ch1`, `chapter01`, `chapter_01`, `01`, `1`

---

## 🖼️ How to Get Manga Panels (Free)

### Option A — Download from any manga reader (simplest)
1. Go to any manga reader site (MangaDex, etc.)
2. Open Chapter 1
3. Right-click each panel → Save Image
4. Name them `001.jpg`, `002.jpg`, etc.
5. Put in `panels/ch01/` folder
6. Push to GitHub

> Takes ~20-30 mins per chapter manually. Or use a browser download extension
> to bulk-save all images on a page.

### Option B — Use a downloader script
Tools like `gallery-dl` can download manga chapters:
```bash
pip install gallery-dl
gallery-dl "https://mangadex.org/chapter/CHAPTER_ID"
```
Then organize into `panels/ch01/` structure.

### Option C — Screenshot the official app
Webtoon app has Solo Leveling officially.
Take screenshots panel by panel → put in panels folder.

---

## 🔄 How the Pipeline Works

```
panels/ch01/001.jpg  ─→  Gemini Vision reads image
                              ↓
                    "Jinwoo stood at the entrance, his
                     hands trembling. After ten years..."
                              ↓
                    Kokoro TTS generates audio (8-15s)
                              ↓
                    FFmpeg: panel + audio + Ken Burns zoom
                              ↓
                         scene clip
                              ↓
panels/ch01/002.jpg  ─→  (same process)

All clips + BGM  ─→  Final long video (20-60 min)
```

**Gemini reads each actual panel image** → writes narration about what's happening in that specific panel → that's what makes it line-by-line accurate.

---

## 🚀 Running on GitHub Actions

### Manual trigger:
1. Actions tab → "Panel Recap Generator" → Run workflow
2. Enter chapter range, format, voice → Run

### Auto trigger:
- Push new panel images to `panels/` → workflow runs automatically
- Or edit `config.txt` and push

---

## ⚙️ Secrets Needed

| Secret | Value |
|--------|-------|
| `KEY1` | Gemini API key (free: aistudio.google.com) |
| `GROQ_KEY` | Groq API key (free: console.groq.com) — fallback |
| `TG_TOKEN` | Telegram bot token |
| `USER_ID` | Your Telegram user ID |

---

## 🎙️ Voice Options

| Voice | Style |
|-------|-------|
| `am_adam` | Deep dramatic male (best for action manga) |
| `am_michael` | Warm male narrator |
| `af_heart` | Warm female narrator |
| `af_bella` | Intense dramatic female |
| `bm_george` | British male (epic tone) |

---

## 💡 Pro Tips

- **5 chapters = ~30-50 min video** depending on panel count
- **Narration cache** — Gemini is only called once per panel. If the run fails and restarts, cached panels are skipped (no double billing)
- **BGM** — add any royalty-free dramatic music as `bgm/dramatic.mp3` — pipeline auto-mixes it at 12% volume
- **Chapter markers** — automatically inserted when chapter number changes
- **Groq fallback** — if Gemini Vision fails, Groq generates context-based narration

---

## ❓ Troubleshooting

| Problem | Fix |
|---------|-----|
| "Panels directory not found" | Create `panels/ch01/` folder with images |
| Gemini fails on panels | Check KEY1 secret, try GROQ_KEY as backup |
| Video too short | Add more chapters or panels |
| Black bars on images | Normal for 9:16 — landscape panels get letterboxed |
| Workflow timeout | Reduce chapter range (5 chapters per run recommended) |
