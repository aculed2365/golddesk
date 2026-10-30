"""Send a fake TradingView alert to your desk.
Usage:  python test_alert.py https://YOUR-APP.up.railway.app YOUR_SECRET
"""
import json
import sys
import urllib.request

from app import SAMPLE_ALERT

url, secret = sys.argv[1].rstrip("/"), sys.argv[2]
alert = dict(SAMPLE_ALERT, secret=secret, time="TEST-" + __import__("time").strftime("%H%M%S"))
req = urllib.request.Request(url + "/webhook", data=json.dumps(alert).encode(),
                             headers={"content-type": "application/json"})
print(urllib.request.urlopen(req, timeout=15).read().decode())
