"""Rupavahini schedule from https://tv.rupavahini.lk/tv-schedule/ (static weekly table, rows tagged data-day, 24h Sri Lanka time)."""
import html, re, urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://tv.rupavahini.lk/tv-schedule/"
UA = "ManusIPTV-data/1.0 (+https://github.com/WAOmaster/manus-iptv-data)"
CHANNEL = "Rupavahini.lk"
SL = timezone(timedelta(hours=5, minutes=30))
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_ROW = re.compile(r'<tr data-day="(\w+)"><td>(\d{1,2}):(\d{2}):(\d{2})</td><td>(.*?)</td>')


def parse(page, now):
    """-> programmes for SL-today and SL-tomorrow. now = UTC epoch."""
    rows = _ROW.findall(page)
    today = datetime.fromtimestamp(now, SL).replace(hour=0, minute=0, second=0, microsecond=0)
    starts = []
    for d in (today, today + timedelta(days=1)):
        for day, h, m, s, t in rows:
            title = " ".join(html.unescape(re.sub(r"<[^>]+>", "", t)).split())
            if day == DAYS[d.weekday()] and title:
                starts.append((int(d.replace(hour=int(h), minute=int(m), second=int(s)).timestamp()), title))
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
        print("WARNING rupavahini:", e)
        return []
