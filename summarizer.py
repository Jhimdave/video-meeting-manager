
import json

import llm
from config import Settings

CHUNK_CHARS = 9000
MERGE_LIMIT = 8000

MATCH_SYSTEM = """Identify the meeting title, actual attendees, and relevant projects.
Use the provided known people and project IDs.
Do not include people only mentioned in the discussion.
Respond ONLY with JSON:
{"title": "short title", "attendee_ids": [], "project_ids": []}
Use exact IDs from the lists. Write in the transcript's language."""

MAP_SYSTEM = """Extract only important meeting information.
Respond ONLY with JSON:
{"key_points": [], "decisions": [], "action_items": []}
Include:
- What was completed and current progress.
- Important URLs, applications, tools, platforms, and technical details.
- Confirmed decisions and blockers.
- Concrete task titles only; do not include owners or deadlines in action items.
Keep points short. Preserve exact URLs and important names, numbers, and dates.
Remove small talk, repetition, and irrelevant details. Never invent facts.
Write in the transcript's language."""

MERGE_SYSTEM = """Merge meeting notes into one JSON object:
{"key_points": [], "decisions": [], "action_items": []}
Remove duplicates and irrelevant details. Preserve important facts, exact URLs,
tools, names, decisions, and action items. Do not invent facts.
Keep action items as task titles only; omit owners and deadlines.
Respond ONLY with JSON."""

REDUCE_SYSTEM = """Create a short, practical meeting summary.
Respond ONLY with JSON:
{
  "overview": "2 short sentences describing the meeting and outcome",
  "sections": [
    {"heading": "Completed / Discussed", "points": []},
    {"heading": "Important Information", "points": []}
  ],
  "decisions": [],
  "action_items": []
}
Include only:
- What was done and the current status.
- Important URLs, applications, tools, and data to remember.
- Confirmed decisions.
- Titles only for tasks that still need to be done; do not include owners or deadlines.
Use short bullet points. Omit empty sections.
Avoid repetition, small talk, and unnecessary explanations.
Preserve exact URLs and important technical details. Never invent facts.
Write in the input's language."""


def _norm(i: str) -> str:
    return str(i).replace("-", "").strip().lower()


def _pick_ids(returned, candidates: list[dict]) -> list[str]:
    by_id = {_norm(c["id"]): c["id"] for c in candidates}
    by_title = {c["title"].strip().lower(): c["id"] for c in candidates}
    out = []
    for item in returned or []:
        cid = by_id.get(_norm(item)) or by_title.get(str(item).strip().lower())
        if cid and cid not in out:
            out.append(cid)
    return out


def _lines(items: list[dict]) -> str:
    return "\n".join(f"{c['id']} | {c['title']}" for c in items) or "(none)"


def _strs(value) -> list[str]:
    return [str(v).strip() for v in (value or []) if str(v).strip()]


def _action_item_titles(value) -> list[str]:
    titles = []
    for item in value or []:
        if isinstance(item, dict):
            item = item.get("task") or item.get("title")
        if isinstance(item, str) and item.strip():
            titles.append(item.strip())
    return titles


def _split(text: str, limit: int) -> list[str]:
    parts, cur, size = [], [], 0
    for line in text.splitlines():
        if cur and size + len(line) > limit:
            parts.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        parts.append("\n".join(cur))
    return parts


def _group(notes: list[str], limit: int) -> list[list[str]]:
    groups, cur, size = [], [], 0
    for note in notes:
        if cur and size + len(note) > limit:
            groups.append(cur)
            cur, size = [], 0
        cur.append(note)
        size += len(note)
    if cur:
        groups.append(cur)
    return groups


def identify(transcript: str, fallback_title: str, people: list[dict],
             projects: list[dict], s: Settings, log) -> dict:
    result = {"title": fallback_title, "attendee_ids": [], "project_ids": []}
    try:
        log(f"Identifying meeting ({s.match_model})...")
        sample = transcript if len(transcript) <= 8000 else transcript[:6000] + "\n[...]\n" + transcript[-2000:]
        user = f"KNOWN PEOPLE:\n{_lines(people)}\n\nKNOWN PROJECTS:\n{_lines(projects)}\n\nTRANSCRIPT:\n{sample}"
        data = llm.chat_json(s, s.match_model, MATCH_SYSTEM, user, max_out=1500)
        result["title"] = (data.get("title") or fallback_title).strip()
        result["attendee_ids"] = _pick_ids(data.get("attendee_ids"), people)
        result["project_ids"] = _pick_ids(data.get("project_ids"), projects)
    except Exception as e:
        log(f"Meeting identification failed: {e}")
    return result


def summarize(transcript: str, s: Settings, log) -> dict:
    result = {"overview": "", "sections": [], "decisions": [], "action_items": []}
    try:
        log(f"Summarizing ({s.summary_model})...")
        if len(transcript) <= CHUNK_CHARS:
            source = transcript
        else:
            parts = _split(transcript, CHUNK_CHARS)
            notes = []
            for i, part in enumerate(parts, 1):
                log(f"Reading part {i}/{len(parts)}...")
                data = llm.chat_json(s, s.summary_model, MAP_SYSTEM, part, max_out=1500)
                notes.append(json.dumps(data, ensure_ascii=False))

            for _ in range(4):
                if len(notes) < 2 or sum(len(n) for n in notes) <= MERGE_LIMIT:
                    break
                groups = _group(notes, MERGE_LIMIT)
                if len(groups) == len(notes):
                    break
                log(f"Merging notes ({len(notes)} -> {len(groups)})...")
                notes = [
                    json.dumps(
                        llm.chat_json(s, s.summary_model, MERGE_SYSTEM, "\n".join(group), max_out=1500),
                        ensure_ascii=False
                    )
                    for group in groups
                ]
            source = "\n".join(notes)

        data = llm.chat_json(s, s.summary_model, REDUCE_SYSTEM, source, max_out=2000, effort="medium")
        sections = []
        for sec in data.get("sections") or []:
            if isinstance(sec, dict) and _strs(sec.get("points")):
                sections.append({
                    "heading": str(sec.get("heading") or "Discussion").strip(),
                    "points": _strs(sec["points"])
                })

        result.update({
            "overview": str(data.get("overview") or "").strip(),
            "sections": sections,
            "decisions": _strs(data.get("decisions")),
            "action_items": _action_item_titles(data.get("action_items"))
        })
    except Exception as e:
        log(f"Summary failed; transcript will be retained: {e}")
    return result
