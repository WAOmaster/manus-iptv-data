"""Step 2: probe every http(s) stream. usage: probe.py WORKDIR HISTORY.json [--deadline SEC]
Writes WORKDIR/probe.json {hash: status} and updates HISTORY.json (rolling state).
Status: a=alive d=dead t=timeout/unknown g=geo-blocked/auth. 'dead' is only published after 2 consecutive dead days."""
import asyncio, datetime, errno, os, ssl, sys, time
from urllib.parse import urljoin
import aiohttp
from common import *

CONC, TIMEOUT, MAXB = int(os.environ.get("PROBE_CONC", 64)), 8, 65536


def classify_http(code):
    if 200 <= code < 300:
        return None
    if code in (401, 403, 451):
        return "g"
    if code in (404, 410):
        return "d"
    return "t"  # 400/405/429/5xx: ambiguous, never call it dead


def looks_ts(b):
    return len(b) > 0 and b[0] == 0x47 and (len(b) < 189 or b[188] == 0x47)


async def fetch(sess, url, hdrs):
    """returns (status_if_failed_or_None, body_bytes, content_type)"""
    async with sess.get(url, headers=hdrs, allow_redirects=True) as r:
        c = classify_http(r.status)
        if c:
            return c, b"", ""
        body = await r.content.read(MAXB)
        return None, body, r.headers.get("Content-Type", "").lower()


async def probe_one(sess, rec):
    hdrs = {"User-Agent": rec["ua"] or "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    if rec["ref"]:
        hdrs["Referer"] = rec["ref"]
    try:
        return await asyncio.wait_for(_probe(sess, rec, hdrs), TIMEOUT)
    except (TimeoutError, asyncio.TimeoutError):
        return "t"
    except (ssl.SSLError, aiohttp.ClientConnectorCertificateError, aiohttp.ClientConnectorSSLError):
        return "d"
    except aiohttp.ClientConnectorDNSError:
        return "d"
    except aiohttp.ClientConnectorError as e:
        return "d" if getattr(e, "os_error", None) and e.os_error.errno == errno.ECONNREFUSED else "t"
    except Exception:
        return "t"  # resets, bad HTTP, too many redirects: ambiguous


async def _probe(sess, rec, hdrs):
    bad, body, ct = await fetch(sess, rec["url"], hdrs)
    if bad:
        return bad
    head = body.lstrip(b"\xef\xbb\xbf \t\r\n")[:8]
    if head.startswith(b"#EXTM3U"):
        text = body.decode("utf-8", "replace")
        if "#EXT-X-STREAM-INF" in text:  # master: the first variant must be a real media playlist
            lines = text.replace("\r", "").split("\n")
            i = next(i for i, l in enumerate(lines) if l.startswith("#EXT-X-STREAM-INF"))
            v = next((l.strip() for l in lines[i + 1:] if l.strip() and not l.startswith("#")), None)
            if not v:
                return "d"
            bad, body, _ = await fetch(sess, urljoin(rec["url"], v), hdrs)
            if bad:
                return bad
            text = body.decode("utf-8", "replace")
        return "a" if ("#EXTINF" in text or "#EXT-X-TARGETDURATION" in text) else "d"
    if looks_ts(body) or (body and ct.startswith(("video/", "audio/", "application/dash+xml", "application/octet-stream"))):
        return "a"
    if b"<MPD" in body[:2048]:
        return "a"
    return "d"  # 2xx but not a stream (html page, empty body)


async def run(recs, deadline):
    asyncio.get_running_loop().set_default_executor(__import__('concurrent.futures').futures.ThreadPoolExecutor(CONC))  # DNS lookups use it
    res, q = {}, asyncio.Queue()
    for r in recs:
        q.put_nowait(r)
    conn = aiohttp.TCPConnector(limit=CONC, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=TIMEOUT + 2)) as sess:
        async def worker():
            while time.time() < deadline:
                try:
                    r = q.get_nowait()
                except asyncio.QueueEmpty:
                    return
                res[r["h"]] = await probe_one(sess, r)
        await asyncio.gather(*[worker() for _ in range(CONC)])
    return res


def apply_history(res, hist, today):
    """dead needs 2 consecutive dead days; first dead day keeps the previous published status (or t)."""
    out, new = {}, {}
    for h, s in res.items():
        old = hist.get(h, {})
        if s == "d":
            n = old.get("n", 0) + 1
            pub = "d" if n >= 2 else (old.get("s") if old.get("s") in ("a", "g") else "t")
        else:
            n, pub = 0, s
        out[h] = pub
        new[h] = {"n": n, "s": pub}
    return out, new


def main(work, hist_path, deadline_s=1500):
    recs = [r for r in load(f"{work}/playlist.json")]
    web = [r for r in recs if r["url"].lower().startswith(("http://", "https://"))]
    t0 = time.time()
    res = asyncio.run(run(web, t0 + deadline_s))
    hist = load(hist_path) if os.path.exists(hist_path) else {}
    out, new = apply_history(res, hist, None)
    import collections
    dump({"raw": dict(collections.Counter(res.values())), "seconds": round(time.time() - t0)}, f"{work}/probe_stats.json")
    for r in recs:  # not probed (non-http or deadline hit): unknown
        out.setdefault(r["h"], "t")
    dump(new, hist_path)
    dump(out, f"{work}/probe.json")
    print("probed", len(res), "of", len(web), "in", round(time.time() - t0), "s", dict(collections.Counter(out.values())))


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], int(a[a.index("--deadline") + 1]) if "--deadline" in a else 1500)
