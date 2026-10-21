import unittest
from unittest.mock import Mock

from config import Settings
from notion import Notion, NotionError, VERSION


def settings(**overrides) -> Settings:
    values = {
        "notion_token": "test-token",
        "database_id": "meeting-db",
        "data_source_id": "",
        "people_db_id": "",
        "people_data_source_id": "",
        "projects_db_id": "",
        "projects_data_source_id": "",
        "prop_title": "Name",
        "prop_time": "Time",
        "prop_attendees": "Attendees",
        "prop_projects": "Projects",
        "prop_files": "Files",
        "prop_notes": "Notes",
        "prop_video_link": "Video Link",
        "provider": "groq",
        "groq_api_key": "",
        "groq_whisper_model": "",
        "local_whisper_model": "",
        "language": "",
        "match_model": "",
        "summary_model": "",
        "tpm_budget": 7000,
        "cache_days": 7,
        "timezone": "UTC",
        "upload_transcript": False,
    }
    values.update(overrides)
    return Settings(**values)


class NotionDataSourceTests(unittest.TestCase):
    def test_uses_relation_data_source_with_legacy_database_override(self):
        notion = Notion(settings(people_db_id="people-db"), log=lambda _: None)
        calls = []

        def request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            if path == "/databases/meeting-db":
                return {"data_sources": [{"id": "meeting-source", "name": "Meetings"}]}
            if path == "/data_sources/meeting-source":
                return {"properties": {
                    "Attendees": {"type": "relation", "relation": {
                        "database_id": "people-db", "data_source_id": "people-source",
                    }},
                }}
            if path == "/databases/people-db":
                return {"data_sources": [{"id": "people-source", "name": "People"}]}
            if path == "/data_sources/people-source":
                return {"properties": {"Name": {"type": "title"}}}
            if path == "/data_sources/people-source/query":
                return {"results": [{
                    "id": "person-page",
                    "properties": {"Name": {"title": [{"plain_text": "Alex"}]}},
                }], "has_more": False}
            self.fail(f"Unexpected Notion request: {method} {path}")

        notion._req = request

        pages = notion.related_pages("Attendees", "people-db")

        self.assertEqual(pages, [{"id": "person-page", "title": "Alex"}])
        self.assertIn(("POST", "/data_sources/people-source/query", {"json": {"page_size": 100}}), calls)
        self.assertNotIn(("POST", "/databases/people-db/query", {"json": {"page_size": 100}}), calls)

    def test_explicit_data_source_skips_database_discovery(self):
        notion = Notion(settings(), log=lambda _: None)
        notion._req = Mock()

        self.assertEqual(notion._resolve_data_source_id("meeting-db", "source-two"), "source-two")
        notion._req.assert_not_called()

    def test_requires_explicit_data_source_for_multi_source_database(self):
        notion = Notion(settings(), log=lambda _: None)
        notion._req = Mock(return_value={"data_sources": [
            {"id": "source-one", "name": "One"},
            {"id": "source-two", "name": "Two"},
        ]})

        with self.assertRaisesRegex(NotionError, "NOTION_DATA_SOURCE_ID"):
            notion._resolve_data_source_id("meeting-db")

        notion._req.assert_called_once_with("GET", "/databases/meeting-db")

    def test_creates_meeting_page_under_data_source(self):
        notion = Notion(settings(data_source_id="meeting-source"), log=lambda _: None)
        requests = []

        def request(method, path, **kwargs):
            requests.append((method, path, kwargs))
            if path == "/data_sources/meeting-source":
                return {"properties": {"Name": {"type": "title"}}}
            if path == "/pages":
                return {"id": "new-page", "url": "https://notion.test/new-page"}
            self.fail(f"Unexpected Notion request: {method} {path}")

        notion._req = request

        url = notion.create_meeting(
            title="Weekly sync",
            date=None,
            attendee_ids=[],
            project_ids=[],
            video_link="",
            notes="",
            file_ids=[],
            overview="",
            sections=[],
            decisions=[],
            action_items=[],
            transcript="Transcript",
        )

        self.assertEqual(url, "https://notion.test/new-page")
        create_request = next(call for call in requests if call[1] == "/pages")
        self.assertEqual(
            create_request[2]["json"]["parent"],
            {"type": "data_source_id", "data_source_id": "meeting-source"},
        )
        self.assertFalse(any(path.startswith("/databases/") for _, path, _ in requests))
        self.assertEqual(VERSION, "2026-03-11")


if __name__ == "__main__":
    unittest.main()
