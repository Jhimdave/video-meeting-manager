"""Step 1: title + attendees + projects (small model, cached ID lists).
Step 2: full-length summary (big model), chunked so it fits the free-tier tokens-per-minute limit."""
import json

import llm
from config import Settings

CHUNK_CHARS = 9000   # transcript characters per AI call
MERGE_LIMIT = 8000   # max characters of notes handed to the final summary call

MATCH_SYSTEM = """You label a meeting transcript for a Notion database.

You get KNOWN PEOPLE and KNOWN PROJECTS as "id | title" lines, then the transcript (start and end of the meeting).
The transcript has NO speaker labels, so infer who attended from greetings, people addressed by name,
self-introductions and sign-offs. Respond ONLY with JSON:
{"title": "short descriptive meeting title (max 8 words)",
 "attendee_ids": ["id from KNOWN PEOPLE"],
 "project_ids": ["id from KNOWN PROJECTS"]}

Rules:
- Match first names, nicknames and partial names to the closest entry in KNOWN PEOPLE.
- Do NOT include people who were only talked about, only those who took part.
- project_ids: the project(s) the meeting is actually about.
- Use ids copied exactly from the lists. If nobody or nothing matches, return an empty list.
- Write the title in the transcript's language."""

MAP_SYSTEM = """You read ONE part of a longer meeting transcript. Extract everything important, in detail.
Respond ONLY with JSON:
{"key_points": ["complete sentence with names, numbers, dates, tools, reasons"],
 "decisions": ["..."],
 "action_items": ["task - owner (and due date) if mentioned"]}
Do not skip details, do not invent facts. Keep every person's name and project name that appears.
Write in the transcript's language."""

MERGE_SYSTEM = """You merge several JSON notes taken from consecutive parts of one meeting into ONE JSON note
of the same shape: {"key_points": [...], "decisions": [...], "action_items": [...]}.
Remove duplicates, keep names, numbers, dates and reasons. Respond ONLY with JSON."""

REDUCE_SYSTEM = """You write the final, FULL-LENGTH meeting summary. The input is either a meeting transcript
or JSON notes taken from all parts of it. Respond ONLY with JSON:
{"overview": "3-5 sentence overview of the meeting and its outcome",
 "sections": [{"heading": "topic", "points": ["complete, detailed sentence", "..."]}],
 "decisions": ["..."],
 "action_items": ["task - owner (and due date) if mentioned"]}

Rules:
- sections: group ALL important points by topic (3-8 sections). Be thorough: keep names, numbers, dates, tools and
  the reasons behind decisions. Do not drop details to save space.
- Do not invent facts. Write in the input's language."""


def _norm(i: str) -> str:
    return str(i).replace("-", "").strip().lower()


def _pick_ids(returned, candidates: list[dict]) -> list[str]:
    """Keeps only IDs that really exist in the candidate list (a returned title is accepted as fallback)."""
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
    for n in notes:
        if cur and size + len(n) > limit:
            groups.append(cur)
            cur, size = [], 0
        cur.append(n)
        size += len(n)
    if cur:
        groups.append(cur)
    return groups


def identify(transcript: str, fallback_title: str, people: list[dict], projects: list[dict],
             s: Settings, log) -> dict:
    result = {"title": fallback_title, "attendee_ids": [], "project_ids": []}
    try:
        log(f"Identifying title, attendees and projects ({s.match_model})...")
        sample = transcript if len(transcript) <= 8000 else transcript[:6000] + "\n[...]\n" + transcript[-2000:]
        user = f"KNOWN PEOPLE:\n{_lines(people)}\n\nKNOWN PROJECTS:\n{_lines(projects)}\n\nTRANSCRIPT:\n{sample}"
        data = llm.chat_json(s, s.match_model, MATCH_SYSTEM, user, max_out=1500)
        result["title"] = (data.get("title") or fallback_title).strip()
        result["attendee_ids"] = _pick_ids(data.get("attendee_ids"), people)
        result["project_ids"] = _pick_ids(data.get("project_ids"), projects)
    except Exception as e:
        log(f"Title/attendee step failed, using fallback: {e}")
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
                log(f"  reading part {i}/{len(parts)}...")
                data = llm.chat_json(s, s.summary_model, MAP_SYSTEM, part, max_out=2500)
                notes.append(json.dumps(data, ensure_ascii=False))
            for _ in range(4):  # shrink until it fits the final call
                if len(notes) < 2 or sum(len(n) for n in notes) <= MERGE_LIMIT:
                    break
                groups = _group(notes, MERGE_LIMIT)
                if len(groups) == len(notes):
                    break
                log(f"  merging notes ({len(notes)} -> {len(groups)})...")
                notes = [json.dumps(llm.chat_json(s, s.summary_model, MERGE_SYSTEM, "\n".join(g), max_out=2500),
                                    ensure_ascii=False) for g in groups]
            source = "\n".join(notes)

        data = llm.chat_json(s, s.summary_model, REDUCE_SYSTEM, source, max_out=3500, effort="medium")
        sections = []
        for sec in data.get("sections") or []:
            if isinstance(sec, dict) and _strs(sec.get("points")):
                sections.append({"heading": str(sec.get("heading") or "Discussion").strip(),
                                 "points": _strs(sec["points"])})
        result.update({
            "overview": str(data.get("overview") or "").strip(),
            "sections": sections,
            "decisions": _strs(data.get("decisions")),
            "action_items": _strs(data.get("action_items")),
        })
    except Exception as e:  # still create the page with the transcript so work isn't lost
        log(f"AI summary failed, page will contain the transcript only: {e}")
    return result
