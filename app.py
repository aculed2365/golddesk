"""Gold Desk — receives TradingView alerts, runs the agents, texts you A/A+ calls.

PAPER MODE ONLY: it never places a trade. Plain Python, no extra packages.
Run:  python app.py      (Railway runs this automatically)
"""
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import agents
import config
import db
import risk
import tg
import watcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("desk")
pool = ThreadPoolExecutor(max_workers=6)


def now_dubai() -> datetime:
    return datetime.now(config.DUBAI)


def is_paused() -> bool:
    return db.get_state("paused", "no") == "yes"


def market_open(t: datetime) -> bool:
    """Gold is shut roughly Sat 02:00 -> Mon 02:00 Dubai."""
    wd, h = t.weekday(), t.hour  # Mon=0 ... Sun=6
    if wd == 5 and h >= 2:
        return False
    if wd == 6:
        return False
    if wd == 0 and h < 2:
        return False
    return True


# ----------------------------------------------------------------- the desk
def format_call(alert, plan, radar_report, risk_out, verdict) -> str:
    grade = verdict["grade"]
    lots = risk.lots_for(grade)
    d = plan["direction"].upper()
    dollars = (risk_out.get("risk_per_lot_usd") or 0) * lots
    icon = "🟢" if d == "LONG" else "🔴"
    reasons = "\n".join(f"• {r}" for r in (verdict.get("reasons") or [])[:3])
    tp2 = plan.get("tp2")
    tps = f"{plan['tp1']}" + (f" / {tp2}" if tp2 else "")
    bias = radar_report.get("bias", "?") if isinstance(radar_report, dict) else "?"
    return (
        f"{icon} PAPER CALL — GOLD\n"
        f"ENTER TRADE: {d} {plan['entry']}, {grade}, {lots:g} lots, SL {plan['stop']}, TP {tps}\n"
        f"Strategy: {plan.get('strategy', '')}\n"
        f"Risk: {risk_out.get('stop_points')} pts ≈ ${dollars:,.0f} at {lots:g} lots\n"
        f"Why:\n{reasons}\n"
        f"Kill it if: {verdict.get('watch', '')}\n"
        f"News radar: {bias} — {radar_report.get('bias_reason', '') if isinstance(radar_report, dict) else ''}\n"
        f"⚠️ Paper only — nothing was placed."
    )


def run_desk(alert: dict) -> None:
    run_id = db.new_run(alert)
    try:
        scan = agents.scanner(alert)
        db.note(run_id, "scanner", scan)
        if not scan.get("valid"):
            db.finish(run_id, "noise")
            return

        # setup analyst and the news/big-money radar work at the same time
        f_plan = pool.submit(agents.setup, alert, scan)
        f_radar = pool.submit(agents.radar)
        plan, radar_report = f_plan.result(), f_radar.result()
        db.note(run_id, "setup", plan)
        db.note(run_id, "radar", radar_report)

        risk_out = risk.check(plan, radar_report, now_dubai())
        db.note(run_id, "risk", risk_out)
        if not risk_out["approved"] and plan.get("direction") in (None, "none"):
            db.finish(run_id, "no setup")
            return

        verdict = agents.boss(alert, scan, plan, radar_report, risk_out)
        if not risk_out["approved"]:
            verdict["grade"] = "none"  # code always wins over the AI
        db.note(run_id, "boss", verdict)
        grade = verdict.get("grade", "none")

        if grade in ("A+", "A"):
            msg = format_call(alert, plan, radar_report, risk_out, verdict)
            if is_paused():
                db.finish(run_id, "paused", grade, msg)
            else:
                tg.send(msg)
                db.finish(run_id, "called", grade, msg)
        else:
            db.finish(run_id, "logged", grade)
    except Exception as e:  # noqa: BLE001 - one bad alert never crashes the desk
        log.exception("run %s failed", run_id)
        db.finish(run_id, f"error: {e}")


