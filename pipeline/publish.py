"""Step 4+5: merge EPG sources per feed (T34), build the three public files in OUTDIR.
usage: publish.py WORKDIR OUTDIR [--grab DIR] [--no-net]   (WORKDIR has playlist.json probe.json plan.json + API json)"""
import collections, glob, gzip, importlib.util, json, os, re, sys, time
import xml.etree.ElementTree as ET
from common import *
from epg import read_xmltv, window

MJH = ["PlutoTV", "Plex", "Roku", "SamsungTVPlus"]
SHARE = ["IN1", "UK1", "US2", "AU1", "CA2", "IE1", "DE1", "FR1"]  # epgshare01 per-country files (each < 8 MB gz)
PLUTO = re.compile(r"(?:plu-|pluto\.tv/channels/)([0-9a-f]{24})")


def norm(x):
    return re.sub(r"[^a-z0-9]", "", base_id(x).lower())


def dl(url, path):
    try:
        open(path, "wb").write(get(url, 300))
        return True
    except Exception as e:
        print("download failed", url, e)
        return False


def src_mjh(work, recs, guides, lo, hi):
    """i.mjh.nz guides -> {published channel id: programmes}. A guide row with a feed maps to 'channel@feed' only;
    a Pluto id read from the stream url maps to that exact playlist id (never to the channel's other feeds)."""
    bs = {r["base"] for r in recs}
    want = collections.defaultdict(set)  # xmltv id -> published ids
    for g in guides:
        if g["site"] == "i.mjh.nz" and g["channel"] in bs:
            want[g["site_id"].split("#", 1)[-1]].add(f'{g["channel"]}@{g["feed"]}' if g.get("feed") else g["channel"])
    for r in recs:
        m = PLUTO.search(r["url"]) or PLUTO.search(r["logo"])
        if m:
            want[m.group(1)].add(r["id"])
    got = {}
    for n in MJH:
        p = f"{work}/{n}.xml.gz"
        if dl(f"https://i.mjh.nz/{n}/all.xml.gz", p):
            for cid, progs in read_xmltv(p, set(want), lo, hi).items():
                for k in want[cid]:
                    got.setdefault(k, progs)
    return got


def src_grab(grab_dir, ids, bs, lo, hi):
    """Grabber output -> {channel id as written: programmes}; kept when it is a playlist id or a feed-less base id."""
    got = {}
    for p in sorted(glob.glob(f"{grab_dir}/**/*.xml", recursive=True)):
        try:
            for cid, progs in read_xmltv(p, None, lo, hi).items():
                if cid in ids or (cid in bs):
                    got.setdefault(cid, progs)
        except ET.ParseError as e:
            print("bad grabber file", p, e)
    return got


def src_share(work, missing, lo, hi):
    """epgshare01 knows no feeds: {base id: programmes}, used for main feeds only (see assign)."""
    byn = collections.defaultdict(list)
    for b in missing:
        byn[norm(b)].append(b)
    got = {}
    for n in SHARE:
        p = f"{work}/share_{n}.xml.gz"
        if not dl(f"https://epgshare01.online/epgshare01/epg_ripper_{n}.xml.gz", p):
            continue
        ids = {}  # channel ids present in the file that match a missing playlist channel
        with gzip.open(p, "rb") as f:
            for _, el in ET.iterparse(f, events=("end",)):
                if el.tag == "channel" and norm(el.get("id", "")) in byn:
                    ids[el.get("id")] = norm(el.get("id"))
                if el.tag == "channel":
                    el.clear()
                if el.tag == "programme":
                    break
        for cid, progs in read_xmltv(p, set(ids), lo, hi).items():
            for b in byn[ids[cid]]:
                got.setdefault(b, progs)
    return got


