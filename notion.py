"""Minimal Notion API client (requests only)."""
import time
from pathlib import Path

import requests

from config import Settings

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"
TEXT_LIMIT = 2000


class NotionError(Exception):
    pass


def rich_text(text: str, max_chars: int = 6000) -> list[dict]:
    text = text[:max_chars]
    return [{"type": "text", "text": {"content": text[i:i + TEXT_LIMIT]}} for i in range(0, len(text), TEXT_LIMIT)]


def _paragraphs(text: str) -> list[dict]:
    return [{"object": "block", "type": "paragraph",
             "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[i:i + TEXT_LIMIT]}}]}}
            for i in range(0, len(text), TEXT_LIMIT)]


class Notion:
    def __init__(self, s: Settings, log=print):
        self.s = s
        self.log = log
        self.http = requests.Session()
        self.http.headers.update({"Authorization": f"Bearer {s.notion_token}", "Notion-Version": VERSION})
        self._schemas: dict[str, dict] = {}

    # ---------- low level ----------
    def _req(self, method: str, path: str, **kw) -> dict:
        for _ in range(6):
            r = self.http.request(method, API + path, timeout=120, **kw)
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After", 2)))
                continue
            if r.status_code >= 400:
                raise NotionError(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
            return r.json()
        raise NotionError("Notion rate limit hit repeatedly.")

    def schema(self, db_id: str) -> dict:
        if db_id not in self._schemas:
            self._schemas[db_id] = self._req("GET", f"/databases/{db_id}")
        return self._schemas[db_id]

    def _title_prop(self, db_id: str) -> str:
        for name, p in self.schema(db_id)["properties"].items():
            if p["type"] == "title":
                return name
        raise NotionError(f"Database {db_id} has no title property")

    # ---------- relations ----------
    def related_pages(self, prop_name: str, override_db: str = "") -> list[dict]:
        """Returns every page [{id, title}] of the database a relation column points to."""
        prop = self.schema(self.s.database_id)["properties"].get(prop_name)
        if not prop or prop["type"] != "relation":
            self.log(f"  ! '{prop_name}' is not a relation column in the database - matching skipped")
            return []
        db_id = override_db or prop["relation"]["database_id"]
        try:
            title_prop = self._title_prop(db_id)
            pages, cursor = [], None
            while True:
                body = {"page_size": 100}
                if cursor:
                    body["start_cursor"] = cursor
                res = self._req("POST", f"/databases/{db_id}/query", json=body)
                for p in res["results"]:
                    title = "".join(t.get("plain_text", "") for t in p["properties"][title_prop]["title"]).strip()
                    if title:
                        pages.append({"id": p["id"], "title": title})
                if not res.get("has_more"):
                    break
                cursor = res["next_cursor"]
            return pages
        except NotionError as e:
            self.log(f"  ! could not read the database behind '{prop_name}' "
                     f"(share it with your integration): {e}")
            return []

    # ---------- files ----------
    def upload_file(self, path: Path, content_type: str = "text/plain") -> str:
        created = self._req("POST", "/file_uploads", json={"filename": path.name, "content_type": content_type})
        with open(path, "rb") as fh:
            self._req("POST", f"/file_uploads/{created['id']}/send",
                      files={"file": (path.name, fh, content_type)})
        return created["id"]

    # ---------- the meeting page ----------
    def create_meeting(self, *, title: str, date: dict | None, attendee_ids: list[str], project_ids: list[str],
                       video_link: str, notes: str, file_ids: list[tuple[str, str]],
                       overview: str, sections: list[dict], decisions: list[str],
                       action_items: list[str], transcript: str) -> str:
        s = self.s
        db_props = self.schema(s.database_id)["properties"]
        props: dict = {}

        def has(name: str) -> bool:
            if name not in db_props:
                self.log(f"  ! property '{name}' not found in the database - skipped (check PROP_* in .env)")
                return False
            return True

        props[self._title_prop(s.database_id)] = {"title": rich_text(title, 200)}

        if date and has(s.prop_time):
            props[s.prop_time] = {"date": date}
        for prop_name, ids in ((s.prop_attendees, attendee_ids), (s.prop_projects, project_ids)):
            if ids and has(prop_name):
                if db_props[prop_name]["type"] == "relation":
                    props[prop_name] = {"relation": [{"id": i} for i in ids]}
                else:
                    self.log(f"  ! '{prop_name}' is not a relation column - skipped")
        if file_ids and has(s.prop_files):
            props[s.prop_files] = {"files": [
                {"name": name, "type": "file_upload", "file_upload": {"id": fid}} for name, fid in file_ids]}
        if notes and has(s.prop_notes):
            props[s.prop_notes] = {"rich_text": rich_text(notes)}
        if video_link and has(s.prop_video_link):
            if db_props[s.prop_video_link]["type"] == "url":
                props[s.prop_video_link] = {"url": video_link}
            else:
                props[s.prop_video_link] = {"rich_text": rich_text(video_link)}

        # page body: summary, action items, full transcript
        blocks: list[dict] = []

        def heading(text, level=2):
            key = f"heading_{level}"
            blocks.append({"object": "block", "type": key,
                           key: {"rich_text": [{"type": "text", "text": {"content": text[:200]}}]}})

        def bullet(text):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": rich_text(text, 1900)}})

        if overview:
            heading("Overview")
            blocks += _paragraphs(overview)
        if sections:
            heading("Summary")
            for sec in sections:
                heading(sec["heading"], 3)
                for point in sec["points"]:
                    bullet(point)
        if decisions:
            heading("Decisions")
            for d in decisions:
                bullet(d)
        if action_items:
            heading("Action items")
            for item in action_items:
                blocks.append({"object": "block", "type": "to_do",
                               "to_do": {"rich_text": rich_text(item, 1900), "checked": False}})
        heading("Transcript")
        blocks += _paragraphs(transcript)

        page = self._req("POST", "/pages", json={
            "parent": {"database_id": s.database_id}, "properties": props, "children": blocks[:100]})
        rest = blocks[100:]
        for i in range(0, len(rest), 100):
            self._req("PATCH", f"/blocks/{page['id']}/children", json={"children": rest[i:i + 100]})
        return page.get("url", "")
