# Copilot instructions

## Project

This is a Python 3.10+ Tkinter desktop app that transcribes meeting audio/video, creates AI-generated notes, and publishes them to Notion. See [PROJECT_CONTEXT.md](../docs/PROJECT_CONTEXT.md) for verified architecture and setup details.

## Working in this repository

- Keep changes focused and compatible with the existing standard-library-first, module-based design.
- Preserve both source execution (`python app.py`) and the PyInstaller packaging flow (`MeetingToNotion.spec`) when changing startup, paths, or bundled resources.
- Load configuration through `config.Settings`; add or change environment variables in both `.env.example` and `README.md`.
- Keep external service calls behind the existing `Notion`, `llm`, and `transcriber` modules. Do not make real API calls in tests or validation.
- Preserve user data in `.env`, `cache/`, and `transcripts/`. Never read, print, or commit secrets or private meeting content.
- Log recoverable processing errors through the existing `log` callback; avoid silently hiding failures or logging credentials/transcript contents.
- Use type hints and follow the existing naming and formatting patterns. Do not add dependencies without a demonstrated need.
- Run the focused unit suite with `python -m unittest discover -s tests -v`; keep Notion/Groq interactions mocked in tests. For source changes, also run a syntax check on affected modules if needed.

## Documentation

- Keep `README.md` current for user-facing setup and operation.
- Update `docs/PROJECT_CONTEXT.md` when verified architecture, workflow, or configuration changes.
- Update `docs/ROADMAP.md` only when a milestone or priority is confirmed; mark unknown priorities as undecided.
- Add a dated entry to `docs/AI_CHANGELOG.md` for meaningful implementation or setup changes.
