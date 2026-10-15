"""Groq chat helper: respects the free-tier tokens-per-minute limit, retries, parses JSON."""
import json
import time

import requests

from config import Settings

CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_window: dict[str, list[tuple[float, int]]] = {}  # model -> [(time, estimated tokens)] of the last 60 s


def _throttle(model: str, tokens: int, budget: int) -> None:
    """Sleeps until this request fits into the per-minute token budget of the model."""
    tokens = min(tokens, budget)
    while True:
        now = time.time()
        recent = [(t, k) for t, k in _window.get(model, []) if now - t < 60]
        _window[model] = recent
        if not recent or sum(k for _, k in recent) + tokens <= budget:
            break
        time.sleep(max(0.5, 60 - (now - recent[0][0]) + 0.5))
    _window[model].append((time.time(), tokens))


def _retry_after(r: requests.Response, default: float) -> float:
    try:
        return float(r.headers.get("retry-after", ""))
    except ValueError:
        return default


def chat(s: Settings, model: str, system: str, user: str, *,
         json_mode: bool = False, max_out: int = 2500, effort: str = "low") -> str:
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "max_completion_tokens": max_out,
        "reasoning_effort": effort,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    estimate = int((len(system) + len(user)) / 3) + max_out  # conservative: ~3 chars per token
    simplified = False
    for attempt in range(8):
        _throttle(model, estimate, s.tpm_budget)
        r = requests.post(CHAT_URL, headers={"Authorization": f"Bearer {s.groq_api_key}"}, json=body, timeout=300)
        if r.status_code == 429:
            wait = _retry_after(r, 15 * (attempt + 1))
            if wait > 120:
                raise RuntimeError(
                    f"Groq limit reached for {model}; retry in about {int(wait / 60) + 1} min "
                    "(daily limit?) or change the model in .env.")
            time.sleep(wait + 1)
            continue
        if r.status_code == 400 and not simplified:
            # the model rejected an optional parameter: retry with the bare minimum
            body.pop("response_format", None)
            body.pop("reasoning_effort", None)
            simplified = True
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Groq error {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"].get("content") or ""
    raise RuntimeError("Groq rate limit hit repeatedly; try again in a minute.")


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a == -1 or b <= a:
            raise
        return json.loads(text[a:b + 1])


def chat_json(s: Settings, model: str, system: str, user: str, **kw) -> dict:
    for attempt in (0, 1):
        text = chat(s, model, system, user, json_mode=True, **kw)
        try:
            return parse_json(text)
        except json.JSONDecodeError:
            if attempt:
                raise
            user += "\n\nReturn ONLY one complete, valid JSON object. Be more concise."
    return {}
