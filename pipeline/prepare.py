"""Step 1+3: download iptv-org data, build one record per stream, compute popularity, pick grabber sites.
usage: prepare.py WORKDIR [--sample N]   -> WORKDIR/playlist.json, WORKDIR/plan.json (+ raw API files)"""
import collections, math, os, re, sys
from common import *


def main(work, sample=0):
    os.makedirs(work, exist_ok=True)
    for n in ("channels", "feeds", "guides", "streams"):
        open(f"{work}/{n}.json", "wb").write(get(f"{API}{n}.json"))
    channels = {c["id"]: c for c in load(f"{work}/channels.json")}
    feeds = collections.Counter(f["channel"] for f in load(f"{work}/feeds.json"))
    guides = load(f"{work}/guides.json")
    streams = load(f"{work}/streams.json")
    sites_by_ch = collections.defaultdict(set)
    for g in guides:
        if g["channel"]:
            sites_by_ch[g["channel"]].add(g["site"])
    nstreams = collections.Counter(s["channel"] for s in streams if s["channel"])
    qual = {s["url"]: s.get("quality") or "" for s in streams}

    entries = parse_m3u(get(M3U, 300).decode("utf-8", "replace"))
    seen, recs = set(), []
    for e in entries:
        u = e["url"]
        if u in seen:
            continue
        seen.add(u)
        tid = e.get("tvg-id", "")
        b = base_id(tid)
        ch = channels.get(b, {})
        m = re.search(r"\((\d{3,4}p)\)", e["name"])
        recs.append({
            "id": tid, "base": b, "name": re.sub(r"\s*\[[^\]]*\]|\s*\(\d{3,4}p\)", "", e["name"]).strip(),
            "url": u, "h": url_hash(u), "ua": e.get("http-user-agent") or e.get("user-agent", ""),
            "ref": e.get("http-referrer") or e.get("referrer", ""),
            "country": (ch.get("country") or (b.rsplit(".", 1)[-1] if "." in b else "")).lower(),
            "cats": ch.get("categories") or [e.get("group-title", "")], "logo": e.get("tvg-logo", ""),
            "q": qual.get(u) or (m.group(1) if m else ""),
        })
    # popularity: ln(1+G)+0.5ln(1+F)+0.3ln(1+S)+0.5[network]+0.3[launched], normalised to 0-10 over the playlist
    def pop(b):
        c = channels.get(b)
        if not c:
            return 0.0
        return (math.log1p(len(sites_by_ch[b])) + 0.5 * math.log1p(feeds[b]) + 0.3 * math.log1p(nstreams[b])
                + 0.5 * bool(c.get("network")) + 0.3 * bool(c.get("launched")))
    raw = {r["base"]: pop(r["base"]) for r in recs}
    mx = max(raw.values()) or 1
    for r in recs:
        r["p"] = round(raw[r["base"]] / mx * 10, 1)
    if sample:  # local dry runs only
        import random
        random.Random(1).shuffle(recs)
        recs = recs[:sample]
    dump(recs, f"{work}/playlist.json")

    # grabber sites: greedy by playlist channels NOT already covered by the hosted i.mjh.nz guides
    ids = {r["base"] for r in recs}
    covered = {g["channel"] for g in guides if g["site"] == "i.mjh.nz" and g["channel"]}
    covered |= {r["base"] for r in recs if "plu-" in r["url"] or "images.pluto.tv/channels/" in r["logo"]}
    site_ch = collections.defaultdict(set)
    for g in guides:
        if g["channel"] in ids and g["channel"] not in covered and not g["site"].startswith("i.mjh.nz"):
            site_ch[g["site"]].add(g["channel"])
    picked, left = [], set(ids) - covered
    for _ in range(10):
        s = max(site_ch, key=lambda k: len(site_ch[k] & left), default=None)
        if not s or not site_ch[s] & left:
            break
        picked.append({"site": s, "n": len(site_ch[s] & left)})
        left -= site_ch[s]
    dump({"sites": picked, "playlist_channels": len(ids), "entries": len(recs)}, f"{work}/plan.json")
    print(len(recs), "streams;", len(ids), "channels; sites:", picked)


if __name__ == "__main__":
    a = sys.argv
    main(a[1], int(a[a.index("--sample") + 1]) if "--sample" in a else 0)
