"""Loads all settings from the .env file."""
import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _bool(key: str, default: bool) -> bool:
    return _get(key, "true" if default else "false").lower() in ("1", "true", "yes", "on")


def _int(key: str, default: int) -> int:
    try:
        return int(_get(key, str(default)))
    except ValueError:
        return default


def clean_notion_id(value: str) -> str:
    """Accepts a raw ID or a full Notion URL and returns the 32-char ID."""
    if not value:
        return ""
    m = re.findall(r"[0-9a-fA-F]{32}", value.replace("-", ""))
    return m[-1] if m else value


@dataclass
class Settings:
    notion_token: str
    database_id: str
    people_db_id: str
    projects_db_id: str

    prop_title: str
    prop_time: str
    prop_attendees: str
    prop_projects: str
    prop_files: str
    prop_notes: str
    prop_video_link: str

    provider: str  # groq | local
    groq_api_key: str
    groq_whisper_model: str
    local_whisper_model: str
    language: str

    match_model: str    # title + attendees + projects
    summary_model: str  # full summary
    tpm_budget: int     # tokens per minute we allow ourselves per model

    cache_days: int
    timezone: str
    upload_transcript: bool


def load_settings() -> Settings:
    load_dotenv(override=True)
    return Settings(
        notion_token=_get("NOTION_TOKEN"),
        database_id=clean_notion_id(_get("NOTION_DATABASE_ID")),
        people_db_id=clean_notion_id(_get("NOTION_PEOPLE_DB_ID")),
        projects_db_id=clean_notion_id(_get("NOTION_PROJECTS_DB_ID")),
        prop_title=_get("PROP_TITLE", "Title"),
        prop_time=_get("PROP_TIME", "Time finished"),
        prop_attendees=_get("PROP_ATTENDEES", "Attendees"),
        prop_projects=_get("PROP_PROJECTS", "Projects"),
        prop_files=_get("PROP_FILES", "Files & media"),
        prop_notes=_get("PROP_NOTES", "Notes"),
        prop_video_link=_get("PROP_VIDEO_LINK", "Video Link"),
        provider=_get("TRANSCRIBE_PROVIDER", "groq").lower(),
        groq_api_key=_get("GROQ_API_KEY"),
        groq_whisper_model=_get("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"),
        local_whisper_model=_get("LOCAL_WHISPER_MODEL", "small"),
        language=_get("LANGUAGE"),
        match_model=_get("GROQ_MATCH_MODEL", "openai/gpt-oss-20b"),
        summary_model=_get("GROQ_SUMMARY_MODEL", "openai/gpt-oss-120b"),
        tpm_budget=_int("LLM_TPM_BUDGET", 7000),
        cache_days=_int("CACHE_DAYS", 7),
        timezone=_get("TIMEZONE", "Asia/Manila"),
        upload_transcript=_bool("UPLOAD_TRANSCRIPT", True),
    )


def validate(s: Settings) -> list[str]:
    errors = []
    if not s.notion_token:
        errors.append("NOTION_TOKEN is missing in .env")
    if not s.database_id:
        errors.append("NOTION_DATABASE_ID is missing in .env")
    if not s.groq_api_key:
        errors.append("GROQ_API_KEY is missing in .env (needed for the AI summary even in local transcription mode)")
    if s.provider not in ("groq", "local"):
        errors.append("TRANSCRIBE_PROVIDER must be 'groq' or 'local'")
    return errors