# -------------------------------------------------- background: radar + summary
def radar_loop() -> None:
    time.sleep(20)
    while True:
        try:
            t = now_dubai()
            if market_open(t) and not is_paused():
                rep = agents.radar(force=True)
                if isinstance(rep, dict) and "error" not in rep:
                    if rep.get("alert_now") and rep.get("alert_text"):
                        key = "news:" + rep["alert_text"][:80].lower()
                        if not db.seen_before(key):
                            tg.send(f"📰 GOLD NEWS ALERT\n{rep['alert_text']}\n"
                                    f"Radar bias: {rep.get('bias', '?')}\n"
                                    f"Big money: {rep.get('big_money', '')}")
                    mins, event = risk.minutes_to_event(rep, t)
                    if mins is not None and 0 < mins <= 35 and event:
                        key = f"warn:{event}:{rep['next_high_impact'].get('time_dubai')}"
                        if not db.seen_before(key):
                            tg.send(f"⏰ {event} in {mins:.0f} min "
                                    f"({rep['next_high_impact'].get('time_dubai')} Dubai). "
                                    f"Be flat 2 min before. No new calls until it's out.")
        except Exception:  # noqa: BLE001
            log.exception("radar loop error")
        time.sleep(max(60, config.RADAR_EVERY_MIN * 60))


