# AI Changelog

## 2026-10-22 - Allow direct Notion data-source IDs

- Explicit `NOTION_*_DATA_SOURCE_ID` values now bypass the `GET /databases/{database_id}` discovery call; Notion validates the source when the app retrieves or queries it.
- Documented direct data-source configuration and added coverage ensuring meeting-page creation does not call the database endpoint when a source ID is configured.
- Verified with mocked unit tests; no live Notion API calls made.

## 2026-10-22 - Keep Notes property concise

- Changed the Notion database Notes property to contain only the short meeting overview, not the appended action-item list.
- Action items remain available in the meeting page body.
- Added focused tests for the Notes description and fallback. Verified with the unittest suite and Python syntax check.

## 2026-10-22 - Upgrade Notion API to data sources

- Upgraded Notion requests to API version `2026-03-11`; schema retrieval, relation-list queries, and meeting page parents now use data-source IDs.
- Auto-selects a relation's data source (including the existing Attendees database override) and supports optional explicit source IDs for multi-source databases.
- Updated configuration examples, setup instructions, project context, and roadmap. Added cache scoping to discard entries when configured database/source overrides change.
- Added mocked tests for relation source selection, ambiguous database handling, and page creation parents. No live API requests made.

## 2026-10-22 - Ignore generated PyInstaller output

- Added `build/` and `dist/` to `.gitignore` and removed their generated files from Git tracking while preserving local files.
- Documented the generated build-output directories in `docs/PROJECT_CONTEXT.md`.
- No application behavior changed. Validated ignore rules and that local outputs remain present; no tests run.

## 2026-10-22 - Set up repository guidance and project context

- Added `.github/copilot-instructions.md` with project-specific coding, privacy, validation, and documentation rules.
- Added `docs/PROJECT_CONTEXT.md` to document the verified application workflow, modules, configuration, integrations, and data constraints.
- Added `docs/ROADMAP.md`; recorded confirmed current capabilities and left unprovided priorities explicitly undecided.
- No application behavior changed. No tests run; this documentation-only setup did not require validation.
