"""Shared helpers. Public data only: nothing here reads secrets or user lists."""
import hashlib, json, os, re, urllib.request

API = "https://iptv-org.github.io/api/"
M3U = "https://iptv-org.github.io/iptv/index.m3u"
UA = "Mozilla/5.0 (X11; Linux x86_64) manus-iptv-data/1.0"


def get(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def base_id(tvg_id):
    """'BBCNews.uk@SD' -> 'BBCNews.uk' (guides.json and the EPG use the base id)."""
    return tvg_id.split("@", 1)[0]


LATAM = {"LATAM", "HISPAM", "CENAMER", "CARIB"}  # iptv-org regions that mean "Latin America" -> pseudo country "latam"
HOME_LANG = {"amh": "et", "orm": "et"}  # Ethiopian-only languages: a US-registered Ethiopian feed lists under Ethiopia


def feed_countries(area, langs):
    """Where a feed is really watched, from feeds.json broadcast_area + languages -> lowercase codes, [] = unknown.
    c/XX -> xx; ct/USNYC and s/US-NY -> us; r/LATAM|HISPAM|CENAMER|CARIB -> 'latam'; other regions are ignored."""
    out = []
    for a in area or []:
        k, _, v = a.partition("/")
        c = v[:2].lower() if k in ("c", "ct", "s") else "latam" if k == "r" and v in LATAM else ""
        if c and c not in out:
            out.append(c)
    home = {HOME_LANG.get(x) for x in langs or []}
    if langs and len(home) == 1 and None not in home and out == ["us"]:
        out = [home.pop()]
    return out


def url_hash(url):
    # shortcut: sha1 truncated to 16 hex chars (64 bits) to keep the file small; fine for ~11k urls.
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def parse_m3u(text):
    """iptv-org playlist (CRLF!) -> list of dicts. Strips \\r, honours EXTVLCOPT UA/referrer."""
    out, cur = [], None
    for line in text.replace("\r", "").split("\n"):
        line = line.strip()
        if line.startswith("#EXTINF"):
            head, _, name = line.rpartition(",")
            cur = {k: v for k, v in ATTR.findall(head)}
            cur["name"] = name.strip()
        elif cur is not None and line.startswith("#EXTVLCOPT:"):
            k, _, v = line[11:].partition("=")
            if k == "http-user-agent":
                cur["http-user-agent"] = v
            elif k == "http-referrer":
                cur["http-referrer"] = v
        elif cur is not None and line and not line.startswith("#"):
            cur["url"] = line
            out.append(cur)
            cur = None
    return out