def summary_loop() -> None:
    while True:
        try:
            t = now_dubai()
            day_key = t.strftime("%Y-%m-%d")
            if t.hour == config.SUMMARY_HOUR_DUBAI and db.get_state("summary_day") != day_key:
                db.set_state("summary_day", day_key)
                since = (t - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
                runs = db.runs_since(since)
                calls = [r for r in runs if r["status"] == "called"]
                lines = [f"📊 Gold Desk — last 24h (paper)",
                         f"Alerts in: {len(runs)} | Noise: {sum(r['status'] == 'noise' for r in runs)} "
                         f"| Calls sent: {len(calls)}"]
                for r in calls:
                    first = (r["call"] or "").split("\n")[1] if r["call"] else ""
                    lines.append(f"• {r['ts'][11:16]} {first}")
                tg.send("\n".join(lines))
        except Exception:  # noqa: BLE001
            log.exception("summary loop error")
        time.sleep(60)


def checkin() -> None:
    """Every agent does a real job once and reports in on Telegram."""
    def mark(res):
        return "❌ " + str(res.get("error", ""))[:80] if (not isinstance(res, dict) or "error" in res) else "✅"
    sample = dict(SAMPLE_ALERT)
    scan = agents.scanner(sample)
    plan = agents.setup(sample, scan if "error" not in scan else {"valid": True})
    rad = agents.radar(force=True)
    rk = risk.check(plan if isinstance(plan, dict) else {}, rad, now_dubai())
    boss = agents.boss(sample, scan, plan, rad, rk)
    feeds = []
    for name, url in watcher.FEEDS.items():
        try:
            feeds.append(f"{name} feed ✅ ({len(watcher._fetch(url))} items)")
        except Exception as e:  # noqa: BLE001
            feeds.append(f"{name} feed ❌ {str(e)[:60]}")
    radar_line = (f"{rad.get('bias', '?')} — {rad.get('bias_reason', '')}"
                  if isinstance(rad, dict) and "error" not in rad else "")
    nxt = (rad.get("next_high_impact") or {}) if isinstance(rad, dict) else {}
    tg.send("\n".join([
        "🟡 GOLD DESK — AGENT CHECK-IN (paper mode)",
        f"1. Scanner {mark(scan)}",
        f"2. Setup analyst {mark(plan)}",
        f"3. Big Money & World News radar {mark(rad)}",
        f"4. Risk rules ✅ (code)",
        f"5. Boss {mark(boss)}",
        f"6. Trump/news watcher: " + " | ".join(feeds),
        f"Radar read: {radar_line}" if radar_line else "",
        f"Trump: {rad.get('trump', '')}" if isinstance(rad, dict) and rad.get("trump") else "",
        f"Next big release: {nxt.get('event')} {nxt.get('time_dubai')} Dubai" if nxt.get("event") else "",
        "Scanning for: prior-day break+retest, 30-min box, continuation, gold/silver pocket, sweeps.",
    ]).replace("\n\n", "\n").strip())


# ------------------------------------------------------------------ web server
SAMPLE_ALERT = {
    "secret": "", "ticker": "XAUUSD", "tf": "5", "time": "TEST",
    "signals": ["pd_retest_up"], "price": 3895.2,
    "levels": {"pdh": 3890.0, "pdl": 3851.4, "day_hi": 3897.8, "day_lo": 3866.3,
               "box_hi": 3884.1, "box_lo": 3876.9, "h4_swing_hi": 3958.0, "h4_swing_lo": 3842.0,
               "zone_top": 3886.3, "zone_bot": 3866.4, "m15_hi20": 3893.9, "m15_lo20": 3866.3},
    "trend": {"m15": "up", "h4": "up"}, "vol_ratio": 1.6, "size_ratio": 1.4,
    "candles": [[3884.0, 3888.5, 3883.2, 3887.9, 4100], [3887.9, 3891.6, 3886.8, 3891.2, 5200],
                [3891.2, 3892.0, 3888.9, 3889.6, 3900], [3889.6, 3890.4, 3889.1, 3890.2, 3300],
                [3890.2, 3895.6, 3890.0, 3895.2, 6900]],
    "test": True,
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj, indent=2, default=str).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter logs
        log.info("%s %s", self.command, self.path.split("?")[0])

    def _authed(self, q) -> bool:
        return q.get("key", [""])[0] == config.WEBHOOK_SECRET

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/health"):
            return self._send(200, {"ok": True, "desk": "gold", "paper": True,
                                    "paused": is_paused(), "dubai": now_dubai().isoformat()})
        if not self._authed(q):
            return self._send(403, {"error": "wrong key"})
        if u.path == "/stop":
            db.set_state("paused", "yes")
            return self._send(200, {"ok": True, "desk": "PAUSED — no calls until /start"})
        if u.path == "/start":
            db.set_state("paused", "no")
            return self._send(200, {"ok": True, "desk": "RUNNING"})
        if u.path == "/status":
            return self._send(200, {"paused": is_paused(), "runs_last_hour": db.runs_last_hour(),
                                    "market_open": market_open(now_dubai())})
        if u.path == "/calls":
            return self._send(200, db.recent_runs(int(q.get("n", ["30"])[0])))
        if u.path == "/radar":
            return self._send(200, agents.radar(force=True))
        if u.path == "/link":
            return self._send(200, tg.link())
        if u.path == "/checkin":
            pool.submit(checkin)
            return self._send(200, {"ok": True, "note": "agents are checking in — watch Telegram (~1 min)"})
        if u.path == "/test":
            if q.get("telegram", ["0"])[0] == "1":
                ok = tg.send("✅ Gold Desk test message — your phone is connected.")
                return self._send(200, {"telegram_sent": ok})
            pool.submit(run_desk, dict(SAMPLE_ALERT))
            return self._send(200, {"ok": True, "note": "fake alert sent through the desk; check /calls in ~1 min"})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/webhook":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("content-length", 0))
            alert = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "bad json"})
        if alert.get("secret") != config.WEBHOOK_SECRET:
            return self._send(403, {"error": "wrong secret"})
        alert.pop("secret", None)
        if is_paused():
            return self._send(200, {"ok": True, "skipped": "paused"})
        if db.runs_last_hour() >= config.MAX_RUNS_PER_HOUR:
            return self._send(200, {"ok": True, "skipped": "hourly cap"})
        key = f"alert:{alert.get('time')}:{','.join(alert.get('signals') or [])}"
        if db.seen_before(key):
            return self._send(200, {"ok": True, "skipped": "duplicate"})
        pool.submit(run_desk, alert)  # answer TradingView fast, work in background
        return self._send(200, {"ok": True})


def main() -> None:
    threading.Thread(target=radar_loop, daemon=True).start()
    threading.Thread(target=summary_loop, daemon=True).start()
    threading.Thread(target=watcher.watch_loop,
                     args=(lambda: market_open(now_dubai()), is_paused), daemon=True).start()
    port = int(os.getenv("PORT", "8000"))
    log.info("Gold Desk up on port %s (PAPER MODE)", port)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
