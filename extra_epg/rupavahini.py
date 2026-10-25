"""Rupavahini schedule from https://tv.rupavahini.lk/tv-schedule/ (static weekly table, rows tagged data-day, Sri Lanka time)."""
import html, re, urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://tv.rupavahini.lk/tv-schedule/"
UA = "ManusIPTV-data/1.0 (+https://github.com/WAOmaster/manus-iptv-data)"
CHANNEL = "Rupavahini.lk"
SL = timezone(timedelta(hours=5, minutes=30))
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_ROW = re.compile(r'<tr[^>]*data-day="(\w+)"[^>]*>\s*<td>([^<]*)</td>\s*<td>(.*?)</td>', re.S)


def _clock(s):
    """'HH:MM[:SS]', 'HH.MM', '12.30 AM', '24:00' (= next day 00:00) -> seconds after SL midnight, or None."""
    m = re.match(r'\s*(\d{1,2})(?:[:.](\d{2})(?:[:.](\d{2}))?)?(?:\s*([ap])\.?m\.?)?', s, re.I)
    if not m:
        return None
    h, mi, se, ap = int(m[1]), int(m[2] or 0), int(m[3] or 0), (m[4] or "").lower()
    if ap:  # 12-hour clock: 12 AM = 00, 12 PM = 12
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if ap == "p" else 0)
    if h > 24 or mi > 59 or se > 59:
        return None
    return h * 3600 + mi * 60 + se  # 24:13:30 is 00:13:30 of the next day


def parse(page, now):
    """-> programmes for SL-today and SL-tomorrow. now = UTC epoch."""
    rows = []
    for day, t, cell in _ROW.findall(page):
        title = " ".join(html.unescape(re.sub(r"<[^>]+>", "", cell)).split())
        if not title:
            continue
        secs = _clock(html.unescape(t))
        if secs is None:
            print("WARNING rupavahini: skipped unparseable time %r (%s)" % (t, title[:40]))
            continue
        rows.append((day, secs, title))
    today = datetime.fromtimestamp(now, SL).replace(hour=0, minute=0, second=0, microsecond=0)
    starts = []
    for d in (today, today + timedelta(days=1)):
        for day, secs, title in rows:
            if day == DAYS[d.weekday()]:  # secs >= 86400 lands on the next calendar day
                starts.append((int(d.timestamp()) + secs, title))
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
