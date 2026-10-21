# Project Context

## Purpose and stack

Meeting to Notion is a Windows-friendly Python 3.10+ Tkinter desktop app. It processes meeting video/audio, transcribes it, creates a structured AI summary, and writes a meeting page to Notion. The GUI is bundled as a Windows executable with PyInstaller.

## Entry points and workflow

- Source entry point: `app.py`; `python app.py` starts the Tkinter UI.
- Packaged entry point: `MeetingToNotion.spec` bundles the app and `icon.ico`.
- `app.py` loads settings, validates required configuration, and runs `pipeline.run` on a worker thread while displaying log messages.
- `pipeline.py` discovers input media, reuses or creates a transcript in `transcripts/`, removes timestamps for AI processing, identifies title/attendees/projects, summarizes the transcript, and creates a Notion page. The database Notes property gets only the short overview; tasks stay in the page body.
- `media.py` checks for ffmpeg/ffprobe, discovers supported media files in the selected folder (non-recursively), probes duration, and extracts audio chunks.
- `transcriber.py` uses Groq Whisper or optional local `faster-whisper`; `llm.py` handles Groq chat requests, JSON parsing, retries, and per-model token throttling.
- `summarizer.py` identifies meeting metadata and produces overview, sections, decisions, and action items.
- `cache.py` stores Notion people/project IDs and titles in `cache/`, refreshing them after `CACHE_DAYS` or on user request.
- `notion.py` reads database schemas and related pages, uploads transcripts when enabled, and creates meeting pages and body blocks.
- `paths.py` resolves the app data directory for source and PyInstaller execution.

## Configuration and integrations

Configuration is loaded from `.env` via `config.py`. `.env.example` lists the supported variables:

- Notion: `NOTION_TOKEN`, `NOTION_DATABASE_ID`, optional `NOTION_DATA_SOURCE_ID`, `NOTION_PEOPLE_DB_ID`, `NOTION_PROJECTS_DB_ID`, `NOTION_PEOPLE_DATA_SOURCE_ID`, and `NOTION_PROJECTS_DATA_SOURCE_ID`.
- Database property names: `PROP_TITLE`, `PROP_TIME`, `PROP_ATTENDEES`, `PROP_PROJECTS`, `PROP_FILES`, `PROP_NOTES`, `PROP_VIDEO_LINK`.
- Transcription: `TRANSCRIBE_PROVIDER`, `GROQ_WHISPER_MODEL`, `LOCAL_WHISPER_MODEL`, optional `LANGUAGE`.
- Groq AI: `GROQ_API_KEY`, `GROQ_MATCH_MODEL`, `GROQ_SUMMARY_MODEL`, `LLM_TPM_BUDGET`.
- Other: `CACHE_DAYS`, `TIMEZONE`, `UPLOAD_TRANSCRIPT`.

The Notion integration must have access to the Meeting Notes database and databases linked by its Attendees and Projects relations. The app uses Notion API version `2026-03-11`, discovers data sources from database metadata and relation properties by default, and accepts explicit data-source IDs that bypass database-ID discovery. ffmpeg and ffprobe must be installed and available on `PATH`. Local transcription uses the optional dependencies in `requirements-local.txt`; the main dependencies are in `requirements.txt`.

## Data and safety constraints

- `.env` contains credentials and is ignored by Git; `.env.example` is the safe configuration template.
- `cache/` and `transcripts/` contain generated/private user data and are ignored by Git. Do not delete or overwrite these as part of routine changes.
- `build/` and `dist/` contain generated PyInstaller output and are ignored by Git; the spec and source files remain the build inputs.
- Avoid real Notion/Groq requests during validation.
- Focused Notion data-source migration tests live in `tests/` and use mocked API responses. No CI configuration is present.

## Commands

- Install core dependencies: `pip install -r requirements.txt`
- Install optional local transcription dependency: `pip install -r requirements-local.txt`
- Run from source: `python app.py`
- Run unit tests: `python -m unittest discover -s tests -v`
- Build the Windows executable using the existing PyInstaller spec: `pyinstaller MeetingToNotion.spec`
