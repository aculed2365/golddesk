"""All settings come from environment variables (set them in Railway -> Variables)."""
import os
from datetime import timedelta, timezone


def _f(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


DUBAI = timezone(timedelta(hours=4), "Dubai")  # Dubai has no daylight saving

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # your PRIVATE chat, not the public scoreboard

# Models (change any time without touching code)
SCANNER_MODEL = os.getenv("SCANNER_MODEL", "claude-haiku-5-5")
SETUP_MODEL = os.getenv("SETUP_MODEL", "claude-sonnet-5-5")
RADAR_MODEL = os.getenv("RADAR_MODEL", "claude-sonnet-5-5")
BOSS_MODEL = os.getenv("BOSS_MODEL", "claude-opus-5-5")

# Your rules, enforced in code (the AI cannot override these)
LOTS_A = _f("LOTS_A", 4)
LOTS_APLUS = _f("LOTS_APLUS", 6)
MIN_STOP = _f("MIN_STOP", 3)           # noise floor only ($). Real stop = beyond the prior swing high/low
MIN_TP1 = _f("MIN_TP1", 5)             # first target must be MORE than this many $ away
NEWS_BLOCK_BEFORE_MIN = _f("NEWS_BLOCK_BEFORE_MIN", 20)  # no new calls this close to high-impact news
NEWS_BLOCK_AFTER_MIN = _f("NEWS_BLOCK_AFTER_MIN", 2)
MAX_RUNS_PER_HOUR = int(_f("MAX_RUNS_PER_HOUR", 20))     # cost guard
DOLLARS_PER_POINT_PER_LOT = _f("DOLLARS_PER_POINT_PER_LOT", 100)

# Big Money & World News radar
RADAR_EVERY_MIN = _f("RADAR_EVERY_MIN", 15)
RADAR_CACHE_MIN = _f("RADAR_CACHE_MIN", 10)

SUMMARY_HOUR_DUBAI = int(_f("SUMMARY_HOUR_DUBAI", 7))

PAPER_MODE = True  # this build never places real trades

DB_PATH = os.getenv("DB_PATH", "/data/desk.db" if os.path.isdir("/data") else "desk.db")
