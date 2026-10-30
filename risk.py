"""Risk manager: hard rules in plain code. The AI cannot talk its way past these."""
from datetime import datetime

import config


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def minutes_to_event(radar: dict, now: datetime):
    ev = (radar or {}).get("next_high_impact") or {}
    t = ev.get("time_dubai") if isinstance(ev, dict) else None
    if not t:
        return None, None
    try:
        when = datetime.strptime(t.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=config.DUBAI)
    except ValueError:
        return None, ev.get("event")
    return (when - now).total_seconds() / 60, ev.get("event")


def check(plan: dict, radar: dict, now: datetime) -> dict:
    vetoes = []
    direction = (plan or {}).get("direction")
    entry, stop, tp1, tp2 = (_num(plan.get(k)) for k in ("entry", "stop", "tp1", "tp2"))

    if direction not in ("long", "short"):
        vetoes.append("no trade direction")
    elif None in (entry, stop, tp1):
        vetoes.append("missing entry/stop/target")
    else:
        if direction == "long" and not (stop < entry < tp1):
            vetoes.append("long levels out of order (need stop < entry < TP1)")
        if direction == "short" and not (tp1 < entry < stop):
            vetoes.append("short levels out of order (need TP1 < entry < stop)")
        if abs(entry - stop) < config.MIN_STOP:
            vetoes.append(f"stop too tight ({abs(entry - stop):.1f} < {config.MIN_STOP:g})")
        if abs(tp1 - entry) <= config.MIN_TP1:
            vetoes.append(f"TP1 too close ({abs(tp1 - entry):.1f} <= {config.MIN_TP1:g})")

    if str(plan.get("candle_check", "")).lower() != "pass":
        vetoes.append("candle check failed")

    mins, event = minutes_to_event(radar, now)
    if mins is not None and -config.NEWS_BLOCK_AFTER_MIN <= mins <= config.NEWS_BLOCK_BEFORE_MIN:
        vetoes.append(f"high-impact news window: {event} ({mins:+.0f} min)")

    stop_pts = abs(entry - stop) if entry is not None and stop is not None else None
    return {
        "approved": not vetoes,
        "vetoes": vetoes,
        "stop_points": round(stop_pts, 2) if stop_pts is not None else None,
        "risk_per_lot_usd": round(stop_pts * config.DOLLARS_PER_POINT_PER_LOT) if stop_pts else None,
        "lots_if_A": config.LOTS_A,
        "lots_if_A+": config.LOTS_APLUS,
    }


def lots_for(grade: str) -> float:
    return config.LOTS_APLUS if grade == "A+" else config.LOTS_A
