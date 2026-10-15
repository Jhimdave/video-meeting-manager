"""Reads transcript files (.txt, .md, .vtt, .srt, .docx) into plain text."""
import html
import re
import zipfile
from pathlib import Path

TRANSCRIPT_EXTS = {".txt", ".md", ".vtt", ".srt", ".docx"}


def find_transcripts(path: str) -> list[Path]:
    """A file returns [file]; a folder returns every transcript file inside it (non-recursive)."""
    p = Path(path.strip().strip('"').strip("'")).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Path not found: {p}")
    if p.is_file():
        return [p]
    files = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in TRANSCRIPT_EXTS)
    if not files:
        raise FileNotFoundError(f"No transcript files (.txt .md .vtt .srt .docx) found in folder: {p}")
    return files


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def _clean_subtitles(text: str) -> str:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        if line.startswith(("NOTE", "Kind:", "Language:")):
            continue
        out.append(re.sub(r"<[^>]+>", "", line))
    return "\n".join(out)


def read_transcript(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".docx":
        text = _read_docx(path)
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if ext in (".vtt", ".srt"):
            text = _clean_subtitles(text)
    text = text.strip()
    if not text:
        raise ValueError("The transcript file is empty.")
    return text
