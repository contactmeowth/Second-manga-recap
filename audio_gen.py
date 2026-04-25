#!/usr/bin/env python3
"""
audio_gen.py — Kokoro TTS audio generator (properly installed, no fake API)

How Kokoro actually works:
  pip install kokoro soundfile
  apt-get install espeak-ng       ← required for phoneme processing
  Then run locally — no internet needed after install
"""

import os
import sys
import subprocess
import soundfile as sf
from pathlib import Path


# Voice map — Kokoro voice IDs
VOICES = {
    "am_adam":    "am_adam",    # deep US male — good for dramatic narration
    "am_michael": "am_michael", # warm US male
    "af_heart":   "af_heart",   # warm US female
    "af_bella":   "af_bella",   # expressive US female
    "bf_emma":    "bf_emma",    # British female
    "bm_george":  "bm_george",  # British male
}

_pipeline = None   # lazy-load so import doesn't crash if kokoro missing


def _get_pipeline(lang_code: str = "a"):
    """Lazy-load Kokoro pipeline (downloads model ~350MB on first run, cached after)."""
    global _pipeline
    if _pipeline is None:
        try:
            from kokoro import KPipeline
            _pipeline = KPipeline(lang_code=lang_code)
            print("✅  Kokoro pipeline loaded")
        except Exception as e:
            print(f"❌  Kokoro failed to load: {e}")
            return None
    return _pipeline


def generate_audio_kokoro(text: str, voice: str, out_path: Path) -> bool:
    """
    Generate audio using locally installed Kokoro.
    Returns True on success, False on failure.
    """
    pipeline = _get_pipeline()
    if pipeline is None:
        return False

    voice_id = VOICES.get(voice, "am_adam")
    print(f"   🎙️  Kokoro TTS | voice={voice_id} | chars={len(text)}")

    try:
        import soundfile as sf
        import numpy as np

        # Kokoro generates audio in chunks — collect and concatenate
        audio_chunks = []
        generator = pipeline(text, voice=voice_id, speed=0.92)
        for _, _, audio in generator:
            audio_chunks.append(audio)

        if not audio_chunks:
            return False

        # Concatenate all chunks
        full_audio = np.concatenate(audio_chunks)

        # Save as WAV first (soundfile is easier), then convert to MP3 via ffmpeg
        wav_tmp = out_path.with_suffix(".tmp.wav")
        sf.write(str(wav_tmp), full_audio, 24000)  # Kokoro sample rate = 24000

        # Convert WAV → MP3
        subprocess.run([
            "ffmpeg", "-y", "-i", str(wav_tmp),
            "-b:a", "192k", str(out_path)
        ], check=True, capture_output=True)

        wav_tmp.unlink(missing_ok=True)
        print(f"   ✅  Kokoro audio saved: {out_path}")
        return True

    except Exception as e:
        print(f"   ❌  Kokoro generation error: {e}")
        return False


def generate_audio_edgetts(text: str, voice: str, out_path: Path) -> bool:
    """
    Fallback: edge-tts (Microsoft neural voices, free, needs internet).
    Returns True on success, False on failure.
    """
    voice_map = {
        "am_adam":    "en-US-GuyNeural",
        "am_michael": "en-US-ChristopherNeural",
        "af_heart":   "en-US-AriaNeural",
        "af_bella":   "en-US-JennyNeural",
        "bf_emma":    "en-GB-SoniaNeural",
        "bm_george":  "en-GB-RyanNeural",
    }
    edge_voice = voice_map.get(voice, "en-US-GuyNeural")
    tmp_mp3    = out_path.with_suffix(".tmp.mp3")

    print(f"   🔄  edge-tts fallback | voice={edge_voice}")

    try:
        subprocess.run([
            "edge-tts",
            "--voice", edge_voice,
            "--text",  text,
            "--write-media", str(tmp_mp3)
        ], check=True, capture_output=True, timeout=60)

        # Convert to proper MP3 with consistent settings
        subprocess.run([
            "ffmpeg", "-y", "-i", str(tmp_mp3),
            "-b:a", "192k", str(out_path)
        ], check=True, capture_output=True)

        tmp_mp3.unlink(missing_ok=True)
        print(f"   ✅  edge-tts audio saved: {out_path}")
        return True

    except Exception as e:
        print(f"   ❌  edge-tts error: {e}")
        return False


def generate_silence(duration: float, out_path: Path):
    """Last resort: generate silence so pipeline doesn't crash."""
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", str(duration), str(out_path)
    ], check=True, capture_output=True)
    print(f"   ⚠️  Used silence fallback: {out_path}")


def generate_audio(text: str, voice: str, out_path: Path):
    """
    Main function — try Kokoro first, then edge-tts, then silence.
    This is what recap_pipeline.py calls.
    """
    if not text.strip():
        generate_silence(2.0, out_path)
        return

    # Try 1: Kokoro (best quality)
    if generate_audio_kokoro(text, voice, out_path):
        return

    # Try 2: edge-tts (still good, Microsoft neural)
    if generate_audio_edgetts(text, voice, out_path):
        return

    # Try 3: silence (pipeline keeps going at least)
    generate_silence(4.0, out_path)
