"""Step 4b: run the iptv-org/epg grabber for ONE site on the playlist channels, in chunks, within a deadline.
usage: grab.py WORKDIR EPG_REPO SITE OUTDIR [--deadline SEC] [--cap N] [--chunk N]
Output is written by the grabber only when a chunk finishes, so chunks keep partial results if the deadline hits."""
import os, re, subprocess, sys, time, xml.etree.ElementTree as ET
from common import *


def main(work, repo, site, out, deadline=1200, cap=400, chunk=100):
    t_end = time.time() + deadline
    repo, out = os.path.abspath(repo), os.path.abspath(out)
    repo, out = os.path.abspath(repo), os.path.abspath(out)
    pop = {}
    for r in load(f"{work}/playlist.json"):
        pop[r["base"]] = max(pop.get(r["base"], 0), r["p"])
    chans, seen = [], set()
    import glob
    for f in glob.glob(f"{repo}/sites/{site}/*.channels.xml"):
        for c in ET.parse(f).getroot().iter("channel"):
            b = base_id(c.get("xmltv_id") or "")
            if b in pop and b not in seen:
                seen.add(b); chans.append((pop[b], c))
    chans = [c for _, c in sorted(chans, key=lambda x: -x[0])[:cap]]
    print(site, len(chans), "channels")
    os.makedirs(out, exist_ok=True)
    for i in range(0, len(chans), chunk):
        left = t_end - time.time()
        if left < 60:
            print("deadline reached, skipping remaining chunks"); break
        root = ET.Element("channels")
        for c in chans[i:i + chunk]:
            root.append(c)
        cf = f"{out}/chunk{i // chunk}.channels.xml"
        ET.ElementTree(root).write(cf, encoding="utf-8", xml_declaration=True)
        try:
            subprocess.run(["npm", "run", "grab", "---", f"--channels={cf}", "--days=2", "--maxConnections=10",
                            f"--output={out}/{site}_{i // chunk}.xml"], cwd=repo, timeout=left, check=False)
        except subprocess.TimeoutExpired:
            print("chunk timed out"); break


if __name__ == "__main__":
    a = sys.argv
    kw = {k: int(a[a.index("--" + k) + 1]) for k in ("deadline", "cap", "chunk") if "--" + k in a}
    main(a[1], a[2], a[3], a[4], **kw)