def src_extra(ids, bs, now):
    """Plugin interface: extra_epg/<name>.py exposes fetch(now) -> [{channel_id,start,stop,title}] (start/stop UTC epoch s)."""
    got = {}
    for p in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "extra_epg", "[!_]*.py"))):
        try:
            spec = importlib.util.spec_from_file_location("extra_" + os.path.basename(p)[:-3], p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for r in mod.fetch(now):
                if (r["channel_id"] in ids or r["channel_id"] in bs) and r["stop"] > r["start"]:
                    got.setdefault(r["channel_id"], []).append([int(r["start"]), int(r["stop"]), str(r["title"])[:80]])
        except Exception as e:
            print("extra_epg module failed", p, e)
    return got


def main_ids(recs, feeds):
    """base id -> playlist ids that are the channel's MAIN feed (feeds.json is_main; a feed we have no record of counts as main)."""
    out = collections.defaultdict(list)
    for r in recs:
        f = feeds.get((r["base"], r["id"].partition("@")[2]))
        if f is None or f.get("is_main"):
            out[r["base"]].append(r["id"])
    return out


class Merger:
    """Never shows a different region's schedule. A source row for a playlist id (channel@feed) is used for that feed only.
    A row for a bare base id is a fallback for the channel's MAIN feed, and only if that feed got no guide of its own."""
    def __init__(self, ids, mains):
        self.ids, self.mains, self.merged, self.used, self.pending = ids, mains, {}, {}, []

    def add(self, name, got):
        self.used.setdefault(name, {"channels_added": 0})
        for cid, progs in got.items():
            if not progs:
                continue
            if cid in self.ids:
                if cid not in self.merged:
                    self.merged[cid] = sorted(progs); self.used[name]["channels_added"] += 1
            elif "@" not in cid:
                self.pending.append((name, cid, progs))

    def flush(self):
        for name, cid, progs in self.pending:
            for i in self.mains.get(cid, ()):
                if i not in self.merged:
                    self.merged[i] = sorted(progs); self.used[name]["channels_added"] += 1
        self.pending = []

    def missing_bases(self):
        return {b for b, ms in self.mains.items() if any(i not in self.merged for i in ms)}

    def published(self):
        """Exact keys, plus each channel's base id as an alias of its main feed when that is unambiguous (feed-less ids)."""
        out = {}
        for k, v in self.merged.items():
            out[k] = v
            b = k.partition("@")[0]
            if self.mains.get(b) == [k]:
                out[b] = v
        return out


def main(work, out, grab_dir=None, net=True):
    t0 = time.time()
    now = int(t0)
    lo, hi = window(now)
    recs, probe = load(f"{work}/playlist.json"), load(f"{work}/probe.json")
    ids, bs = {r["id"] for r in recs}, {r["base"] for r in recs if r["base"]}
    feeds = {(f["channel"], f["id"]): f for f in load(f"{work}/feeds.json")}
    m = Merger(ids, main_ids(recs, feeds))
    m.add("extra_epg", src_extra(ids, bs, now))
    if net:
        m.add("i.mjh.nz", src_mjh(work, recs, load(f"{work}/guides.json"), lo, hi))
    if grab_dir and os.path.isdir(grab_dir):
        m.add("iptv-org/epg grabber", src_grab(grab_dir, ids, bs, lo, hi))
    m.flush()
    if net:
        m.add("epgshare01", src_share(work, m.missing_bases(), lo, hi))
        m.flush()
    used = m.used
    merged = m.published()

    today = time.strftime("%Y%m%d", time.gmtime(now))
    chans = [{"u": r["url"], "h": r["h"], "id": r["id"], "s": probe.get(r["h"], "t"), "p": r["p"], "c": today,
              **({"cc": r["cc"]} if r.get("cc") else {}), **({"lg": r["lg"]} if r.get("lg") else {})} for r in recs]
    os.makedirs(out, exist_ok=True)
    for name, obj in (("channels.json.gz", chans), ("epg.json.gz", merged)):
        with gzip.GzipFile(f"{out}/{name}", "wb", 9, mtime=0) as f:
            f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode())
    cnt = collections.Counter(c["s"] for c in chans)
    meta = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "counts": {"alive": cnt["a"], "dead": cnt["d"], "geo": cnt["g"], "timeout": cnt["t"], "total": len(chans)},
        "epg": {"channels_with_epg": len({k.partition("@")[0] for k in m.merged}), "feeds_with_epg": len(m.merged), "playlist_channels": len(bs),
                "coverage_pct": round(100 * len({k.partition("@")[0] for k in m.merged}) / max(1, len(bs)), 1),
                "entries_with_epg_pct": round(100 * sum(r["id"] in m.merged for r in recs) / max(1, len(recs)), 1),
                "window_utc": [lo, hi]},
        "sources": used,
        "probe": load(f"{work}/probe_stats.json") if os.path.exists(f"{work}/probe_stats.json") else {},
        "sizes_gz": {n: os.path.getsize(f"{out}/{n}") for n in ("channels.json.gz", "epg.json.gz")},
        "publish_seconds": round(time.time() - t0),
        "notes": "S: a=alive d=dead(2 days running) g=geo/auth-blocked from the US runner, t=timeout/unknown. epg keys are exact playlist tvg-ids (channel@feed, that feed only); a bare base id is an alias of the main feed. channels cc = broadcast countries when they differ from the id suffix, lg = first feed language.",
    }
    dump(meta, f"{out}/meta.json")
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], a[a.index("--grab") + 1] if "--grab" in a else None, "--no-net" not in a)
