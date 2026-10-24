"""Hiru TV schedule from https://www.hirutv.lk/web_pages/Schedule/Schedule.php (static HTML, Mon-Sun tab panes, 12h Sri Lanka time)."""
import html, re, urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://www.hirutv.lk/web_pages/Schedule/Schedule.php"
UA = "ManusIPTV-data/1.0 (+https://github.com/WAOmaster/manus-iptv-data)"
CHANNEL = "HiruTV.lk"
SL = timezone(timedelta(hours=5, minutes=30))
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_PANE = re.compile(r'<div class="tab-pane[^"]*" id="(\w+)" role="tabpanel">(.*?)(?=<div class="tab-pane|\Z)', re.S)
_ITEM = re.compile(r"<div>(.*?)</div>\s*<span class=\"badge-time\">\s*(\d{1,2}):(\d{2})\s*([AP]M)\s*</span>", re.S)


def parse(page, now):
    """-> programmes for SL-today and SL-tomorrow. now = UTC epoch."""
    panes = {m.group(1): m.group(2) for m in _PANE.finditer(page)}
    today = datetime.fromtimestamp(now, SL).replace(hour=0, minute=0, second=0, microsecond=0)
    starts = []  # (epoch, title)
    for d in (today, today + timedelta(days=1)):
        for t, h, m, ap in _ITEM.findall(panes.get(DAYS[d.weekday()], "")):
            h = int(h) % 12 + (12 if ap == "PM" else 0)
            title = " ".join(html.unescape(re.sub(r"<[^>]+>", "", t)).split())
            if title:
                starts.append((int(d.replace(hour=h, minute=int(m)).timestamp()), title))
    starts = sorted(set(starts))  # the page repeats rows
    out = []
    for i, (a, t) in enumerate(starts):
        b = starts[i + 1][0] if i + 1 < len(starts) else a + 3600
        if b > a:
            out.append({"channel_id": CHANNEL, "start": a, "stop": b, "title": t})
    return out


def fetch(now):
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return parse(r.read().decode("utf-8", "replace"), now)
    except Exception as e:
        print("WARNING hiru:", e)
        return []
