"""The desk's agents. Each one is a Claude call with its own instructions."""
import json
import threading
import time
from datetime import datetime
from pathlib import Path

import config
import db
from llm import ask

PROMPTS = Path(__file__).parent


def _prompt(name: str) -> str:
    text = (PROMPTS / f"prompt_{name}.md").read_text()
    return (text.replace("{PLAYBOOK}", (PROMPTS / "prompt_playbook.md").read_text())
                .replace("{MIN_STOP}", f"{config.MIN_STOP:g}")
                .replace("{MIN_TP1}", f"{config.MIN_TP1:g}"))


def _now_dubai() -> str:
    return datetime.now(config.DUBAI).strftime("%A %Y-%m-%d %H:%M")


def scanner(alert: dict) -> dict:
    return ask(config.SCANNER_MODEL, _prompt("scanner"),
               "ALERT:\n" + json.dumps(alert), max_tokens=300)


def setup(alert: dict, scan: dict) -> dict:
    user = (f"Dubai time now: {_now_dubai()}\nALERT:\n{json.dumps(alert)}\n"
            f"SCANNER said: {json.dumps(scan)}")
    return ask(config.SETUP_MODEL, _prompt("setup"), user, max_tokens=900)


# ---- Big Money & World News radar (cached so every alert doesn't pay for a new search)
_radar_lock = threading.Lock()
_radar_cache = {"ts": 0.0, "data": None}


def radar(force: bool = False) -> dict:
    with _radar_lock:
        age_min = (time.time() - _radar_cache["ts"]) / 60
        if not force and _radar_cache["data"] and age_min < config.RADAR_CACHE_MIN:
            return _radar_cache["data"]
        data = ask(config.RADAR_MODEL, _prompt("radar"),
                   f"Dubai time now: {_now_dubai()}. Run the radar for gold.",
                   max_tokens=8000, search=True)
        if "error" not in data:
            _radar_cache.update(ts=time.time(), data=data)
            db.save_radar(data)
        return data


def boss(alert: dict, scan: dict, plan: dict, radar_report: dict, risk: dict) -> dict:
    user = (f"Dubai time now: {_now_dubai()}\n"
            f"ALERT: {json.dumps(alert)}\nSCANNER: {json.dumps(scan)}\n"
            f"SETUP ANALYST: {json.dumps(plan)}\nRADAR: {json.dumps(radar_report)}\n"
            f"RISK MANAGER (code): {json.dumps(risk)}")
    return ask(config.BOSS_MODEL, _prompt("boss"), user, max_tokens=700)
