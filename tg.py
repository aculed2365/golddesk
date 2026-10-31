"""Send messages to your private Telegram chat (with sound, so your phone makes a noise)."""
import json
import logging
import urllib.request

import config
import db

log = logging.getLogger("desk")


def _api(method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def chat_id() -> str:
    return config.TELEGRAM_CHAT_ID or db.get_state("tg_chat_id", "")


def link() -> dict:
    """Find the chat of whoever last messaged the bot privately and remember it."""
    if not config.TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}
    updates = _api("getUpdates").get("result", [])
    for u in reversed(updates):
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private":
            db.set_state("tg_chat_id", str(chat["id"]))
            log.warning("TELEGRAM_CHAT_LINK %s", chat["id"])
            send("✅ Gold Desk linked to this chat. Calls and alerts will come here.")
            return {"ok": True, "chat_id": chat["id"],
                    "linked_to": chat.get("first_name", "") or chat.get("username", "")}
    return {"ok": False, "error": "send your bot any message in Telegram first, then try again"}


def send(text: str) -> bool:
    cid = chat_id()
    if not (config.TELEGRAM_BOT_TOKEN and cid):
        log.info("TELEGRAM (not configured):\n%s", text)
        return False
    for attempt in range(3):
        try:
            return _api("sendMessage", {"chat_id": cid, "text": text,
                                        "disable_web_page_preview": True}).get("ok", False)
        except Exception as e:  # noqa: BLE001
            log.warning("telegram send failed (try %d): %s", attempt + 1, e)
    return False
