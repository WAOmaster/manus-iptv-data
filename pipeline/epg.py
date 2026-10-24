"""XMLTV helpers: streaming parse, window filter, per-source collectors. All times -> UTC epoch seconds."""
import gzip, re, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone

TITLE_MAX = 80
_TS = re.compile(r"^(\d{14})\s*([+-]\d{4})?")


def parse_ts(s):
    m = _TS.match(s or "")
    if not m:
        return None
    dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    off = m.group(2) or "+0000"
    sign = 1 if off[0] == "+" else -1
    secs = sign * (int(off[1:3]) * 3600 + int(off[3:5]) * 60)
    return int(dt.replace(tzinfo=timezone.utc).timestamp()) - secs


def read_xmltv(path, wanted, lo, hi):
    """Stream an XMLTV file (.gz or plain). wanted: set of channel ids, or None=all.
    Returns {channel_id: [[start,stop,title],...]} for programmes overlapping [lo,hi]."""
    out = {}
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as f:
        for _, el in ET.iterparse(f, events=("end",)):
            if el.tag != "programme":
                if el.tag == "channel":
                    el.clear()
                continue
            cid = el.get("channel")
            if wanted is None or cid in wanted:
                a, b = parse_ts(el.get("start")), parse_ts(el.get("stop"))
                t = el.findtext("title")
                if a and b and t and b > lo and a < hi:
                    out.setdefault(cid, []).append([a, b, " ".join(t.split())[:TITLE_MAX]])
            el.clear()
    return out


def window(now=None):
    now = now or int(time.time())
    return now - 2 * 3600, now + 30 * 3600
