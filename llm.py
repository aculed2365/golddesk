"""One helper to ask Claude and get JSON back. Plain Python, no extra packages.
Retries twice, never crashes the desk."""
import json
import logging
import re
import time
import urllib.error
import urllib.request

import config

log = logging.getLogger("desk")

API_URL = "https://api.anthropic.com/v1/messages"
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 6}


def parse_json(text: str) -> dict:
    """Pull the JSON object out of a model reply (handles ```json fences and extra prose)."""
    text = re.sub(r"</?cite[^>]*>", "", text)  # web-search citation tags
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    candidates = [fence.group(1)] if fence else []
    depth, start, blocks = 0, None, []
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                blocks.append(text[start: i + 1])
    candidates += list(reversed(blocks))
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"no JSON in reply: {text[:300]}")


def _post(body: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]!r}") from None


def ask(model: str, system: str, user: str, *, max_tokens: int = 1500,
        search: bool = False) -> dict:
    last_err = None
    for attempt in range(3):  # first try + 2 retries
        try:
            messages = [{"role": "user", "content": user}]
            resp = None
            for _ in range(4):  # a web search turn can pause; continue it
                body = {"model": model, "max_tokens": max_tokens,
                        "system": system, "messages": messages}
                if search:
                    body["tools"] = [WEB_SEARCH_TOOL]
                resp = _post(body, timeout=180 if search else 90)
                if resp.get("stop_reason") == "pause_turn":
                    messages.append({"role": "assistant", "content": resp["content"]})
                    continue
                break
            text = "".join(b.get("text", "") for b in resp.get("content", [])
                           if b.get("type") == "text")
            return parse_json(text)
        except Exception as e:  # noqa: BLE001 - log and retry
            last_err = e
            log.warning("model call failed (%s, try %d): %s", model, attempt + 1, e)
            time.sleep(1.5 * (attempt + 1))
    return {"error": str(last_err)}
