# Meeting to Notion

Paste the path of a meeting video (or a folder of videos), click one button, and the app:

1. **Transcribes** the recording (Groq Whisper, or local faster-whisper) and saves it in `transcripts/`
2. loads **people and projects** (id + title) from `cache/` - fetched from Notion only once a week
3. asks a small AI model for a **title**, the **attendees** and the **projects** (it returns Notion page IDs)
4. asks a bigger AI model for a **full-length summary** (overview, detailed sections, decisions, action items)
5. creates the page in your **Meeting Notes** database

| Notion property | Filled with |
|---|---|
| Title | your title, or the AI title |
| Time finished | video file date as end time; start = end - video length (shows as a range) |
| Attendees | relation, set from the IDs the AI identified |
| Projects | relation, set from the IDs the AI identified |
| Files & media | the transcript as a `.txt` file |
| Notes | overview + action items |
| Video Link | the URL you type |

The page body gets Overview, Summary (sections with bullets), Decisions, Action items (checkboxes) and the full Transcript.

## The weekly cache

`cache/notion_cache.json` (used by the app) and `cache/notion_cache.md` (readable copy) hold the people and project
titles with their IDs. They refresh automatically after 7 days (`CACHE_DAYS`), when empty, or when you tick
**Refresh Notion cache now** (use it after adding a new person or project). Returned IDs are always checked against
this list, so the AI can never link a page that doesn't exist.

## Setup

1. Python 3.10+ and **ffmpeg** (`winget install ffmpeg` / `brew install ffmpeg` / `apt install ffmpeg`).
2. `pip install -r requirements.txt` (Linux may also need `sudo apt install python3-tk`).
3. Copy `.env.example` to `.env` and fill in `NOTION_TOKEN`, `NOTION_DATABASE_ID`, `GROQ_API_KEY`.
4. In Notion, open the Meeting Notes database > `...` > Connections > add your integration.
   Do the same for the **People** and **Projects** databases, otherwise they can't be read.
5. `python app.py`

## Free-tier notes (Groq)

- gpt-oss models are limited to about 8,000 tokens per minute and 200,000 per day on the free tier, so long meetings
  are summarized in chunks and the app waits between calls (`LLM_TPM_BUDGET`). A 1-hour meeting takes a few minutes
  and roughly 25-30K tokens, so expect around 6 meetings per day.
- Whisper allows about 2 hours of audio per hour. If you hit it, wait or set `TRANSCRIBE_PROVIDER=local`.
- A saved transcript is reused on re-runs, so a failed AI step doesn't cost audio quota again. Delete the `.txt` in
  `transcripts/` to transcribe again.
- Whisper has no speaker labels, so attendees are inferred from names spoken in the meeting (greetings, being
  addressed, sign-offs). Meetings where nobody says names may return no attendees.
- If the AI step fails, the page is still created with the transcript and the log says why.
- Rename properties via `PROP_*` in `.env` if your columns differ. Missing columns are skipped with a log line.
