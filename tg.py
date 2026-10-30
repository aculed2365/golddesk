"""Send messages to your private Telegram chat (with sound, so your phone makes a noise)."""
import json
import logging
import urllib.request

import config

log = logging.getLogger("desk")


def send(text: str) -> bool:
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        log.info("TELEGRAM (not configured):\n%s", text)
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": config.TELEGRAM_CHAT_ID, "text": text,
                       "disable_web_page_preview": True}).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read()).get("ok", False)
        except Exception as e:  # noqa: BLE001
            log.warning("telegram send failed (try %d): %s", attempt + 1, e)
    return False
