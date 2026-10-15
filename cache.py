"""Weekly cache of the People / Projects pages (id + title) so we don't query Notion for every meeting.

Files (in ./cache):
  notion_cache.json  - what the app reads
  notion_cache.md    - same data in a human-readable list
A list is refreshed when it is older than CACHE_DAYS (default 7), when it is empty, when the
Meeting Notes database changed, or when you tick "Refresh Notion cache now" in the UI.
"""
import json
import time
from datetime import datetime
from pathlib import Path

from config import Settings

CACHE_DIR = Path(__file__).parent / "cache"
JSON_FILE = CACHE_DIR / "notion_cache.json"
MD_FILE = CACHE_DIR / "notion_cache.md"


def _load() -> dict:
    try:
        return json.loads(JSON_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _save(data: dict, days: int) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    JSON_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Notion cache", "", f"_Refreshes automatically after {days} days._", ""]
    for key, title in (("people", "People (Attendees)"), ("projects", "Projects")):
        entry = data.get(key) or {}
        lines.append(f"## {title}")
        if entry.get("fetched_at"):
            lines.append(f"_Updated {_stamp(entry['fetched_at'])}_")
        lines.append("")
        lines += [f"- {i['title']} - `{i['id']}`" for i in entry.get("items", [])]
        lines.append("")
    MD_FILE.write_text("\n".join(lines), encoding="utf-8")


def get_lists(notion, s: Settings, log, force: bool = False) -> tuple[list[dict], list[dict]]:
    data = _load()
    if data.get("meeting_db") != s.database_id:
        data = {"meeting_db": s.database_id}
    now = time.time()
    changed = False
    out = {}
    for key, prop, override in (("people", s.prop_attendees, s.people_db_id),
                                ("projects", s.prop_projects, s.projects_db_id)):
        entry = data.get(key) or {}
        items = entry.get("items") or []
        age_days = (now - entry.get("fetched_at", 0)) / 86400
        if items and not force and age_days < s.cache_days:
            log(f"Using cached {key}: {len(items)} (updated {_stamp(entry['fetched_at'])})")
        else:
            log(f"Refreshing {key} from Notion...")
            items = notion.related_pages(prop, override)
            if items:
                data[key] = {"fetched_at": now, "items": items}
                changed = True
                log(f"  {len(items)} {key} cached")
        out[key] = items
    if changed:
        _save(data, s.cache_days)
    return out["people"], out["projects"]
