"""The full flow: video -> transcript -> title/attendees/projects (cached lists) -> full summary -> Notion page."""
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import cache
import media
import summarizer
import transcriber
from config import Settings
from notion import Notion
from paths import APP_DIR

OUT_DIR = APP_DIR / "transcripts"
TIMESTAMP = re.compile(r"^\[[\d:]+\]\s*", re.M)


def _notes_description(overview: str) -> str:
    return overview.strip() or "See transcript on the page."


def _timezone(tz_name: str):
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return datetime.now().astimezone().tzinfo


def _build_date(video: Path, duration: float, override: str, tz_name: str) -> dict:
    tz = _timezone(tz_name)
    if override.strip():
        end = datetime.strptime(override.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    else:
        end = datetime.fromtimestamp(video.stat().st_mtime, tz)
    if duration >= 60:
        return {"start": (end - timedelta(seconds=duration)).isoformat(), "end": end.isoformat()}
    return {"start": end.isoformat()}


def get_transcript(video: Path, s: Settings, log) -> Path:
    """Transcribes once; later runs reuse the saved file in ./transcripts (saves Groq audio quota)."""
    OUT_DIR.mkdir(exist_ok=True)
    txt = OUT_DIR / f"{video.stem} transcript.txt"
    if txt.exists() and txt.stat().st_size > 0:
        log(f"Reusing saved transcript: {txt.name} (delete it to transcribe again)")
        return txt
    txt.write_text(transcriber.transcribe(video, s, log), encoding="utf-8")
    log(f"Transcript saved: {txt}")
    return txt


def process_video(video: Path, form: dict, s: Settings, notion: Notion,
                  people: list[dict], projects: list[dict], log) -> str:
    log(f"=== {video.name} ===")
    duration = media.probe_duration(video)
    txt_path = get_transcript(video, s, log)
    transcript = txt_path.read_text(encoding="utf-8")
    ai_text = TIMESTAMP.sub("", transcript)  # timestamps only waste tokens

    match = summarizer.identify(ai_text, video.stem, people, projects, s, log)
    title = form.get("title", "").strip() or match["title"]
    names = {p["id"]: p["title"] for p in people + projects}
    log("Attendees: " + (", ".join(names[i] for i in match["attendee_ids"]) or "none identified"))
    log("Projects: " + (", ".join(names[i] for i in match["project_ids"]) or "none identified"))

    summ = summarizer.summarize(ai_text, s, log)
    notes = _notes_description(summ["overview"])

    file_ids = []
    if s.upload_transcript:
        log("Uploading transcript file to Notion...")
        try:
            file_ids.append((txt_path.name, notion.upload_file(txt_path, "text/plain")))
        except Exception as e:
            log(f"Transcript file upload skipped: {e}")

    try:
        date = _build_date(video, duration, form.get("time_finished", ""), s.timezone)
    except Exception as e:
        log(f"Time finished skipped ({e}). Use format YYYY-MM-DD HH:MM")
        date = None

    log("Creating Notion page...")
    url = notion.create_meeting(
        title=title,
        date=_build_date(video, duration, form.get("time_finished", ""), s.timezone),
        attendee_ids=match["attendee_ids"],
        project_ids=match["project_ids"],
        video_link=form.get("video_link", "").strip(),
        notes=notes,
        file_ids=file_ids,
        overview=summ["overview"],
        sections=summ["sections"],
        decisions=summ["decisions"],
        action_items=summ["action_items"],
        transcript=transcript,
    )
    log(f"Done: {url}")
    return url


def run(path: str, form: dict, s: Settings, log) -> list[str]:
    media.require_ffmpeg()
    videos = media.find_videos(path)
    log(f"Found {len(videos)} file(s) to process.")
    notion = Notion(s, log)
    people, projects = cache.get_lists(notion, s, log, force=bool(form.get("refresh_cache")))
    urls = []
    for v in videos:
        try:
            urls.append(process_video(v, form, s, notion, people, projects, log))
        except Exception as e:
            log(f"FAILED {v.name}: {e}")
    return urls
