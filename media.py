"""ffmpeg / ffprobe helpers."""
import shutil
import subprocess
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac"}


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError(
            "ffmpeg/ffprobe not found. Install ffmpeg and make sure it is on your PATH "
            "(Windows: winget install ffmpeg | macOS: brew install ffmpeg | Linux: apt install ffmpeg)."
        )


def find_videos(path: str) -> list[Path]:
    """A file returns [file]; a folder returns every video/audio file inside it (non-recursive)."""
    p = Path(path.strip().strip('"').strip("'")).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Path not found: {p}")
    if p.is_file():
        return [p]
    files = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTS)
    if not files:
        raise FileNotFoundError(f"No video/audio files found in folder: {p}")
    return files


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def extract_audio_chunks(video: Path, out_dir: Path, chunk_seconds: int = 600) -> list[Path]:
    """Mono 16 kHz low-bitrate mp3 chunks (small enough for Groq's 25 MB upload limit)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "chunk_%04d.mp3")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
         "-b:a", "32k", "-f", "segment", "-segment_time", str(chunk_seconds),
         "-reset_timestamps", "1", pattern],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-500:]}")
    chunks = sorted(out_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise RuntimeError("ffmpeg produced no audio (does the file contain an audio track?)")
    return chunks
