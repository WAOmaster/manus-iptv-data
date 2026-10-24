"""Step 4+5: merge EPG sources, build the three public files in OUTDIR.
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
    want = collections.defaultdict(set)  # xmltv id -> playlist base ids
    for g in guides:
        if g["site"] == "i.mjh.nz" and g["channel"] in bases(recs):
            want[g["site_id"].split("#", 1)[-1]].add(g["channel"])
    for r in recs:
        m = PLUTO.search(r["url"]) or PLUTO.search(r["logo"])
        if m:
            want[m.group(1)].add(r["base"])
    got = {}
    for n in MJH:
        p = f"{work}/{n}.xml.gz"
        if dl(f"https://i.mjh.nz/{n}/all.xml.gz", p):
            for cid, progs in read_xmltv(p, set(want), lo, hi).items():
                for b in want[cid]:
                    got.setdefault(b, progs)
    return got


def src_grab(grab_dir, bs, lo, hi):
    got = {}
    for p in sorted(glob.glob(f"{grab_dir}/**/*.xml", recursive=True)):
        try:
            for cid, progs in read_xmltv(p, None, lo, hi).items():
                if base_id(cid) in bs:
                    got.setdefault(base_id(cid), progs)
        except ET.ParseError as e:
            print("bad grabber file", p, e)
    return got


def src_share(work, missing, lo, hi):
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


def src_extra(bs, now):
    """Plugin interface: extra_epg/<name>.py exposes fetch(now) -> [{channel_id,start,stop,title}] (start/stop UTC epoch s)."""
    got = {}
    for p in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "extra_epg", "[!_]*.py"))):
        try:
            spec = importlib.util.spec_from_file_location("extra_" + os.path.basename(p)[:-3], p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for r in mod.fetch(now):
                if base_id(r["channel_id"]) in bs and r["stop"] > r["start"]:
                    got.setdefault(base_id(r["channel_id"]), []).append([int(r["start"]), int(r["stop"]), str(r["title"])[:80]])
        except Exception as e:
            print("extra_epg module failed", p, e)
    return got


_bases = None
def bases(recs):
    global _bases
    if _bases is None:
        _bases = {r["base"] for r in recs if r["base"]}
    return _bases


def main(work, out, grab_dir=None, net=True):
    t0 = time.time()
    now = int(t0)
    lo, hi = window(now)
    recs, probe = load(f"{work}/playlist.json"), load(f"{work}/probe.json")
    bs = bases(recs)
    merged, used = {}, {}
    def add(name, got):
        n = 0
        for b, progs in got.items():
            if b not in merged and progs:
                merged[b] = sorted(progs); n += 1
        used[name] = {"channels_added": n}
        print(name, "adds", n)
    add("extra_epg", src_extra(bs, now))
    if net:
        add("i.mjh.nz", src_mjh(work, recs, load(f"{work}/guides.json"), lo, hi))
    if grab_dir and os.path.isdir(grab_dir):
        add("iptv-org/epg grabber", src_grab(grab_dir, bs, lo, hi))
    if net:
        add("epgshare01", src_share(work, bs - set(merged), lo, hi))

    today = time.strftime("%Y%m%d", time.gmtime(now))
    chans = [{"u": r["url"], "h": r["h"], "id": r["id"], "s": probe.get(r["h"], "t"), "p": r["p"], "c": today} for r in recs]
    os.makedirs(out, exist_ok=True)
    for name, obj in (("channels.json.gz", chans), ("epg.json.gz", merged)):
        with gzip.GzipFile(f"{out}/{name}", "wb", 9, mtime=0) as f:
            f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode())
    cnt = collections.Counter(c["s"] for c in chans)
    meta = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "counts": {"alive": cnt["a"], "dead": cnt["d"], "geo": cnt["g"], "timeout": cnt["t"], "total": len(chans)},
        "epg": {"channels_with_epg": len(merged), "playlist_channels": len(bs),
                "coverage_pct": round(100 * len(merged) / max(1, len(bs)), 1),
                "entries_with_epg_pct": round(100 * sum(r["base"] in merged for r in recs) / max(1, len(recs)), 1),
                "window_utc": [lo, hi]},
        "sources": used,
        "probe": load(f"{work}/probe_stats.json") if os.path.exists(f"{work}/probe_stats.json") else {},
        "sizes_gz": {n: os.path.getsize(f"{out}/{n}") for n in ("channels.json.gz", "epg.json.gz")},
        "publish_seconds": round(time.time() - t0),
        "notes": "S: a=alive d=dead(2 days running) g=geo/auth-blocked from the US runner, t=timeout/unknown. epg keys are base channel ids (tvg-id without @feed).",
    }
    dump(meta, f"{out}/meta.json")
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], a[a.index("--grab") + 1] if "--grab" in a else None, "--no-net" not in a)
