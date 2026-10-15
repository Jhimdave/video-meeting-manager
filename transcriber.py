"""Transcription via Groq Whisper API or local faster-whisper."""
import tempfile
import time
from pathlib import Path

import requests

import media
from config import Settings

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _mmss(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def _retry_after(r: requests.Response, default: float) -> float:
    try:
        return float(r.headers.get("retry-after", ""))
    except ValueError:
        return default


def _groq_transcribe_file(path: Path, s: Settings) -> dict:
    data = {"model": s.groq_whisper_model, "response_format": "verbose_json"}
    if s.language:
        data["language"] = s.language
    for attempt in range(6):
        with open(path, "rb") as fh:
            r = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {s.groq_api_key}"},
                files={"file": (path.name, fh, "audio/mpeg")},
                data=data,
                timeout=600,
            )
        if r.status_code == 429:
            wait = _retry_after(r, 10 * (attempt + 1))
            if wait > 120:
                raise RuntimeError(
                    f"Groq audio limit reached; retry in about {int(wait / 60) + 1} min "
                    "(free tier allows 2 hours of audio per hour), or set TRANSCRIBE_PROVIDER=local."
                )
            time.sleep(wait + 1)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Groq transcription error {r.status_code}: {r.text[:300]}")
        return r.json()
    raise RuntimeError("Groq rate limit hit repeatedly; try again in a minute.")


def _transcribe_groq(video: Path, s: Settings, log) -> list[dict]:
    segments: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        log("Extracting audio with ffmpeg...")
        chunks = media.extract_audio_chunks(video, Path(tmp))
        offset = 0.0
        for i, chunk in enumerate(chunks, 1):
            log(f"Transcribing chunk {i}/{len(chunks)} with Groq Whisper...")
            res = _groq_transcribe_file(chunk, s)
            for seg in res.get("segments") or []:
                text = (seg.get("text") or "").strip()
                if text:
                    segments.append({"start": offset + seg["start"], "end": offset + seg["end"], "text": text})
            if not res.get("segments") and res.get("text"):
                segments.append({"start": offset, "end": offset, "text": res["text"].strip()})
            offset += media.probe_duration(chunk)
    return segments


def _transcribe_local(video: Path, s: Settings, log) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("Local mode needs: pip install -r requirements-local.txt") from e
    log(f"Loading local Whisper model '{s.local_whisper_model}' (first run downloads it)...")
    model = WhisperModel(s.local_whisper_model, device="auto", compute_type="auto")
    log("Transcribing locally (this can take a while on CPU)...")
    seg_iter, _info = model.transcribe(str(video), language=s.language or None, vad_filter=True)
    return [
        {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
        for seg in seg_iter if seg.text.strip()
    ]


def transcribe(video: Path, s: Settings, log) -> str:
    """Returns the timestamped transcript, one '[mm:ss] text' line per segment."""
    segments = _transcribe_groq(video, s, log) if s.provider == "groq" else _transcribe_local(video, s, log)
    if not segments:
        raise RuntimeError("Transcription came back empty (no speech detected?).")
    return "\n".join(f"[{_mmss(sg['start'])}] {sg['text']}" for sg in segments)
